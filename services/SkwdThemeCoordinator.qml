pragma ComponentBehavior: Bound

import QtQuick

// Keep only the latest confirmed render for the configured global-theme output.
// This component does not write settings, run a generator, or apply wallpapers.
QtObject {
    id: root
    property bool enabled: false
    property string output: ""
    property int settleMs: 250
    property var latest: ({})
    property string lastSignature: ""
    signal themeSourceReady(string path, string output, double generation)

    function accept(event: var): void {
        if (!root.enabled || !event || event.rendered !== true) return
        const output = String(event.output ?? "")
        const path = String(event.theme_source ?? "")
        const generation = Number(event.generation)
        if (!output || !path || !Number.isFinite(generation) || generation < 0) return
        const previous = root.latest[output]
        if (previous && generation <= previous.generation) return
        const next = Object.assign({}, root.latest)
        next[output] = { path: path, generation: generation }
        root.latest = next
        if (output === root.output) root.queueSelected()
    }

    // Snapshot generations belong to Paper, not the daemon event stream.
    // Seed only missing outputs so a newer subscribed event always wins.
    function seed(snapshot: var): void {
        if (!root.enabled || snapshot?.available !== true || !Array.isArray(snapshot.outputs)) return
        const next = Object.assign({}, root.latest)
        let changed = false
        for (const item of snapshot.outputs) {
            const output = String(item?.output ?? "")
            const path = String(item?.theme_source ?? "")
            if (item?.rendered !== true || !output || !path || next[output]) continue
            next[output] = { path: path, generation: -1 }
            changed = true
        }
        if (changed) {
            root.latest = next
            root.queueSelected()
        }
    }

    function queueSelected(): void {
        timer.stop()
        if (!root.enabled || !root.output || !root.latest[root.output]) return
        timer.start()
    }

    function reset(): void {
        timer.stop()
        root.latest = ({})
        root.lastSignature = ""
    }

    onOutputChanged: root.queueSelected()
    onEnabledChanged: if (!enabled) root.reset()

    property Timer timer: Timer {
        interval: Math.max(0, root.settleMs)
        repeat: false
        onTriggered: {
            const item = root.latest[root.output]
            if (!root.enabled || !item) return
            const signature = JSON.stringify([root.output, item.path, item.generation])
            if (signature === root.lastSignature) return
            root.lastSignature = signature
            root.themeSourceReady(item.path, root.output, item.generation)
        }
    }
}
