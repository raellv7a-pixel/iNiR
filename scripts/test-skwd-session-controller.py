#!/usr/bin/env python3
"""Exercise session preference transitions without a running desktop."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SessionControllerTest(unittest.TestCase):
    def test_other_family_restores_native_after_confirmed_release(self):
        quickshell = shutil.which("quickshell")
        if not quickshell:
            self.skipTest("quickshell is not installed")
        with tempfile.TemporaryDirectory(prefix="inir-skwd-family-") as temp:
            base = Path(temp)
            services, common = base / "qs/services", base / "qs/modules/common"
            for path in (services, common, base / "runtime"):
                path.mkdir(parents=True, exist_ok=True)
            (base / "runtime").chmod(0o700)
            shutil.copy(ROOT / "services/SkwdIntegration.qml", services / "SkwdIntegration.qml")
            (base / "qs/qmldir").write_text("module qs\nsingleton GlobalStates 1.0 GlobalStates.qml\n")
            (base / "qs/GlobalStates.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property bool wallpaperSelectorOpen: false; property string wallpaperSelectorTargetMonitor: "" }\n')
            (common / "qmldir").write_text("module qs.modules.common\nsingleton Config 1.0 Config.qml\n")
            (common / "Config.qml").write_text('''pragma Singleton
import QtQuick
QtObject {
    property bool ready: true
    property bool loadedSafely: true
    property string filePath: ""
    property var options: ({panelFamily: "ii", background: {backend: {provider: "awww"}}, iris: {skwd: {mode: "skwd", themeOutput: "DP-1"}}})
    function setNestedValue(path, value) { let v = JSON.parse(JSON.stringify(options)); v.iris.skwd.mode = value; options = v }
}
''')
            (services / "qmldir").write_text('module qs.services\nsingleton SkwdIntegration 1.0 SkwdIntegration.qml\nsingleton SkwdWallpaper 1.0 SkwdWallpaper.qml\nsingleton AwwwBackend 1.0 AwwwBackend.qml\n')
            (services / "AwwwBackend.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { readonly property string provider: "awww" }\n')
            (services / "SkwdWallpaper.qml").write_text('''pragma Singleton
import QtQuick
import qs.modules.common
QtObject {
    property bool nativeAdapterAvailable: false
    property bool nativeBaselineVerified: false
    property bool nativeRenderingSuppressed: true
    property bool enabled: false
    property bool connected: true
    property bool colorSyncEnabled: false
    property bool integrationCompatible: true
    property bool integrationEligible: true
    property string themeAuthority: "inir"
    property bool pickOnly: false
    property string themeOutput: ""
    property string handoffPhase: "blocked"
    signal handoffFailed(string message)
    signal disconnected()
    signal acquirePersistenceRequested(int id, string token)
    signal requestFinished(int id, string method, var result, var error)
    function acquisitionPersisted(id, token) {}
    function send(method, params) { return 0 }
    function markRendererUnhealthy() {}
    function updateOwnershipOutputs(outputs) {}
    function requestOwnership(mode, outputs) {
        if (mode !== "native" || !nativeAdapterAvailable || !nativeBaselineVerified) return false
        handoffPhase = "release-for-native"
        Qt.callLater(() => { Config.setNestedValue("iris.skwd.mode", "native"); nativeRenderingSuppressed = false; handoffPhase = "native" })
        return true
    }
}
''')
            (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import qs.services
import qs.modules.common
ShellRoot {
    Connections { target: SkwdWallpaper; function onHandoffPhaseChanged() {
        if (SkwdWallpaper.handoffPhase === "native") verify.start()
    } }
    Timer { id: verify; interval: 10; onTriggered: {
        if (!SkwdWallpaper.nativeRenderingSuppressed && Config.options.iris.skwd.mode === "native") {
            console.log("OTHER_FAMILY_RECOVERED"); Qt.exit(0)
        } else Qt.exit(1)
    } }
    Component.onCompleted: SkwdIntegration.start()
    Timer { interval: 3000; running: true; onTriggered: Qt.exit(1) }
}
''')
            env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "NIRI_SOCKET", "DBUS_SESSION_BUS_ADDRESS")}
            env.update(QT_QPA_PLATFORM="offscreen", QML_IMPORT_PATH=str(base), HOME=temp,
                       XDG_RUNTIME_DIR=str(base / "runtime"), XDG_CONFIG_HOME=str(base / "config"),
                       XDG_CACHE_HOME=str(base / "cache"))
            result = subprocess.run([quickshell, "-p", str(base / "shell.qml"), "--no-color"], env=env,
                                    text=True, capture_output=True, timeout=8)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OTHER_FAMILY_RECOVERED", result.stdout + result.stderr)

    def test_native_activation_and_boot_recovery(self):
        quickshell = shutil.which("quickshell")
        if not quickshell:
            self.skipTest("quickshell is not installed")
        for initial in ("native", "skwd"):
            with self.subTest(initial=initial), tempfile.TemporaryDirectory(prefix="inir-skwd-session-") as temp:
                base = Path(temp)
                services = base / "qs/services"
                common = base / "qs/modules/common"
                for path in (services, common, base / "runtime"):
                    path.mkdir(parents=True, exist_ok=True)
                (base / "runtime").chmod(0o700)
                shutil.copy(ROOT / "services/SkwdIntegration.qml", services / "SkwdIntegration.qml")
                (base / "qs/qmldir").write_text("module qs\nsingleton GlobalStates 1.0 GlobalStates.qml\n")
                (base / "qs/GlobalStates.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property bool wallpaperSelectorOpen: false; property string wallpaperSelectorTargetMonitor: "" }\n')
                (common / "qmldir").write_text("module qs.modules.common\nsingleton Config 1.0 Config.qml\n")
                (common / "Config.qml").write_text('''pragma Singleton
import QtQuick
QtObject {
    property bool ready: true
    property bool loadedSafely: true
    property string filePath: ""
    property var options: ({panelFamily: "iris", background: {backend: {provider: "awww"}}, iris: {skwd: {mode: "''' + initial + '''", themeOutput: "DP-1"}}})
    function setNestedValue(path, value) { let v = JSON.parse(JSON.stringify(options)); v.iris.skwd.mode = value; options = v }
}
''')
                (services / "qmldir").write_text('''module qs.services
singleton SkwdIntegration 1.0 SkwdIntegration.qml
singleton SkwdWallpaper 1.0 SkwdWallpaper.qml
singleton AwwwBackend 1.0 AwwwBackend.qml
''')
                (services / "AwwwBackend.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { readonly property string provider: "awww" }\n')
                (services / "SkwdWallpaper.qml").write_text('''pragma Singleton
import QtQuick
QtObject {
    id: root
    property bool nativeAdapterAvailable: false
    property bool nativeBaselineVerified: false
    property bool nativeRenderingSuppressed: ''' + ("true" if initial == "skwd" else "false") + '''
    property bool enabled: false
    property bool connected: true
    property bool colorSyncEnabled: false
    property bool integrationCompatible: true
    property bool integrationEligible: true
    property string themeAuthority: "inir"
    property bool pickOnly: false
    property string themeOutput: ""
    property string handoffPhase: "''' + ("blocked" if initial == "skwd" else "native") + '''"
    property int acquisitions: 0
    property int healthRequests: 0
    property var fallbackApplied: []
    signal handoffFailed(string message)
    signal disconnected()
    signal requestFinished(int id, string method, var result, var error)
    function send(method, params) {
        if (method === "wall.apply") { fallbackApplied = fallbackApplied.concat([params]); return 999 }
        const id = 100 + ++healthRequests
        Qt.callLater(() => requestFinished(id, method, {available: true, outputs: []}, null))
        return id
    }
    function markRendererUnhealthy() { handoffPhase = "blocked" }
    signal acquirePersistenceRequested(int id, string token)
    function acquisitionPersisted(id, token) {}
    function updateOwnershipOutputs(outputs) {}
    function requestOwnership(mode, outputs) {
        if (!nativeAdapterAvailable || !nativeBaselineVerified) return false
        if (mode === "skwd") {
            acquisitions++
            handoffPhase = "release-for-skwd"
            Qt.callLater(() => { nativeRenderingSuppressed = true; handoffPhase = "skwd" })
        } else {
            handoffPhase = "release-for-native"
            Qt.callLater(() => { nativeRenderingSuppressed = false; handoffPhase = "native" })
        }
        return true
    }
}
''')
                (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import qs.services
import qs.modules.common
ShellRoot {
    property bool activated: false
    property bool testedDisconnect: false
    Connections {
        target: SkwdWallpaper
        function onHandoffPhaseChanged() {
            if (SkwdWallpaper.handoffPhase === "skwd") {
                activated = true
                if (!testedDisconnect) { testedDisconnect = true; simulateDisconnect.start() }
                else verifyStart.start()
            } else if (activated && SkwdWallpaper.handoffPhase === "native") verifyEnd.start()
        }
    }
    Timer { id: simulateDisconnect; interval: 10; onTriggered: {
        SkwdWallpaper.connected = false
        SkwdWallpaper.integrationCompatible = false
        SkwdWallpaper.handoffPhase = "blocked"
        SkwdWallpaper.disconnected()
        reconnect.start()
    } }
    Timer { id: reconnect; interval: 10; onTriggered: {
        SkwdWallpaper.connected = true
        SkwdWallpaper.integrationCompatible = true
    } }
    Timer { id: verifyStart; interval: 5; onTriggered: {
        if (Config.options.iris.skwd.mode !== "skwd" || !SkwdWallpaper.nativeRenderingSuppressed) { Qt.exit(1); return }
        if (SkwdWallpaper.acquisitions === 2) {
            SkwdIntegration.monitorNames = ["DP-1", "DP-2"]
            SkwdIntegration.healthIntervalMs = 20
            return
        }
        if (SkwdWallpaper.acquisitions !== 3 || SkwdWallpaper.healthRequests < 3) { Qt.exit(1); return }
        SkwdIntegration.requestMode("native")
    } }
    Timer { id: verifyEnd; interval: 5; onTriggered: {
        if (Config.options.iris.skwd.mode !== "native" || SkwdWallpaper.nativeRenderingSuppressed) { Qt.exit(1); return }
        console.log("SESSION_CONTROLLER_OK"); Qt.exit(0)
    } }
    Component.onCompleted: {
        SkwdIntegration.start()
        if (Config.options.iris.skwd.mode === "native") {
            SkwdIntegration.monitorNames = ["DP-1", "DP-2"]
            let options = JSON.parse(JSON.stringify(Config.options))
            options.background.wallpaperPath = "/tmp/native.png"
            Config.options = options
            SkwdWallpaper.handoffPhase = "waiting-ready"
            SkwdIntegration.seedMissingOutputs({outputs: [{name: "DP-1", path: "/tmp/saved.png"}, {name: "DP-2", path: ""}]})
            if (SkwdWallpaper.fallbackApplied.length !== 1 || SkwdWallpaper.fallbackApplied[0].output !== "DP-2"
                    || SkwdWallpaper.fallbackApplied[0].path !== "/tmp/native.png") { Qt.exit(1); return }
            SkwdWallpaper.handoffPhase = "native"
            SkwdIntegration.requestMode("skwd")
        }
    }
    Timer { interval: 3000; running: true; onTriggered: Qt.exit(1) }
}
''')
                env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "NIRI_SOCKET", "DBUS_SESSION_BUS_ADDRESS")}
                env.update(QT_QPA_PLATFORM="offscreen", QML_IMPORT_PATH=str(base), HOME=str(base),
                           XDG_RUNTIME_DIR=str(base / "runtime"), XDG_CONFIG_HOME=str(base / "config"),
                           XDG_CACHE_HOME=str(base / "cache"))
                proc = subprocess.run([quickshell, "-p", str(base / "shell.qml"), "--no-color"], env=env,
                                      text=True, capture_output=True, timeout=8)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("SESSION_CONTROLLER_OK", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
