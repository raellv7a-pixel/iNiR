pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.common

// Transport only: callers opt in explicitly. No renderer or configuration is
// changed by opening this connection.
Singleton {
    id: root

    property bool enabled: false
    property string socketPath: {
        const override = Quickshell.env("SKWD_WALL_V2_SOCK") ?? ""
        if (override.length > 0) return override
        const runtime = Quickshell.env("XDG_RUNTIME_DIR") ?? ""
        return (runtime.length > 0 ? runtime : "/tmp") + "/skwd-wall-v2/wall.sock"
    }
    property bool connected: false
    readonly property bool ready: root.connected && root.protocolReady && root.subscribed
    property bool protocolReady: false
    property bool subscribed: false
    property string themeAuthority: ""
    property bool pickOnly: true
    property bool rendererReleased: true
    property var capabilities: []
    readonly property bool integrationCompatible: root.ready
        && root.capabilities.includes("inir-theme-authority-v1")
        && root.capabilities.includes("output-theme-source-v1")
    readonly property bool integrationEligible: root.integrationCompatible
        && root.themeAuthority === "inir" && !root.pickOnly && !root.rendererReleased
    property var outputs: []
    property string lastError: ""
    property int requestSerial: 0
    property int newestStatusRequest: 0
    property int newestOutputsRequest: 0
    property var pending: ({})
    property var pendingSince: ({})
    property int requestTimeoutMs: 30000
    property int reconnectAttempt: 0
    property bool colorSyncEnabled: false
    property alias themeOutput: themeCoordinator.output
    property string confirmedThemeSource: ""
    property var confirmedSources: ({})
    property var confirmedGenerations: ({})
    // The shell must install a native-renderer adapter and establish its
    // baseline before ownership changes can be requested.
    property bool nativeAdapterAvailable: false
    property bool nativeBaselineVerified: false
    // Set only by the native adapter while it is relinquishing ownership.
    // Until Config has loaded, keep native rendering parked. A persisted Skwd
    // session must not briefly start Awww before its ownership is reconciled.
    property bool nativeRenderingSuppressed: true
    property bool bootDecisionMade: false
    property bool nativeBackdropStopped: false
    readonly property alias handoffPhase: handoff.phase
    property var handoffRequests: ({})

    signal wallpaperApplied(var data)
    signal themeSourceReady(string path, string output, double generation)
    signal requestFinished(int id, string method, var result, var error)
    signal disconnected()
    signal nativePauseRequested(int id)
    signal nativeResumeRequested(int id)
    signal acquirePersistenceRequested(int id, string token)
    signal handoffFailed(string message)

    function decideBootOwnership(): void {
        if (root.bootDecisionMade || !Config.ready || !Config.loadedSafely) return
        const integrated = (Config.options?.iris?.skwd?.mode ?? "native") === "skwd"
        root.nativeRenderingSuppressed = integrated
        if (root.nativeRenderingSuppressed) {
            // Neither cached settings nor a marker proves which renderer owns
            // the desktop after a shell restart. Release must be acknowledged.
            handoff.phase = "blocked"
            handoff.desired = "skwd"
            handoff.nativeKnownActive = false
        }
        root.bootDecisionMade = true
    }
    Component.onCompleted: root.decideBootOwnership()
    Connections {
        target: Config
        function onReadyChanged(): void { root.decideBootOwnership() }
        function onLoadedSafelyChanged(): void { root.decideBootOwnership() }
    }

    function requestOwnership(mode: string, outputs: var): bool {
        if (!root.nativeAdapterAvailable || !root.nativeBaselineVerified) return false
        // Always accept a request to return to native mode. If the socket is
        // unavailable the coordinator remains blocked and retries after reconnect.
        if (mode === "native") {
            handoff.expectedOutputs = Array.from(outputs ?? [])
            handoff.request(mode)
            return true
        }
        if (mode !== "skwd" || !root.integrationCompatible
                || root.themeAuthority !== "inir" || root.pickOnly
                || !root.capabilities.includes("renderer-handoff-v1")
                || !root.capabilities.includes("rendered-snapshot-v1")) return false
        handoff.expectedOutputs = Array.from(outputs ?? [])
        handoff.request(mode)
        return true
    }

    function updateOwnershipOutputs(outputs: var): void {
        handoff.expectedOutputs = Array.from(outputs ?? [])
    }

    function markRendererUnhealthy(): void {
        if (handoff.phase !== "skwd") return
        handoff.nativeKnownActive = false
        handoff.desired = "skwd"
        handoff.phase = "blocked"
    }

    function rememberSource(item: var, seedOnly = false): void {
        const output = String(item?.output ?? "")
        const source = String(item?.theme_source ?? "")
        if (item?.rendered !== true || !output || !source || (seedOnly && root.confirmedSources[output])) return
        const generation = seedOnly ? -1 : Number(item?.generation)
        if (!Number.isFinite(generation) || generation < (seedOnly ? -1 : 0)) return
        if (!seedOnly && root.confirmedGenerations[output] !== undefined
                && generation <= root.confirmedGenerations[output]) return
        const next = Object.assign({}, root.confirmedSources)
        const generations = Object.assign({}, root.confirmedGenerations)
        next[output] = source
        generations[output] = generation
        root.confirmedSources = next
        root.confirmedGenerations = generations
    }

    function sourceForOutput(output: string): string {
        return String(root.confirmedSources[output || root.themeOutput] ?? "")
    }

    function sendHandoff(method: string, params: var, operationId: int, action: string): void {
        const id = root.send(method, params)
        if (!id) {
            handoff.complete(operationId, action, false, { message: "Skwd is disconnected" })
            return
        }
        const next = Object.assign({}, root.handoffRequests)
        next[id] = { operationId: operationId, action: action }
        root.handoffRequests = next
    }

    function finishHandoffRequest(id: int, method: string, result: var, error: var): void {
        const request = root.handoffRequests[id]
        if (!request) return
        const next = Object.assign({}, root.handoffRequests)
        delete next[id]
        root.handoffRequests = next
        const ok = !error && (method === "integration.release" ? result?.released === true
            : method === "integration.acquire" && result?.claimed === true)
        handoff.complete(request.operationId, request.action, ok, error ?? result)
    }

    function nativePauseFinished(id: int, ok: bool, message = ""): void {
        handoff.complete(id, "pause-native", ok, {message: message})
    }

    function nativeResumeFinished(id: int, ok: bool, message = ""): void {
        handoff.complete(id, "resume-native", ok, {message: message})
    }

    function acquisitionPersisted(id: int, token: string): void {
        if (handoff.phase !== "acquire-skwd" || handoff.operationId !== id || handoff.releaseToken !== token) return
        root.sendHandoff("integration.acquire", {token: token}, id, "acquire-skwd")
    }

    function applySelection(path: string, output: string, isVideo: bool): bool {
        if (handoff.phase !== "skwd" || !root.integrationEligible || !path) return false
        return root.send("wall.apply", {
            type: isVideo ? "video" : "static", path: path,
            output: output || "*", source: "user"
        }) !== 0
    }

    function send(method: string, params: var): int {
        if (!socket.connected) return 0
        const id = ++root.requestSerial
        if (method === "status") root.newestStatusRequest = id
        else if (method === "wall.outputs") root.newestOutputsRequest = id
        const next = Object.assign({}, root.pending)
        next[id] = method
        root.pending = next
        const times = Object.assign({}, root.pendingSince)
        times[id] = Date.now()
        root.pendingSince = times
        timeoutPoll.start()
        socket.write(JSON.stringify({ id: id, method: method, params: params ?? ({}) }) + "\n")
        socket.flush()
        return id
    }

    function refresh(): void {
        if (!socket.connected) return
        root.send("status", {})
        root.send("wall.outputs", {})
    }

    function reconcile(): void {
        if (root.colorSyncEnabled && root.integrationEligible
                && root.capabilities.includes("rendered-snapshot-v1"))
            root.send("integration.snapshot", {})
    }

    onIntegrationEligibleChanged: if (root.integrationEligible) root.reconcile()
    onColorSyncEnabledChanged: if (root.colorSyncEnabled) root.reconcile()
    onReadyChanged: if (root.ready && handoff.phase === "blocked" && handoff.desired === "native")
        handoff.request("native")
    onThemeOutputChanged: root.confirmedThemeSource = ""
    onNativeRenderingSuppressedChanged: if (!root.nativeRenderingSuppressed) {
        root.confirmedThemeSource = ""
        root.confirmedSources = ({})
        root.confirmedGenerations = ({})
    }

    function handleLine(line: string): void {
        let message
        try { message = JSON.parse(line) } catch (error) { return }
        if (!message || typeof message !== "object") return
        if (typeof message.event === "string") {
            if (message.event === "skwd.wall.applied") {
                if (root.integrationEligible) root.rememberSource(message.data ?? ({}))
                themeCoordinator.accept(message.data ?? ({}))
                root.wallpaperApplied(message.data ?? ({}))
                if (handoff.phase === "waiting-ready" && message.data?.rendered === true)
                    root.send("integration.snapshot", {})
            }
            else if (message.event === "skwd.wall.outputs_changed") {
                root.send("wall.outputs", {})
                if (handoff.phase === "waiting-ready") root.send("integration.snapshot", {})
            }
            else if (message.event === "skwd.wall.config_changed") root.send("status", {})
            else if (message.event === "skwd.wall.ownership_changed") {
                if (typeof message.data?.rendering_blocked === "boolean")
                    root.rendererReleased = message.data.rendering_blocked
                root.send("status", {})
            }
            return
        }
        const id = Number(message.id)
        const method = root.pending[id]
        if (!method) return
        const next = Object.assign({}, root.pending)
        delete next[id]
        root.pending = next
        const times = Object.assign({}, root.pendingSince)
        delete times[id]
        root.pendingSince = times
        if (Object.keys(next).length === 0) timeoutPoll.stop()
        const result = message.result ?? ({})
        const error = message.error ?? null
        if (error) {
            root.lastError = String(error.message ?? error)
            if (method === "subscribe") root.subscribed = false
            else if (method === "status" && id === root.newestStatusRequest) {
                root.protocolReady = false
                root.themeAuthority = ""
                root.pickOnly = true
                root.rendererReleased = true
                root.capabilities = []
            }
        } else if (method === "subscribe") root.subscribed = result.subscribed === true
        else if (method === "status" && id === root.newestStatusRequest) {
            root.protocolReady = result.protocol?.name === "skwd-wall" && Number(result.protocol?.version) === 1
            root.themeAuthority = String(result.theme_authority ?? "")
            root.pickOnly = result.pick_only !== false
            root.rendererReleased = result.renderer_released !== false
            root.capabilities = Array.isArray(result.integration_features) ? result.integration_features : []
            if (!root.protocolReady) root.lastError = "Unsupported Skwd protocol"
        } else if (method === "wall.outputs" && id === root.newestOutputsRequest) {
            root.outputs = Array.isArray(result.outputs) ? result.outputs : []
        } else if (method === "integration.snapshot") {
            themeCoordinator.seed(result)
            if (result.available === true && Array.isArray(result.outputs))
                for (const item of result.outputs) {
                    root.rememberSource(item, true)
                    if (item?.rendered === true) handoff.confirmReady(String(item.output ?? ""))
                }
        } else if (method === "integration.release" && result.released === true) {
            root.rendererReleased = true
        } else if (method === "integration.acquire" && result.claimed === true) {
            // A claim permits rendering but is not a readiness confirmation.
            root.rendererReleased = false
            root.refresh()
        }
        root.finishHandoffRequest(id, method, result, error)
        root.requestFinished(id, method, result, error)
    }

    function scheduleReconnect(): void {
        if (!root.enabled || reconnect.running) return
        reconnect.interval = Math.min(15000, 400 * Math.pow(2, Math.min(root.reconnectAttempt++, 5)))
        reconnect.start()
    }

    onEnabledChanged: {
        reconnect.stop()
        if (enabled) socket.connected = true
        else socket.connected = false
    }

    Socket {
        id: socket
        path: root.socketPath
        parser: SplitParser { onRead: line => root.handleLine(line) }
        onError: error => {
            root.lastError = "Skwd socket error: " + error
            root.scheduleReconnect()
        }
        onConnectionStateChanged: {
            root.connected = connected
            if (connected) {
                root.reconnectAttempt = 0
                root.lastError = ""
                root.send("subscribe", {})
                root.refresh()
            } else {
                root.protocolReady = false
                root.subscribed = false
                root.themeAuthority = ""
                root.pickOnly = true
                root.rendererReleased = true
                root.capabilities = []
                root.outputs = []
                root.confirmedSources = ({})
                root.confirmedGenerations = ({})
                const lost = root.pending
                root.pending = ({})
                root.pendingSince = ({})
                timeoutPoll.stop()
                for (const id of Object.keys(lost)) {
                    root.finishHandoffRequest(Number(id), String(lost[id]), null, { message: "Skwd connection lost" })
                    root.requestFinished(Number(id), String(lost[id]), null, { message: "Skwd connection lost" })
                }
                if (handoff.phase === "skwd") {
                    handoff.nativeKnownActive = false
                    handoff.desired = "skwd"
                    handoff.phase = "blocked"
                }
                root.disconnected()
                root.scheduleReconnect()
            }
        }
    }
    SkwdThemeCoordinator {
        id: themeCoordinator
        enabled: root.colorSyncEnabled && root.integrationEligible
        onThemeSourceReady: (path, output, generation) => {
            root.confirmedThemeSource = path
            root.themeSourceReady(path, output, generation)
        }
    }
    SkwdHandoff {
        id: handoff
        onReleaseRequested: id => root.sendHandoff("integration.release", {}, id, handoff.phase)
        onAcquireRequested: (id, token) => root.acquirePersistenceRequested(id, token)
        onPauseNativeRequested: id => root.nativePauseRequested(id)
        onResumeNativeRequested: id => root.nativeResumeRequested(id)
        onFailed: message => root.handoffFailed(message)
        onPhaseChanged: if (handoff.phase === "waiting-ready") root.send("integration.snapshot", {})
    }
    Timer {
        id: timeoutPoll
        interval: Math.max(20, Math.min(1000, root.requestTimeoutMs / 2))
        repeat: true
        onTriggered: {
            const now = Date.now()
            const remaining = Object.assign({}, root.pending)
            const times = Object.assign({}, root.pendingSince)
            const expired = []
            for (const id of Object.keys(remaining)) {
                if (now - Number(times[id] ?? now) < Math.max(1, root.requestTimeoutMs)) continue
                expired.push([Number(id), String(remaining[id])])
                delete remaining[id]
                delete times[id]
            }
            root.pending = remaining
            root.pendingSince = times
            if (Object.keys(remaining).length === 0) timeoutPoll.stop()
            for (const item of expired) {
                if (item[1] === "status" && item[0] === root.newestStatusRequest) {
                    root.protocolReady = false
                    root.rendererReleased = true
                }
                root.lastError = "Skwd request timed out"
                root.finishHandoffRequest(item[0], item[1], null, { message: root.lastError })
                root.requestFinished(item[0], item[1], null, { message: root.lastError })
            }
        }
    }
    Timer {
        id: reconnect
        repeat: false
        onTriggered: if (root.enabled) socket.connected = true
    }
}
