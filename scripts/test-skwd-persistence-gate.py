#!/usr/bin/env python3
"""The daemon cannot acquire until the integrated mode exists on disk."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PersistenceGateTest(unittest.TestCase):
    def test_waits_for_config_file_before_acquisition(self):
        quickshell = shutil.which('quickshell')
        if not quickshell:
            self.skipTest('quickshell is not installed')
        with tempfile.TemporaryDirectory(prefix='inir-skwd-save-') as temp:
            base = Path(temp)
            services = base / 'qs/services'
            common = base / 'qs/modules/common'
            for path in (services, common, base / 'runtime'):
                path.mkdir(parents=True, exist_ok=True)
            (base / 'runtime').chmod(0o700)
            config_file = base / 'config.json'
            config_file.write_text(json.dumps({'iris': {'skwd': {'mode': 'native'}}}))
            shutil.copy(ROOT / 'services/SkwdIntegration.qml', services / 'SkwdIntegration.qml')
            (base / 'qs/qmldir').write_text('module qs\nsingleton GlobalStates 1.0 GlobalStates.qml\n')
            (base / 'qs/GlobalStates.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { property bool wallpaperSelectorOpen: false; property string wallpaperSelectorTargetMonitor: "" }\n')
            (common / 'qmldir').write_text('module qs.modules.common\nsingleton Config 1.0 Config.qml\n')
            (common / 'Config.qml').write_text('''pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
QtObject {
    id: root
    property bool ready: true
    property bool loadedSafely: true
    property bool saveStarted: false
    property string filePath: Quickshell.env("TEST_CONFIG_PATH")
    property var options: ({panelFamily: "iris", background: {backend: {provider: "awww"}}, iris: {skwd: {mode: "native", themeOutput: "DP-1"}}})
    function setNestedValue(path, value) { let v = JSON.parse(JSON.stringify(options)); v.iris.skwd.mode = value; options = v; timer.restart() }
    property Timer timer: Timer { interval: 250; onTriggered: { root.saveStarted = true; writer.setText(JSON.stringify(root.options)) } }
    property FileView writer: FileView { path: root.filePath; watchChanges: false }
}
''')
            (services / 'qmldir').write_text('module qs.services\nsingleton SkwdIntegration 1.0 SkwdIntegration.qml\nsingleton SkwdWallpaper 1.0 SkwdWallpaper.qml\nsingleton AwwwBackend 1.0 AwwwBackend.qml\n')
            (services / 'AwwwBackend.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { readonly property string provider: "awww" }\n')
            (services / 'SkwdWallpaper.qml').write_text('''pragma Singleton
import QtQuick
import qs.modules.common
QtObject {
    id: root
    property bool nativeAdapterAvailable: false
    property bool nativeBaselineVerified: false
    property bool nativeRenderingSuppressed: false
    property bool enabled: false
    property bool connected: true
    property bool colorSyncEnabled: false
    property bool integrationCompatible: true
    property bool integrationEligible: true
    property string themeAuthority: "inir"
    property bool pickOnly: false
    property string themeOutput: ""
    property string handoffPhase: "native"
    signal handoffFailed(string message)
    signal disconnected()
    signal requestFinished(int id, string method, var result, var error)
    function send(method, params) { return 0 }
    function markRendererUnhealthy() { handoffPhase = "blocked" }
    signal acquirePersistenceRequested(int id, string token)
    signal finished(bool valid)
    function updateOwnershipOutputs(outputs) {}
    function requestOwnership(mode, outputs) {
        handoffPhase = "acquire-skwd"
        Qt.callLater(() => acquirePersistenceRequested(42, "token"))
        return true
    }
    function acquisitionPersisted(id, token) {
        const valid = id === 42 && token === "token" && Config.saveStarted
        handoffPhase = "skwd"
        finished(valid)
    }
}
''')
            (base / 'shell.qml').write_text('''import QtQuick
import Quickshell
import qs.services
ShellRoot {
    Connections { target: SkwdWallpaper; function onFinished(valid) {
        if (valid) { console.log("PERSISTENCE_GATE_OK"); Qt.exit(0) } else Qt.exit(1)
    } }
    Component.onCompleted: { SkwdIntegration.start(); SkwdIntegration.requestMode("skwd") }
    Timer { interval: 4000; running: true; onTriggered: Qt.exit(1) }
}
''')
            env = {k: v for k, v in os.environ.items() if k not in ('WAYLAND_DISPLAY', 'NIRI_SOCKET', 'DBUS_SESSION_BUS_ADDRESS')}
            env.update(QT_QPA_PLATFORM='offscreen', QML_IMPORT_PATH=str(base), HOME=temp,
                       XDG_RUNTIME_DIR=str(base / 'runtime'), XDG_CONFIG_HOME=str(base / 'config'),
                       XDG_CACHE_HOME=str(base / 'cache'), TEST_CONFIG_PATH=str(config_file))
            result = subprocess.run([quickshell, '-p', str(base / 'shell.qml'), '--no-color'],
                                    env=env, capture_output=True, text=True, timeout=8)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PERSISTENCE_GATE_OK', result.stdout + result.stderr)
            self.assertEqual(json.loads(config_file.read_text())['iris']['skwd']['mode'], 'skwd')


if __name__ == '__main__':
    unittest.main()
