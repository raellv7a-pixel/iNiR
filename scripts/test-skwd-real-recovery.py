#!/usr/bin/env python3
"""Validate recovery using the local daemon and disposable configuration."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT.parent / 'skwd-deck/target/debug/skwd-walld'


class RealRecoveryTest(unittest.TestCase):
    def test_recovery_against_real_daemon(self):
        if not DAEMON.is_file():
            self.skipTest('the local debug daemon is unavailable')
        with tempfile.TemporaryDirectory(prefix='inir-real-recovery-') as temp:
            base = Path(temp)
            for path in ('config/inir', 'config/skwd-wall-v2', 'run', 'walls'):
                (base / path).mkdir(parents=True, exist_ok=True)
            (base / 'run').chmod(0o700)
            config = base / 'config/inir/config.json'
            original = {'iris': {'skwd': {'mode': 'skwd', 'themeOutput': 'DP-2'}}, 'keep': 42}
            config.write_text(json.dumps(original))
            (base / 'config/skwd-wall-v2/config.json').write_text(json.dumps({
                'theme': {'authority': 'inir'}, 'paper': {'engine': 'skwd-paper'},
                'paths': {'wallpaper': str(base / 'walls'), 'paperBin': '/nonexistent/paper'}}))
            env = {k: v for k, v in os.environ.items() if k not in (
                'WAYLAND_DISPLAY', 'NIRI_SOCKET', 'DBUS_SESSION_BUS_ADDRESS', 'SKWD_WALL_V2_SOCK',
                'SKWD_WALL_V2_CONFIG', 'SKWD_WALL_V2_CACHE', 'SKWD_PAPER_V2_SOCKET')}
            env.update(HOME=temp, XDG_CONFIG_HOME=str(base / 'config'), XDG_CACHE_HOME=str(base / 'cache'),
                       XDG_STATE_HOME=str(base / 'state'), XDG_RUNTIME_DIR=str(base / 'run'),
                       XDG_CURRENT_DESKTOP='isolated-test')
            daemon = subprocess.Popen([str(DAEMON), '--external-wallpaper-owner'], env=env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                sock = base / 'run/skwd-wall-v2/wall.sock'
                for _ in range(100):
                    if sock.exists(): break
                    if daemon.poll() is not None: self.fail('isolated daemon exited')
                    time.sleep(.05)
                else: self.fail('isolated daemon socket unavailable')
                result = subprocess.run(['python', str(ROOT / 'scripts/skwd-restore-native.py'), '--shell-stopped'],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                current = json.loads(config.read_text())
                self.assertEqual(current['iris']['skwd']['mode'], 'native')
                self.assertEqual(current['iris']['skwd']['themeOutput'], 'DP-2')
                self.assertEqual(current['keep'], 42)
                backups = list(config.parent.glob('config.json.before-skwd-restore-*'))
                self.assertEqual(len(backups), 1)
                self.assertEqual(json.loads(backups[0].read_text()), original)
            finally:
                daemon.terminate()
                try: daemon.wait(timeout=5)
                except subprocess.TimeoutExpired: daemon.kill(); daemon.wait()


if __name__ == '__main__':
    unittest.main()
