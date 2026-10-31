#!/usr/bin/env python3
"""Exercise the QML transport against an isolated local daemon stand-in."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SkwdTransportTest(unittest.TestCase):
    def test_handoff_over_socket_waits_for_both_outputs(self):
        quickshell = shutil.which("quickshell")
        if not quickshell:
            self.skipTest("quickshell is not installed")
        with tempfile.TemporaryDirectory(prefix="inir-skwd-handoff-socket-") as temp:
            base = Path(temp)
            module = base / "testbridge"
            module.mkdir()
            (base / "runtime").mkdir(mode=0o700)
            (module / "qmldir").write_text("module testbridge\nsingleton SkwdWallpaper 1.0 SkwdWallpaper.qml\nSkwdThemeCoordinator 1.0 SkwdThemeCoordinator.qml\nSkwdHandoff 1.0 SkwdHandoff.qml\n")
            for name in ("SkwdWallpaper.qml", "SkwdThemeCoordinator.qml", "SkwdHandoff.qml"):
                shutil.copy(ROOT / "services" / name, module / name)
            (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import testbridge
ShellRoot {
    property bool started: false
    property bool wentSkwd: false
    Connections {
        target: SkwdWallpaper
        function onIntegrationCompatibleChanged() {
            if (!started && SkwdWallpaper.integrationCompatible) {
                started = true
                if (SkwdWallpaper.requestOwnership("skwd", ["DP-1", "DP-2"])) { Qt.exit(1); return }
                SkwdWallpaper.nativeAdapterAvailable = true
                SkwdWallpaper.nativeBaselineVerified = true
                if (!SkwdWallpaper.requestOwnership("skwd", ["DP-1", "DP-2"])) Qt.exit(1)
            }
        }
        function onNativePauseRequested(id) { SkwdWallpaper.nativePauseFinished(id, true) }
        function onNativeResumeRequested(id) { SkwdWallpaper.nativeResumeFinished(id, true) }
        function onHandoffPhaseChanged() {
            if (SkwdWallpaper.handoffPhase === "skwd") {
                wentSkwd = true
                if (!SkwdWallpaper.applySelection("/tmp/selected.png", "DP-2", false)) Qt.exit(1)
            } else if (wentSkwd && SkwdWallpaper.handoffPhase === "native") {
                console.log("SKWD_HANDOFF_SOCKET_OK"); Qt.exit(0)
            }
        }
        function onRequestFinished(id, method, result, error) {
            if (method === "wall.apply") {
                if (error) { Qt.exit(1); return }
                SkwdWallpaper.requestOwnership("native", ["DP-1", "DP-2"])
            }
        }
        function onHandoffFailed(message) { console.log("HANDOFF_FAILED", message); Qt.exit(1) }
    }
    Component.onCompleted: {
        SkwdWallpaper.enabled = true
    }
    Timer { interval: 4000; running: true; onTriggered: Qt.exit(1) }
}
''')
            sockpath = base / "wall.sock"
            failures = []
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(sockpath))
                listener.listen(1)
                def server():
                    try:
                        conn, _ = listener.accept()
                        with conn, conn.makefile("rwb", buffering=0) as stream:
                            releases = 0
                            for line in stream:
                                req = json.loads(line)
                                method = req["method"]
                                if method == "integration.release":
                                    releases += 1
                                    result = {"released": True, "token": "token-" + str(releases)}
                                elif method == "integration.acquire":
                                    assert req["params"]["token"] == "token-1", req
                                    result = {"claimed": True, "rendered": False}
                                elif method == "wall.apply":
                                    assert req["params"]["path"] == "/tmp/selected.png", req
                                    assert req["params"]["output"] == "DP-2", req
                                    assert req["params"]["type"] == "static", req
                                    result = {"ok": True}
                                elif method == "integration.snapshot":
                                    result = {"available": True, "outputs": [
                                        {"output": "DP-1", "rendered": True},
                                        {"output": "DP-2", "rendered": True}]}
                                elif method == "subscribe": result = {"subscribed": True}
                                elif method == "status":
                                    result = {"protocol": {"name": "skwd-wall", "version": 1},
                                              "theme_authority": "inir", "pick_only": False,
                                              "renderer_released": False,
                                              "integration_features": ["inir-theme-authority-v1", "output-theme-source-v1", "renderer-handoff-v1", "rendered-snapshot-v1"]}
                                else: result = {"outputs": []}
                                stream.write((json.dumps({"id": req["id"], "result": result}) + "\n").encode())
                    except Exception as error:
                        failures.append(error)
                thread = threading.Thread(target=server, daemon=True)
                thread.start()
                env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QML_IMPORT_PATH=str(base),
                           XDG_RUNTIME_DIR=str(base / "runtime"), XDG_CONFIG_HOME=str(base / "config"),
                           XDG_CACHE_HOME=str(base / "cache"), SKWD_WALL_V2_SOCK=str(sockpath))
                proc = subprocess.run([quickshell, "-p", str(base / "shell.qml"), "--no-color"],
                                      env=env, text=True, capture_output=True, timeout=8)
                thread.join(timeout=2)
                self.assertFalse(failures, str(failures))
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("SKWD_HANDOFF_SOCKET_OK", proc.stdout + proc.stderr)

    def test_unresponsive_request_times_out(self):
        quickshell = shutil.which("quickshell")
        if not quickshell:
            self.skipTest("quickshell is not installed")
        with tempfile.TemporaryDirectory(prefix="inir-skwd-timeout-") as temp:
            base = Path(temp)
            module = base / "testbridge"
            module.mkdir()
            (base / "runtime").mkdir(mode=0o700)
            (module / "qmldir").write_text("module testbridge\nsingleton SkwdWallpaper 1.0 SkwdWallpaper.qml\nSkwdThemeCoordinator 1.0 SkwdThemeCoordinator.qml\nSkwdHandoff 1.0 SkwdHandoff.qml\n")
            shutil.copy(ROOT / "services/SkwdWallpaper.qml", module / "SkwdWallpaper.qml")
            shutil.copy(ROOT / "services/SkwdThemeCoordinator.qml", module / "SkwdThemeCoordinator.qml")
            shutil.copy(ROOT / "services/SkwdHandoff.qml", module / "SkwdHandoff.qml")
            (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import testbridge
ShellRoot {
    Connections {
        target: SkwdWallpaper
        function onConnectedChanged() {
            if (SkwdWallpaper.connected) SkwdWallpaper.send("integration.release", {})
        }
        function onRequestFinished(id, method, result, error) {
            if (method !== "integration.release") return
            if (error && String(error.message).includes("timed out")) {
                console.log("SKWD_TIMEOUT_OK"); Qt.exit(0)
            } else Qt.exit(1)
        }
    }
    Component.onCompleted: { SkwdWallpaper.requestTimeoutMs = 100; SkwdWallpaper.enabled = true }
    Timer { interval: 3000; running: true; onTriggered: Qt.exit(1) }
}
''')
            sockpath = base / "wall.sock"
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(sockpath))
                listener.listen(1)
                def server():
                    conn, _ = listener.accept()
                    with conn:
                        while conn.recv(4096):
                            pass
                thread = threading.Thread(target=server, daemon=True)
                thread.start()
                env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QML_IMPORT_PATH=str(base),
                           XDG_RUNTIME_DIR=str(base / "runtime"), XDG_CONFIG_HOME=str(base / "config"),
                           XDG_CACHE_HOME=str(base / "cache"), SKWD_WALL_V2_SOCK=str(sockpath))
                proc = subprocess.run([quickshell, "-p", str(base / "shell.qml"), "--no-color"],
                                      env=env, text=True, capture_output=True, timeout=8)
                thread.join(timeout=2)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("SKWD_TIMEOUT_OK", proc.stdout + proc.stderr)

    def test_snapshot_seeds_selected_monitor_without_overwriting_events(self):
        quickshell = shutil.which("quickshell")
        if not quickshell:
            self.skipTest("quickshell is not installed")
        with tempfile.TemporaryDirectory(prefix="inir-skwd-snapshot-") as temp:
            base = Path(temp)
            (base / "runtime").mkdir(mode=0o700)
            shutil.copy(ROOT / "services/SkwdThemeCoordinator.qml", base / "SkwdThemeCoordinator.qml")
            (base / "shell.qml").write_text('''import QtQuick
import Quickshell
ShellRoot {
    SkwdThemeCoordinator {
        id: coordinator
        enabled: true
        output: "DP-2"
        settleMs: 10
        onThemeSourceReady: (path, output, generation) => {
            if (path === "/tmp/new.png" && output === "DP-2" && generation === 4) {
                console.log("SKWD_SNAPSHOT_OK"); Qt.exit(0)
            } else { console.log("SKWD_SNAPSHOT_BAD", path, output, generation); Qt.exit(1) }
        }
    }
    Component.onCompleted: {
        coordinator.seed({available: true, outputs: [
            {output: "DP-1", theme_source: "/tmp/first.png", rendered: true},
            {output: "DP-2", theme_source: "/tmp/previous.png", rendered: true}]})
        coordinator.accept({output: "DP-2", theme_source: "/tmp/new.png", generation: 4, rendered: true})
        coordinator.seed({available: true, outputs: [
            {output: "DP-2", theme_source: "/tmp/stale.png", rendered: true}]})
    }
    Timer { interval: 3000; running: true; onTriggered: Qt.exit(1) }
}
''')
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=str(base / "runtime"),
                       XDG_CONFIG_HOME=str(base / "config"), XDG_CACHE_HOME=str(base / "cache"))
            proc = subprocess.run([quickshell, "-p", str(base / "shell.qml"), "--no-color"],
                                  env=env, text=True, capture_output=True, timeout=8)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("SKWD_SNAPSHOT_OK", proc.stdout + proc.stderr)

    def test_late_connection_subscribe_status_and_output(self):
        quickshell = shutil.which("quickshell")
        if not quickshell:
            self.skipTest("quickshell is not installed")
        with tempfile.TemporaryDirectory(prefix="inir-skwd-transport-") as temp:
            base = Path(temp)
            module = base / "testbridge"
            module.mkdir()
            (base / "runtime").mkdir(mode=0o700)
            (module / "qmldir").write_text("module testbridge\nsingleton SkwdWallpaper 1.0 SkwdWallpaper.qml\nSkwdThemeCoordinator 1.0 SkwdThemeCoordinator.qml\nSkwdHandoff 1.0 SkwdHandoff.qml\n")
            shutil.copy(ROOT / "services/SkwdWallpaper.qml", module / "SkwdWallpaper.qml")
            shutil.copy(ROOT / "services/SkwdThemeCoordinator.qml", module / "SkwdThemeCoordinator.qml")
            shutil.copy(ROOT / "services/SkwdHandoff.qml", module / "SkwdHandoff.qml")
            (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import testbridge
ShellRoot {
    Connections {
        target: SkwdWallpaper
        function onThemeSourceReady(path, output, generation) {
            if (!SkwdWallpaper.integrationEligible || SkwdWallpaper.themeAuthority !== "inir"
                    || SkwdWallpaper.outputs.length !== 1 || output !== "DP-1"
                    || path !== "/tmp/new.png" || generation !== 3) {
                console.log("SKWD_TRANSPORT_BAD_STATE")
                Qt.exit(1)
            } else { console.log("SKWD_TRANSPORT_OK"); Qt.exit(0) }
        }
    }
    Component.onCompleted: {
        SkwdWallpaper.themeOutput = "DP-1"
        SkwdWallpaper.colorSyncEnabled = true
        SkwdWallpaper.enabled = true
    }
    Timer { interval: 8000; running: true; onTriggered: { console.log("SKWD_TRANSPORT_TIMEOUT"); Qt.exit(1) } }
}
''')
            sockpath = base / "wall.sock"
            failures = []

            def server():
                try:
                    # Start after the first failed connection to exercise retry.
                    time.sleep(1)
                    with socket.socket(socket.AF_UNIX) as listener:
                        listener.bind(str(sockpath))
                        listener.listen(1)
                        listener.settimeout(6)
                        conn, _ = listener.accept()
                        with conn, conn.makefile("rwb", buffering=0) as stream:
                            for line in stream:
                                req = json.loads(line)
                                method = req["method"]
                                results = {
                                    "subscribe": {"subscribed": True},
                                    "status": {"protocol": {"name": "skwd-wall", "version": 1}, "theme_authority": "inir", "pick_only": False, "renderer_released": False, "integration_features": ["inir-theme-authority-v1", "output-theme-source-v1", "rendered-snapshot-v1"]},
                                    "wall.outputs": {"outputs": [{"name": "DP-1", "theme_source": "/tmp/a.png"}]},
                                    "integration.snapshot": {"available": True, "outputs": [{"output": "DP-1", "theme_source": "/tmp/stale-snapshot.png", "rendered": True}]},
                                }
                                response = {"id": req["id"], "result": results.get(method, {})}
                                stream.write((json.dumps(response) + "\n").encode())
                                if method == "wall.outputs":
                                    for data in [
                                        {"output": "DP-1", "theme_source": "/tmp/old.png", "generation": 1, "rendered": True},
                                        {"output": "DP-2", "theme_source": "/tmp/other.png", "generation": 2, "rendered": True},
                                        {"output": "DP-1", "theme_source": "/tmp/new.png", "generation": 3, "rendered": True},
                                        {"output": "DP-1", "theme_source": "/tmp/not-rendered.png", "generation": 4, "rendered": False},
                                        {"output": "DP-1", "theme_source": "/tmp/stale.png", "generation": 1, "rendered": True},
                                    ]:
                                        stream.write((json.dumps({"event": "skwd.wall.applied", "data": data}) + "\n").encode())
                                if method == "integration.snapshot":
                                    time.sleep(1)
                                    return
                except Exception as error:
                    failures.append(error)

            thread = threading.Thread(target=server, daemon=True)
            thread.start()
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QML_IMPORT_PATH=str(base),
                       XDG_RUNTIME_DIR=str(base / "runtime"), XDG_CONFIG_HOME=str(base / "config"),
                       XDG_CACHE_HOME=str(base / "cache"), SKWD_WALL_V2_SOCK=str(sockpath))
            proc = subprocess.run([quickshell, "-p", str(base / "shell.qml"), "--no-color"],
                                  env=env, text=True, capture_output=True, timeout=12)
            thread.join(timeout=7)
            self.assertFalse(failures, str(failures))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("SKWD_TRANSPORT_OK", proc.stdout + proc.stderr)
            self.assertNotIn("Unable to assign", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
