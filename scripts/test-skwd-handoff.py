#!/usr/bin/env python3
"""Exercise the ownership coordinator with offscreen, isolated QML adapters."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HandoffTest(unittest.TestCase):
    def test_timeout_during_acquire_requires_fresh_release(self):
        quickshell = shutil.which("quickshell")
        if not quickshell:
            self.skipTest("quickshell is not installed")
        with tempfile.TemporaryDirectory(prefix="inir-handoff-timeout-") as temp:
            base = Path(temp)
            (base / "runtime").mkdir(mode=0o700)
            shutil.copy(ROOT / "services/SkwdHandoff.qml", base / "SkwdHandoff.qml")
            (base / "shell.qml").write_text('''import QtQuick
import Quickshell
ShellRoot {
    id: root
    property int releases: 0
    SkwdHandoff {
        id: handoff
        timeoutMs: 60
        expectedOutputs: ["DP-1", "DP-2"]
        onReleaseRequested: id => {
            root.releases++
            handoff.complete(id, handoff.phase, true, {token: "token-" + root.releases})
        }
        onPauseNativeRequested: id => handoff.complete(id, "pause-native", true, {})
        onAcquireRequested: (id, token) => {
            // Simulate a late success after the request has timed out.
            late.operation = id
            late.start()
        }
        onResumeNativeRequested: id => {
            if (root.releases !== 2) { console.log("RESUME_BEFORE_RELEASE"); Qt.exit(1); return }
            handoff.complete(id, "resume-native", true, {})
            finish.start()
        }
    }
    Timer { id: late; property int operation: 0; interval: 90
        onTriggered: handoff.complete(operation, "acquire-skwd", true, {}) }
    Timer { id: finish; interval: 100
        onTriggered: {
            if (handoff.phase === "native" && root.releases === 2) { console.log("TIMEOUT_ROLLBACK_OK"); Qt.exit(0) }
            else { console.log("STALE_COMPLETION_CHANGED_STATE"); Qt.exit(1) }
        }
    }
    Component.onCompleted: handoff.request("skwd")
    Timer { interval: 3000; running: true; onTriggered: Qt.exit(1) }
}
''')
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=str(base / "runtime"),
                       XDG_CONFIG_HOME=str(base / "config"), XDG_CACHE_HOME=str(base / "cache"))
            proc = subprocess.run([quickshell, "-p", str(base / "shell.qml"), "--no-color"], env=env,
                                  text=True, capture_output=True, timeout=8)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("TIMEOUT_ROLLBACK_OK", proc.stdout + proc.stderr)

    def test_two_outputs_and_failed_release(self):
        quickshell = shutil.which("quickshell")
        if not quickshell:
            self.skipTest("quickshell is not installed")
        with tempfile.TemporaryDirectory(prefix="inir-handoff-") as temp:
            base = Path(temp)
            (base / "runtime").mkdir(mode=0o700)
            shutil.copy(ROOT / "services/SkwdHandoff.qml", base / "SkwdHandoff.qml")
            (base / "shell.qml").write_text('''import QtQuick
import Quickshell
ShellRoot {
    property int releaseCount: 0
    property int resumes: 0
    SkwdHandoff {
        id: handoff
        expectedOutputs: ["DP-1", "DP-2"]
        timeoutMs: 1000
        onReleaseRequested: id => {
            root.releaseCount++
            const action = handoff.phase
            if (root.releaseCount === 2) handoff.complete(id, action, false, {message: "lost connection"})
            else handoff.complete(id, action, true, {token: "release-" + root.releaseCount})
        }
        onPauseNativeRequested: id => handoff.complete(id, "pause-native", true, {})
        onAcquireRequested: (id, token) => {
            if (token !== "release-1") { console.log("BAD_TOKEN"); Qt.exit(1); return }
            handoff.complete(id, "acquire-skwd", true, {})
            handoff.confirmReady("DP-1")
            if (handoff.phase !== "waiting-ready") { console.log("BAD_PARTIAL"); Qt.exit(1); return }
            handoff.confirmReady("DP-2")
            if (handoff.phase !== "skwd") { console.log("BAD_READY"); Qt.exit(1); return }
            handoff.request("native")
        }
        onResumeNativeRequested: id => {
            root.resumes++
            if (root.releaseCount !== 3) { console.log("BAD_RESUME"); Qt.exit(1); return }
            handoff.complete(id, "resume-native", true, {})
            if (handoff.phase === "native") { console.log("HANDOFF_OK"); Qt.exit(0) }
        }
        onPhaseChanged: {
            if (handoff.phase === "blocked") {
                if (root.resumes !== 0) { console.log("BAD_BLOCK"); Qt.exit(1); return }
                handoff.request("native")
            }
        }
    }
    id: root
    Component.onCompleted: handoff.request("skwd")
    Timer { interval: 3000; running: true; onTriggered: { console.log("HANDOFF_TIMEOUT"); Qt.exit(1) } }
}
''')
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=str(base / "runtime"),
                       XDG_CONFIG_HOME=str(base / "config"), XDG_CACHE_HOME=str(base / "cache"))
            proc = subprocess.run([quickshell, "-p", str(base / "shell.qml"), "--no-color"], env=env,
                                  text=True, capture_output=True, timeout=8)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("HANDOFF_OK", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
