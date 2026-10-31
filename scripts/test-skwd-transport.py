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
    def test_late_connection_subscribe_status_and_output(self):
        quickshell = shutil.which("quickshell")
        if not quickshell:
            self.skipTest("quickshell is not installed")
        with tempfile.TemporaryDirectory(prefix="inir-skwd-transport-") as temp:
            base = Path(temp)
            module = base / "testbridge"
            module.mkdir()
            (base / "runtime").mkdir(mode=0o700)
            (module / "qmldir").write_text("module testbridge\nsingleton SkwdWallpaper 1.0 SkwdWallpaper.qml\n")
            shutil.copy(ROOT / "services/SkwdWallpaper.qml", module / "SkwdWallpaper.qml")
            (base / "shell.qml").write_text('''import QtQuick
import Quickshell
import testbridge
ShellRoot {
    Connections {
        target: SkwdWallpaper
        function onWallpaperApplied(data) {
            if (!SkwdWallpaper.integrationEligible || SkwdWallpaper.themeAuthority !== "inir"
                    || SkwdWallpaper.outputs.length !== 1 || data.output !== "DP-1") {
                console.log("SKWD_TRANSPORT_BAD_STATE")
                Qt.exit(1)
            } else { console.log("SKWD_TRANSPORT_OK"); Qt.exit(0) }
        }
    }
    Component.onCompleted: SkwdWallpaper.enabled = true
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
                                    "status": {"protocol": {"name": "skwd-wall", "version": 1}, "theme_authority": "inir", "pick_only": False, "integration_features": ["inir-theme-authority-v1", "output-theme-source-v1"]},
                                    "wall.outputs": {"outputs": [{"name": "DP-1", "theme_source": "/tmp/a.png"}]},
                                }
                                response = {"id": req["id"], "result": results.get(method, {})}
                                stream.write((json.dumps(response) + "\n").encode())
                                if method == "wall.outputs":
                                    event = {"event": "skwd.wall.applied", "data": {"output": "DP-1", "theme_source": "/tmp/a.png"}}
                                    stream.write((json.dumps(event) + "\n").encode())
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
