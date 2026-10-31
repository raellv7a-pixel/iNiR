pragma ComponentBehavior: Bound

import QtQuick

// Coordinates ownership only. The caller performs and acknowledges each action;
// timeouts and uncertain acknowledgements never start the native renderer until
// a fresh Skwd release has succeeded.
QtObject {
    id: root
    property string phase: "native"
    property string desired: "native"
    property var expectedOutputs: []
    property var readyOutputs: ({})
    property string releaseToken: ""
    property string lastError: ""
    property int operationId: 0
    property int uncertainPauseId: 0
    property int timeoutMs: 30000
    signal releaseRequested(int id)
    signal pauseNativeRequested(int id)
    signal acquireRequested(int id, string token)
    signal resumeNativeRequested(int id)
    signal failed(string message)

    function startOperation(name: string): void {
        const id = ++root.operationId
        root.phase = name
        if (root.operationId !== id || root.phase !== name) return
        watchdog.restart()
        // A deferred signal lets a synchronous adapter reply without a
        // nested state change while startOperation is still executing.
        Qt.callLater(() => {
            if (root.operationId !== id || root.phase !== name) return
            if (name === "release-for-skwd" || name === "release-for-native") root.releaseRequested(id)
            else if (name === "pause-native") root.pauseNativeRequested(id)
            else if (name === "acquire-skwd") root.acquireRequested(id, root.releaseToken)
            else if (name === "resume-native") root.resumeNativeRequested(id)
        })
    }

    function request(mode: string): void {
        if (mode !== "native" && mode !== "skwd") return
        root.desired = mode
        if (root.phase === "native" && mode === "skwd") root.startOperation("release-for-skwd")
        else if ((root.phase === "skwd" || (root.phase === "blocked" && !root.uncertainPauseId)) && mode === "native")
            root.startOperation("release-for-native")
        else if (root.phase === "waiting-ready" && mode === "native")
            root.startOperation("release-for-native")
    }

    function complete(id: int, action: string, ok: bool, result: var): void {
        if (action === "pause-native" && id === root.uncertainPauseId) {
            root.uncertainPauseId = 0
            root.desired = "native"
            root.startOperation("release-for-native")
            return
        }
        if (id !== root.operationId || action !== root.phase) return
        watchdog.stop()
        if (!ok) {
            root.lastError = String(result?.message ?? "Wallpaper ownership operation failed")
            root.failed(root.lastError)
            if (action === "release-for-skwd") root.phase = "native"
            else if (action === "pause-native") {
                root.desired = "native"
                root.startOperation("resume-native")
            }
            else if (action === "acquire-skwd") {
                root.desired = "native"
                root.startOperation("release-for-native")
            } else root.phase = "blocked"
            return
        }
        if (action === "release-for-skwd") {
            root.releaseToken = String(result?.token ?? "")
            if (!root.releaseToken) {
                root.lastError = "Skwd did not provide an ownership token"
                root.phase = "native"
                root.failed(root.lastError)
            } else if (root.desired === "native") root.phase = "native"
            else root.startOperation("pause-native")
        } else if (action === "pause-native") {
            if (root.desired === "native") root.startOperation("resume-native")
            else root.startOperation("acquire-skwd")
        } else if (action === "acquire-skwd") {
            if (root.desired === "native") root.startOperation("release-for-native")
            else {
                root.readyOutputs = ({})
                watchdog.restart()
                root.phase = "waiting-ready"
            }
        } else if (action === "release-for-native") root.startOperation("resume-native")
        else if (action === "resume-native") {
            root.phase = "native"
            if (root.desired === "skwd") root.startOperation("release-for-skwd")
        }
    }

    function confirmReady(output: string): void {
        if (root.phase !== "waiting-ready" || !output) return
        const next = Object.assign({}, root.readyOutputs)
        next[output] = true
        root.readyOutputs = next
        root.checkReady()
    }

    function checkReady(): void {
        const outputs = Array.from(root.expectedOutputs ?? []).map(String).filter(Boolean)
        if (root.phase !== "waiting-ready" || outputs.length === 0
                || !outputs.every(output => root.readyOutputs[output] === true)) return
        watchdog.stop()
        root.phase = "skwd"
    }
    onExpectedOutputsChanged: root.checkReady()

    property Timer watchdog: Timer {
        interval: Math.max(50, root.timeoutMs)
        repeat: false
        onTriggered: {
            if (root.phase === "waiting-ready") {
                root.lastError = "Skwd did not confirm all outputs"
                root.failed(root.lastError)
                root.desired = "native"
                root.startOperation("release-for-native")
            } else if (root.phase === "pause-native") {
                // The adapter may still be stopping native processes. Do not
                // race that unfinished action with a native restart.
                root.lastError = "Native renderer did not stop in time"
                root.uncertainPauseId = root.operationId
                root.phase = "blocked"
                root.failed(root.lastError)
            } else root.complete(root.operationId, root.phase, false, { message: "Wallpaper ownership operation timed out" })
        }
    }
}
