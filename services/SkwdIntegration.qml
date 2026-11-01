pragma Singleton
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import qs
import qs.modules.common
import qs.services

// Session controller. The external preference is verified on disk before
// acquisition, so a crash cannot restart native rendering over a live Skwd.
Singleton {
    id: root
    property bool initialized: false
    property string pendingMode: ""
    property bool operationStarted: false
    property bool daemonLaunchRequested: false
    property bool openWhenConnected: false
    property int pendingAcquireId: 0
    property string pendingAcquireToken: ""
    property int healthRequestId: 0
    property int healthFailures: 0
    property int fallbackRequestId: 0
    property int healthIntervalMs: 10000
    property var monitorNames: Array.from(Quickshell.screens ?? []).map(screen => String(screen?.name ?? "")).filter(Boolean)
    property string lastError: ""
    readonly property string savedMode: String(Config.options?.iris?.skwd?.mode ?? "native")
    readonly property string selectedOutput: String(Config.options?.iris?.skwd?.themeOutput ?? "DP-1")
    readonly property bool useSkwdSelector: root.savedMode === "skwd"
        && (Config.options?.iris?.skwd?.selector ?? "skwd") === "skwd"
    readonly property bool usable: (Config.options?.panelFamily ?? "ii") === "iris"
        && (Config.options?.background?.backend?.provider ?? "awww") === "awww"
        && (Quickshell.env("INIR_STANDALONE_WINDOW") ?? "") !== "1"

    function outputs(): var {
        return Array.from(root.monitorNames ?? [])
    }

    function launch(program: string, args: var): void {
        const directory = String(Quickshell.env("INIR_SKWD_BIN_DIR") ?? "").replace(/\/$/, "")
        if (!directory) {
            Quickshell.execDetached([program].concat(Array.from(args ?? [])))
            return
        }
        const path = directory + ":" + String(Quickshell.env("PATH") ?? "")
        Quickshell.execDetached(["env", "PATH=" + path, directory + "/" + program].concat(Array.from(args ?? [])))
    }

    function statusText(): string {
        if (!root.usable)
            return Translation.tr("Switching wallpaper managers requires the iRiS overlay and the Awww backend.")
        if (root.lastError.includes("connect") || root.lastError.includes("capabilities"))
            return Translation.tr("Could not connect to a compatible Skwd daemon.")
        if (root.lastError)
            return Translation.tr("Could not configure the wallpaper integration. Check the Skwd daemon and try again.")
        return root.pendingMode ? Translation.tr("Switching wallpaper manager…") : ""
    }

    function openSelector(screenName: string): void {
        if (root.useSkwdSelector) {
            root.openSkwd()
            return
        }
        GlobalStates.wallpaperSelectorTargetMonitor = screenName
        GlobalStates.wallpaperSelectorOpen = true
    }

    function openSkwd(): void {
        if (SkwdWallpaper.handoffPhase === "skwd") {
            root.launch("skwd-wall-v2", [])
            return
        }
        root.openWhenConnected = true
        if (!root.requestMode("skwd")) root.openWhenConnected = false
    }

    function start(): void {
        if (root.initialized || !Config.ready || !Config.loadedSafely) return
        root.initialized = true
        // Accessing the singleton installs its pause/resume signal handlers.
        const provider = AwwwBackend.provider
        const shellProcess = (Quickshell.env("INIR_STANDALONE_WINDOW") ?? "") !== "1"
        // Returning to native mode only needs the release acknowledgement;
        // entering integrated mode additionally requires the Awww adapter.
        SkwdWallpaper.nativeAdapterAvailable = shellProcess && provider === "awww"
        SkwdWallpaper.nativeBaselineVerified = shellProcess
        SkwdWallpaper.themeOutput = root.selectedOutput
        if (root.savedMode === "skwd") root.requestMode(root.usable ? "skwd" : "native")
    }

    function requestMode(mode: string): bool {
        if (!root.initialized) root.start()
        if (!root.initialized || (mode !== "native" && mode !== "skwd")
                || (mode === "skwd" && !root.usable)
                || (mode === "native" && !SkwdWallpaper.nativeAdapterAvailable)) {
            root.lastError = "Wallpaper manager cannot be switched from this session."
            return false
        }
        root.lastError = ""
        if (mode === "native") root.openWhenConnected = false
        if (mode === "skwd" && SkwdWallpaper.handoffPhase === "skwd") return true
        if (mode === "native" && SkwdWallpaper.handoffPhase === "native"
                && !SkwdWallpaper.nativeRenderingSuppressed) {
            root.pendingMode = ""
            root.operationStarted = false
            root.daemonLaunchRequested = false
            connectionDeadline.stop()
            SkwdWallpaper.colorSyncEnabled = false
            SkwdWallpaper.enabled = false
            return true
        }
        root.pendingMode = mode
        SkwdWallpaper.enabled = true
        SkwdWallpaper.themeOutput = root.selectedOutput
        if (mode === "native") {
            root.operationStarted = true
            return SkwdWallpaper.requestOwnership("native", root.outputs())
        }
        SkwdWallpaper.colorSyncEnabled = true
        root.operationStarted = false
        connectionDeadline.restart()
        if (!SkwdWallpaper.connected && !root.daemonLaunchRequested) {
            root.daemonLaunchRequested = true
            // If another daemon owns the socket it is left untouched. A newly
            // launched daemon starts with wallpaper restoration blocked.
            root.launch("skwd-walld", ["--external-wallpaper-owner"])
        }
        if (!SkwdWallpaper.connected) daemonRecovery.restart()
        root.tryStart()
        return true
    }

    function tryStart(): void {
        if (root.pendingMode !== "skwd" || root.operationStarted || !SkwdWallpaper.integrationCompatible) return
        connectionDeadline.stop()
        root.operationStarted = true
        if (!SkwdWallpaper.requestOwnership("skwd", root.outputs())) {
            root.operationStarted = false
            root.lastError = "Skwd is missing the required integration capabilities."
        }
    }

    function seedMissingOutputs(result: var): void {
        if (SkwdWallpaper.handoffPhase !== "waiting-ready") return
        // Signal var arguments may expose a QVariantList rather than a JS
        // Array. Normalize before inspecting the daemon's output list.
        const savedOutputs = Array.from(result?.outputs ?? [])
        const background = Config.options?.background ?? ({})
        const monitors = Array.from(background.wallpapersByMonitor ?? [])
        for (const output of root.outputs()) {
            const saved = savedOutputs.find(item => item.name === output)
            if (!saved || saved.path || saved.we_id || saved.current) continue
            const entry = (background.multiMonitor?.enable ?? false) ? monitors.find(item => item.monitor === output) : null
            const path = String(entry?.path || background.wallpaperPath || "").replace(/^file:\/\//, "")
            if (!path) continue
            const video = /\.(mp4|webm|mkv|avi|mov)$/i.test(path)
            SkwdWallpaper.send("wall.apply", {type: video ? "video" : "static", path: path, output: output, source: "user"})
        }
    }

    Component.onCompleted: root.start()

    onSelectedOutputChanged: SkwdWallpaper.themeOutput = root.selectedOutput
    onUsableChanged: if (root.initialized && !root.usable
            && (SkwdWallpaper.nativeRenderingSuppressed || root.pendingMode === "skwd"))
        root.requestMode("native")
    FileView {
        id: persistedConfig
        path: Config.filePath
        watchChanges: true
        onLoaded: {
            if (!root.pendingAcquireId || SkwdWallpaper.handoffPhase !== "acquire-skwd") return
            let saved
            try { saved = JSON.parse(persistedConfig.text()) } catch (error) { return }
            if (saved?.iris?.skwd?.mode !== "skwd") return
            const id = root.pendingAcquireId
            const token = root.pendingAcquireToken
            root.pendingAcquireId = 0
            root.pendingAcquireToken = ""
            persistenceRetry.stop()
            SkwdWallpaper.acquisitionPersisted(id, token)
        }
    }
    Timer {
        id: persistenceRetry
        interval: 100
        repeat: true
        onTriggered: {
            if (!root.pendingAcquireId || SkwdWallpaper.handoffPhase !== "acquire-skwd") {
                root.pendingAcquireId = 0
                root.pendingAcquireToken = ""
                stop()
                return
            }
            persistedConfig.reload()
        }
    }
    Timer {
        id: connectionDeadline
        interval: 15000
        onTriggered: {
            if (root.pendingMode !== "skwd" || root.operationStarted) return
            root.lastError = "Could not connect to a compatible Skwd daemon."
            if (root.savedMode !== "skwd") {
                root.pendingMode = ""
                root.daemonLaunchRequested = false
                SkwdWallpaper.colorSyncEnabled = false
                SkwdWallpaper.enabled = false
            }
        }
    }
    Timer {
        id: daemonRecovery
        interval: 5000
        repeat: true
        onTriggered: {
            if (SkwdWallpaper.connected || (root.savedMode !== "skwd" && root.pendingMode !== "skwd")) {
                stop()
                return
            }
            root.launch("skwd-walld", ["--external-wallpaper-owner"])
        }
    }
    Timer {
        interval: Math.max(20, root.healthIntervalMs)
        repeat: true
        running: SkwdWallpaper.handoffPhase === "skwd" && SkwdWallpaper.integrationEligible
        onTriggered: if (!root.healthRequestId)
            root.healthRequestId = SkwdWallpaper.send("integration.snapshot", {})
    }
    Connections {
        target: Config
        function onReadyChanged(): void { root.start() }
        function onLoadedSafelyChanged(): void { root.start() }
    }
    Connections {
        target: Quickshell
        function onScreensChanged(): void {
            SkwdWallpaper.updateOwnershipOutputs(Array.from(Quickshell.screens ?? []).map(screen => String(screen?.name ?? "")).filter(Boolean))
        }
    }
    Connections {
        target: SkwdWallpaper
        function onConnectedChanged(): void {
            if (SkwdWallpaper.connected) daemonRecovery.stop()
        }
        function onDisconnected(): void {
            if (root.savedMode !== "skwd" && root.pendingMode !== "skwd" && root.pendingMode !== "native") return
            if (root.pendingMode !== "native") {
                root.pendingMode = "skwd"
                root.operationStarted = false
            }
            daemonRecovery.restart()
        }
        function onIntegrationCompatibleChanged(): void { root.tryStart() }
        function onThemeAuthorityChanged(): void {
            if (SkwdWallpaper.connected && SkwdWallpaper.handoffPhase === "skwd" && SkwdWallpaper.themeAuthority !== "inir") root.requestMode("native")
            else root.tryStart()
        }
        function onPickOnlyChanged(): void {
            if (SkwdWallpaper.connected && SkwdWallpaper.handoffPhase === "skwd" && SkwdWallpaper.pickOnly) root.requestMode("native")
            else root.tryStart()
        }
        function onHandoffFailed(message: string): void {
            root.openWhenConnected = false
            root.lastError = message
            console.warn("[SkwdIntegration]", message)
        }
        function onRequestFinished(id: int, method: string, result: var, error: var): void {
            if (id === root.fallbackRequestId) {
                root.fallbackRequestId = 0
                if (!error) root.seedMissingOutputs(result)
                return
            }
            if (id !== root.healthRequestId) return
            root.healthRequestId = 0
            if (SkwdWallpaper.handoffPhase !== "skwd") { root.healthFailures = 0; return }
            const outputs = root.outputs()
            const renderedOutputs = Array.from(result?.outputs ?? [])
            const ready = !error && result?.available === true
                && outputs.length > 0 && outputs.every(output => renderedOutputs.some(item => item?.rendered === true && item.output === output))
            root.healthFailures = ready || outputs.length === 0 ? 0 : root.healthFailures + 1
            if (root.healthFailures < 3) return
            root.healthFailures = 0
            console.warn("[SkwdIntegration] Renderer health confirmation failed for", JSON.stringify(outputs))
            SkwdWallpaper.markRendererUnhealthy()
            root.pendingMode = "skwd"
            root.operationStarted = false
            root.tryStart()
        }
        function onAcquirePersistenceRequested(id: int, token: string): void {
            root.pendingAcquireId = id
            root.pendingAcquireToken = token
            Config.setNestedValue("iris.skwd.mode", "skwd")
            persistenceRetry.restart()
            persistedConfig.reload()
        }
        function onHandoffPhaseChanged(): void {
            if (SkwdWallpaper.handoffPhase === "waiting-ready") {
                root.fallbackRequestId = SkwdWallpaper.send("wall.outputs", {})
            } else if (SkwdWallpaper.handoffPhase === "skwd") {
                if (root.openWhenConnected) {
                    root.openWhenConnected = false
                    root.launch("skwd-wall-v2", [])
                }
                Config.setNestedValue("iris.skwd.mode", "skwd")
                root.pendingMode = ""
                root.operationStarted = false
            } else if (SkwdWallpaper.handoffPhase === "native" && root.operationStarted
                    && !SkwdWallpaper.nativeRenderingSuppressed) {
                if (root.savedMode === "skwd") Config.setNestedValue("iris.skwd.mode", "native")
                root.pendingMode = ""
                root.operationStarted = false
                SkwdWallpaper.colorSyncEnabled = false
                SkwdWallpaper.enabled = false
                root.daemonLaunchRequested = false
            }
        }
    }
}
