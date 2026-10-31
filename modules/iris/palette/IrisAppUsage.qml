pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.common

// Counts only application launches requested from iRiS Spotlight, not open windows.
Singleton {
    id: root
    property var counts: ({})

    function record(id: string): void {
        if (!id) return
        const next = Object.assign({}, root.counts)
        next[id] = Math.max(0, Number(next[id]) || 0) + 1
        root.counts = next
        store.setText(JSON.stringify(next))
    }

    FileView {
        id: store
        path: Directories.stateUserPath + "/iris-spotlight-usage.json"
        blockLoading: true
        atomicWrites: true
        printErrors: false
    }
    Component.onCompleted: {
        try {
            const data = JSON.parse(store.text() || "{}")
            if (data && typeof data === "object" && !Array.isArray(data)) root.counts = data
        } catch (error) { root.counts = ({}) }
    }
}
