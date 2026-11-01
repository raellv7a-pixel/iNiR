#!/usr/bin/env python3
"""Exercise actual Config loading without a desktop or user files."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RealConfigTest(unittest.TestCase):
    def test_boot_ownership_follows_readable_configuration(self):
        quickshell = shutil.which('quickshell')
        if not quickshell:
            self.skipTest('quickshell is not installed')
        for mode in ('native', 'skwd', 'other_skwd', 'invalid'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix='inir-real-config-') as temp:
                base = Path(temp)
                common, bridge, runtime = base / 'qs/modules/common', base / 'bridge', base / 'run'
                for path in (common, bridge, runtime):
                    path.mkdir(parents=True, exist_ok=True)
                runtime.chmod(0o700)
                shutil.copy(ROOT / 'modules/common/Config.qml', common / 'Config.qml')
                (common / 'qmldir').write_text('module qs.modules.common\nsingleton Config 1.0 Config.qml\nsingleton Directories 1.0 Directories.qml\n')
                (common / 'Directories.qml').write_text('pragma Singleton\nimport QtQuick\nimport Quickshell\nQtObject { readonly property string shellConfigPath: Quickshell.env("TEST_CONFIG") }\n')
                for name in ('SkwdWallpaper.qml', 'SkwdThemeCoordinator.qml', 'SkwdHandoff.qml'):
                    shutil.copy(ROOT / 'services' / name, bridge / name)
                (bridge / 'qmldir').write_text('module bridge\nsingleton SkwdWallpaper 1.0 SkwdWallpaper.qml\nSkwdThemeCoordinator 1.0 SkwdThemeCoordinator.qml\nSkwdHandoff 1.0 SkwdHandoff.qml\n')
                family = 'ii' if mode == 'other_skwd' else 'iris'
                saved_mode = 'skwd' if mode == 'other_skwd' else mode
                config = json.dumps({'panelFamily': family, 'iris': {'skwd': {'mode': saved_mode}}}) if mode != 'invalid' else '{bad'
                (base / 'config.json').write_text(config)
                readable = 'false' if mode == 'invalid' else 'true'
                suppressed = 'false' if mode == 'native' else 'true'
                (base / 'shell.qml').write_text('''import QtQuick
import Quickshell
import qs.modules.common
import bridge
ShellRoot {
    Timer { interval: 50; repeat: true; running: true; onTriggered: {
        if (!Config.ready) return
        if (SkwdWallpaper.nativeRenderingSuppressed === ''' + suppressed + ''' && Config.loadedSafely === ''' + readable + ''') {
            console.log("REAL_CONFIG_OK"); Qt.exit(0)
        } else { console.log("REAL_CONFIG_BAD"); Qt.exit(1) }
    } }
    Timer { interval: 8500; running: true; onTriggered: Qt.exit(2) }
}
''')
                env = {k: v for k, v in os.environ.items() if k not in ('WAYLAND_DISPLAY', 'NIRI_SOCKET', 'DBUS_SESSION_BUS_ADDRESS')}
                env.update(HOME=temp, QT_QPA_PLATFORM='offscreen', QML_IMPORT_PATH=temp,
                           XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(base / 'xdg'),
                           XDG_CACHE_HOME=str(base / 'cache'), TEST_CONFIG=str(base / 'config.json'))
                result = subprocess.run([quickshell, '-p', str(base / 'shell.qml'), '--no-color'],
                                        env=env, capture_output=True, text=True, timeout=11)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('REAL_CONFIG_OK', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
