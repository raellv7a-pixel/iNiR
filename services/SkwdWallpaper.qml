pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io

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

    signal wallpaperApplied(var data)
    signal themeSourceReady(string path, string output, double generation)
    signal requestFinished(int id, string method, var result, var error)
    signal disconnected()

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

    function handleLine(line: string): void {
        let message
        try { message = JSON.parse(line) } catch (error) { return }
        if (!message || typeof message !== "object") return
        if (typeof message.event === "string") {
            if (message.event === "skwd.wall.applied") {
                themeCoordinator.accept(message.data ?? ({}))
                root.wallpaperApplied(message.data ?? ({}))
            }
            else if (message.event === "skwd.wall.outputs_changed") root.send("wall.outputs", {})
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
        } else if (method === "integration.release" && result.released === true) {
            root.rendererReleased = true
        } else if (method === "integration.acquire" && result.claimed === true) {
            // A claim permits rendering but is not a readiness confirmation.
            root.rendererReleased = false
            root.refresh()
        }
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
                const lost = root.pending
                root.pending = ({})
                root.pendingSince = ({})
                timeoutPoll.stop()
                for (const id of Object.keys(lost))
                    root.requestFinished(Number(id), String(lost[id]), null, { message: "Skwd connection lost" })
                root.disconnected()
                root.scheduleReconnect()
            }
        }
    }
    SkwdThemeCoordinator {
        id: themeCoordinator
        enabled: root.colorSyncEnabled && root.integrationEligible
        onThemeSourceReady: (path, output, generation) => root.themeSourceReady(path, output, generation)
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
