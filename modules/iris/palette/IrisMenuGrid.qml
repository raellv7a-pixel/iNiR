pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import qs.modules.common.widgets
import qs.modules.iris.components
import qs.modules.iris.style

// A virtualized grid shared by the home sections and the alphabetic catalogue.
GridView {
    id: grid
    property var entries: []
    property int selection: -1
    signal chosen(int index)
    signal pointed(int index, var area, var event)
    readonly property real d: IrisStyle.density
    property int columns: 4
    implicitHeight: Math.ceil(entries.length / Math.max(1, columns)) * cellHeight
    cellWidth: width / columns
    cellHeight: 100 * d
    model: entries
    currentIndex: selection
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: IrisScrollBar {}

    onSelectionChanged: {
        if (selection >= 0 && selection < count)
            positionViewAtIndex(selection, GridView.Contain)
    }

    delegate: Item {
        id: tile
        required property var modelData
        required property int index
        width: grid.cellWidth
        height: grid.cellHeight
        Accessible.role: Accessible.Button
        Accessible.name: String(modelData.name ?? "")
        Rectangle {
            anchors.fill: parent
            anchors.margins: 3 * grid.d
            radius: IrisStyle.radiusTile
            color: grid.selection === tile.index ? IrisStyle.tintFill(IrisStyle.accent) : "transparent"
        }
        SmartAppIcon {
            id: icon
            anchors.horizontalCenter: parent.horizontalCenter
            y: 8 * grid.d
            icon: tile.modelData.iconName
            fallback: "application-x-executable"
            iconSize: Math.round(Math.min(42 * grid.d, Math.max(20 * grid.d, grid.cellWidth - 12 * grid.d)))
        }
        IrisText {
            anchors.top: icon.bottom
            anchors.topMargin: 5 * grid.d
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 4 * grid.d
            horizontalAlignment: Text.AlignHCenter
            text: String(tile.modelData.name ?? "")
            color: IrisStyle.text
            font.pixelSize: IrisStyle.typeFootnote
            maximumLineCount: 2
            wrapMode: Text.Wrap
            elide: Text.ElideRight
        }
        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            onPositionChanged: event => grid.pointed(tile.index, mouse, event)
            onClicked: grid.chosen(tile.index)
        }
    }
}
