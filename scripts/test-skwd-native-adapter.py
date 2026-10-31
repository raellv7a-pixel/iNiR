#!/usr/bin/env python3
"""Test native Awww handoff in a separate runtime with no Wayland connection."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeAdapterTest(unittest.TestCase):
    def test_pause_and_resume_without_starting_a_wallpaper(self):
        quickshell = shutil.which("quickshell")
        if not quickshell:
            self.skipTest("quickshell is not installed")
        with tempfile.TemporaryDirectory(prefix="inir-native-adapter-") as temp:
            base = Path(temp)
            services = base / "qs/services"
            common = base / "qs/modules/common"
            functions = common / "functions"
            for path in (services, functions, base / "runtime"):
                path.mkdir(parents=True, exist_ok=True)
            (base / "runtime").chmod(0o700)
            shutil.copy(ROOT / "services/AwwwBackend.qml", services / "AwwwBackend.qml")
            (services / "qmldir").write_text('''module qs.services
singleton AwwwBackend 1.0 AwwwBackend.qml
singleton SkwdWallpaper 1.0 SkwdWallpaper.qml
singleton Wallpapers 1.0 Wallpapers.qml
singleton WallpaperListener 1.0 WallpaperListener.qml
singleton Appearance 1.0 Appearance.qml
''')
            (common / "qmldir").write_text("module qs.modules.common\nsingleton Config 1.0 Config.qml\n")
            (functions / "qmldir").write_text("module qs.modules.common.functions\nsingleton FileUtils 1.0 FileUtils.qml\nsingleton StringUtils 1.0 StringUtils.qml\n")
            (common / "Config.qml").write_text('''pragma Singleton
import QtQuick
QtObject { property var options: ({background: {backend: {provider: "awww"}}, panelFamily: "iris"}) }
''')
            (services / "SkwdWallpaper.qml").write_text('''pragma Singleton
import QtQuick
QtObject {
    property bool nativeRenderingSuppressed: false
    property bool nativeBackdropStopped: true
    signal nativePauseRequested(int id)
    signal nativeResumeRequested(int id)
    signal pauseDone(int id, bool ok)
    signal resumeDone(int id, bool ok)
    function nativePauseFinished(id, ok, message) { pauseDone(id, ok) }
    function nativeResumeFinished(id, ok, message) { resumeDone(id, ok) }
}
''')
            (services / "Wallpapers.qml").write_text('''pragma Singleton
import QtQuick
QtObject { property bool _applyInProgress: false }
''')
            (services / "WallpaperListener.qml").write_text('''pragma Singleton
import QtQuick
QtObject {
    property bool multiMonitorEnabled: false
    property var effectivePerMonitor: ({})
    function getMonitorName(screen) { return "" }
    function isVideoPath(path) { return false }
    function isGifPath(path) { return false }
}
''')
            (services / "Appearance.qml").write_text('''pragma Singleton
import QtQuick
QtObject { property bool animationsEnabled: false }
''')
            (functions / "FileUtils.qml").write_text('''pragma Singleton
import QtQuick
QtObject { function trimFileProtocol(path) { return path } }
''')
            (functions / "StringUtils.qml").write_text('''pragma Singleton
import QtQuick
QtObject { function shellSingleQuoteEscape(value) { return value } }
''')
            (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import qs.services
ShellRoot {
    Connections {
        target: SkwdWallpaper
        function onPauseDone(id, ok) {
            if (id !== 41 || !ok || !SkwdWallpaper.nativeRenderingSuppressed) { Qt.exit(1); return }
            SkwdWallpaper.nativeResumeRequested(42)
        }
        function onResumeDone(id, ok) {
            if (id === 42 && ok && !SkwdWallpaper.nativeRenderingSuppressed) {
                console.log("NATIVE_ADAPTER_OK"); Qt.exit(0)
            } else Qt.exit(1)
        }
    }
    Component.onCompleted: { let backend = AwwwBackend; SkwdWallpaper.nativePauseRequested(41) }
    Timer { interval: 4000; running: true; onTriggered: Qt.exit(1) }
}
''')
            env = {k: v for k, v in os.environ.items() if k not in (
                "WAYLAND_DISPLAY", "NIRI_SOCKET", "DBUS_SESSION_BUS_ADDRESS", "SWAYSOCK")}
            env.update(QT_QPA_PLATFORM="offscreen", QML_IMPORT_PATH=str(base), HOME=str(base),
                       XDG_RUNTIME_DIR=str(base / "runtime"), XDG_CONFIG_HOME=str(base / "config"),
                       XDG_CACHE_HOME=str(base / "cache"), XDG_STATE_HOME=str(base / "state"),
                       WAYLAND_DISPLAY="isolated-nonexistent-wayland")
            proc = subprocess.run([quickshell, "-p", str(base / "shell.qml"), "--no-color"], env=env,
                                  text=True, capture_output=True, timeout=8)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("NATIVE_ADAPTER_OK", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
