#!/usr/bin/env python3
"""Exercise QML ownership against the real daemon and a disposable Paper stub."""
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
DECK = ROOT.parent / 'skwd-deck'


class DaemonQmlTest(unittest.TestCase):
    def test_two_output_handoff_and_native_return(self):
        quickshell = shutil.which('quickshell')
        daemon = DECK / 'target/debug/skwd-walld'
        if not quickshell or not daemon.is_file():
            self.skipTest('quickshell or the local debug daemon is unavailable')
        with tempfile.TemporaryDirectory(prefix='inir-skwd-e2e-') as temp:
            base = Path(temp)
            services, common = base / 'qml/qs/services', base / 'qml/qs/modules/common'
            for path in (services, common, base / 'run', base / 'config/skwd-wall-v2', base / 'walls'):
                path.mkdir(parents=True, exist_ok=True)
            (base / 'run').chmod(0o700)
            image = base / 'walls/wall.png'
            image.write_bytes(b'fixture')
            config = base / 'inir.json'
            config.write_text(json.dumps({'panelFamily': 'iris', 'iris': {'skwd': {'mode': 'native', 'themeOutput': 'DP-1'}}}))
            (base / 'config/skwd-wall-v2/config.json').write_text(json.dumps({
                'theme': {'authority': 'inir'}, 'paper': {'engine': 'skwd-paper'},
                'paths': {'wallpaper': str(base / 'walls'), 'paperBin': '/nonexistent/paper'},
                'general': {'notifyOnWallpaperChange': False}}))
            (base / 'qml/qs/qmldir').write_text('module qs\nsingleton GlobalStates 1.0 GlobalStates.qml\n')
            (base / 'qml/qs/GlobalStates.qml').write_text('pragma Singleton\nimport QtQuick\nQtObject { property bool wallpaperSelectorOpen: false; property string wallpaperSelectorTargetMonitor: "" }\n')
            (common / 'qmldir').write_text('module qs.modules.common\nsingleton Config 1.0 Config.qml\nsingleton Directories 1.0 Directories.qml\n')
            shutil.copy(ROOT / 'modules/common/Config.qml', common / 'Config.qml')
            (common / 'Directories.qml').write_text('pragma Singleton\nimport QtQuick\nimport Quickshell\nQtObject { readonly property string shellConfigPath: Quickshell.env("TEST_INIR_CONFIG") }\n')
            (services / 'qmldir').write_text('''module qs.services
singleton SkwdIntegration 1.0 SkwdIntegration.qml
singleton SkwdWallpaper 1.0 SkwdWallpaper.qml
singleton AwwwBackend 1.0 AwwwBackend.qml
SkwdThemeCoordinator 1.0 SkwdThemeCoordinator.qml
SkwdHandoff 1.0 SkwdHandoff.qml
''')
            for name in ('SkwdIntegration.qml', 'SkwdWallpaper.qml', 'SkwdThemeCoordinator.qml', 'SkwdHandoff.qml'):
                shutil.copy(ROOT / 'services' / name, services / name)
            (services / 'AwwwBackend.qml').write_text('''pragma Singleton
import QtQuick
import qs.services
import qs.modules.common
QtObject {
    readonly property string provider: "awww"
    property Connections adapter: Connections {
        target: SkwdWallpaper
        function onNativePauseRequested(id) { SkwdWallpaper.nativeRenderingSuppressed = true; SkwdWallpaper.nativePauseFinished(id, true) }
        function onNativeResumeRequested(id) {
            Config.setNestedValue("iris.skwd.mode", "native")
            SkwdWallpaper.nativeRenderingSuppressed = false
            SkwdWallpaper.nativeResumeFinished(id, true)
        }
    }
}
''')
            (base / 'shell.qml').write_text('''import QtQuick
import Quickshell
import qs.services
import qs.modules.common
ShellRoot {
    property bool requested: false
    property bool integrated: false
    Connections { target: Config; function onReadyChanged() { attempt.start() } }
    Connections { target: SkwdWallpaper
        function onIntegrationCompatibleChanged() { attempt.start() }
        function onHandoffFailed(message) { console.log("E2E_HANDOFF_FAILED", message); Qt.exit(1) }
        function onHandoffPhaseChanged() {
            if (SkwdWallpaper.handoffPhase === "skwd") { integrated = true; verify.start() }
            else if (integrated && SkwdWallpaper.handoffPhase === "native") finish.start()
        }
    }
    Timer { id: attempt; interval: 10; onTriggered: {
        if (requested || !Config.ready || !Config.loadedSafely || !SkwdWallpaper.integrationCompatible) return
        SkwdIntegration.start()
        SkwdIntegration.monitorNames = ["DP-1", "DP-2"]
        requested = true
        if (!SkwdIntegration.requestMode("skwd")) Qt.exit(1)
    } }
    Timer { id: verify; interval: 20; onTriggered: {
        if (Config.options.iris.skwd.mode !== "skwd" || !SkwdWallpaper.nativeRenderingSuppressed) { Qt.exit(1); return }
        SkwdIntegration.requestMode("native")
    } }
    Timer { id: finish; interval: 30; onTriggered: {
        if (Config.options.iris.skwd.mode !== "native" || SkwdWallpaper.nativeRenderingSuppressed) { Qt.exit(1); return }
        console.log("SKWD_REAL_DAEMON_QML_OK"); Qt.exit(0)
    } }
    Component.onCompleted: SkwdWallpaper.enabled = true
    Timer { interval: 12000; running: true; onTriggered: { console.log("E2E_TIMEOUT"); Qt.exit(1) } }
}
''')
            env = {k: v for k, v in os.environ.items() if k not in (
                'WAYLAND_DISPLAY', 'NIRI_SOCKET', 'DBUS_SESSION_BUS_ADDRESS', 'SKWD_WALL_V2_SOCK',
                'SKWD_WALL_V2_CONFIG', 'SKWD_WALL_V2_CACHE')}
            paper_socket = base / 'run/paper.sock'
            env.update(HOME=temp, XDG_CONFIG_HOME=str(base / 'config'), XDG_CACHE_HOME=str(base / 'cache'),
                       XDG_STATE_HOME=str(base / 'state'), XDG_RUNTIME_DIR=str(base / 'run'),
                       XDG_CURRENT_DESKTOP='isolated-test', SKWD_FAKE_OUTPUTS='DP-1,DP-2',
                       SKWD_PAPER_V2_SOCKET=str(paper_socket), QT_QPA_PLATFORM='offscreen',
                       QML_IMPORT_PATH=str(base / 'qml'), TEST_INIR_CONFIG=str(config))
            capabilities = json.loads((DECK / 'crates/skwd-wall-core/tests/golden/paper-capabilities-response-v1.jsonl').read_text())['result']
            listener = socket.socket(socket.AF_UNIX)
            listener.bind(str(paper_socket))
            listener.listen(8)
            listener.settimeout(.2)
            stop = threading.Event()
            failures = []
            def serve_paper():
                while not stop.is_set():
                    try:
                        conn, _ = listener.accept()
                    except socket.timeout:
                        continue
                    except OSError:
                        return
                    try:
                        with conn, conn.makefile('rwb', buffering=0) as stream:
                            request = json.loads(stream.readline())
                            method = request['method']
                            if method == 'paper.stop': result = {'stopped': 0}
                            elif method == 'paper.capabilities': result = capabilities
                            elif method == 'paper.status':
                                def assignment(output):
                                    return {'outputs': [output], 'source': {'kind': 'static', 'path': str(image)},
                                            'fill_mode': 'fill', 'mute': True, 'volume': 80,
                                            'layer': 'background', 'generation': 7, 'ready': True}
                                result = {'paused': False, 'assignments': [assignment('DP-1'), assignment('DP-2')]}
                            else: raise AssertionError(request)
                            stream.write((json.dumps({'id': request['id'], 'result': result}) + '\n').encode())
                    except Exception as error:
                        failures.append(error)
            thread = threading.Thread(target=serve_paper, daemon=True)
            thread.start()
            process = subprocess.Popen([str(daemon), '--external-wallpaper-owner'], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                sockpath = base / 'run/skwd-wall-v2/wall.sock'
                for _ in range(100):
                    if sockpath.exists(): break
                    if process.poll() is not None: self.fail('isolated daemon exited')
                    time.sleep(.05)
                else: self.fail('isolated daemon socket not ready')
                result = subprocess.run([quickshell, '-p', str(base / 'shell.qml'), '--no-color'],
                                        env=env, capture_output=True, text=True, timeout=16)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('SKWD_REAL_DAEMON_QML_OK', result.stdout + result.stderr)
                self.assertFalse(failures, str(failures))
            finally:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                stop.set()
                listener.close()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
