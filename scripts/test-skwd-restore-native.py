#!/usr/bin/env python3
"""Exercise the recovery utility against disposable config and Unix sockets."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

SCRIPT = Path(__file__).resolve().with_name('skwd-restore-native.py')


class RecoveryTest(unittest.TestCase):
    def run_case(self, released):
        with tempfile.TemporaryDirectory(prefix='inir-recovery-test-') as temp:
            base = Path(temp)
            config_dir = base / 'config/inir'
            config_dir.mkdir(parents=True)
            config = config_dir / 'config.json'
            original = {'iris': {'skwd': {'mode': 'skwd', 'themeOutput': 'DP-2'}}, 'other': {'keep': True}}
            config.write_text(json.dumps(original))
            sockpath = base / 'daemon.sock'
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(sockpath))
                listener.listen(1)
                def serve():
                    conn, _ = listener.accept()
                    with conn:
                        request = json.loads(conn.makefile('rb').readline())
                        assert request['method'] == 'integration.release'
                        response = {'id': 1, 'result': {'released': True}} if released else {'id': 1, 'error': {'message': 'failed'}}
                        conn.sendall((json.dumps(response) + '\n').encode())
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                env = dict(os.environ, HOME=temp, XDG_CONFIG_HOME=str(base / 'config'), SKWD_WALL_V2_SOCK=str(sockpath))
                result = subprocess.run(['python', str(SCRIPT), '--shell-stopped'], env=env, capture_output=True, text=True, timeout=8)
                thread.join(timeout=2)
            after = json.loads(config.read_text())
            backups = list(config_dir.glob('config.json.before-skwd-restore-*'))
            if released:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(after['iris']['skwd']['mode'], 'native')
                self.assertEqual(after['iris']['skwd']['themeOutput'], 'DP-2')
                self.assertEqual(after['other'], original['other'])
                self.assertEqual(len(backups), 1)
                self.assertEqual(json.loads(backups[0].read_text()), original)
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(after, original)
                self.assertFalse(backups)

    def test_confirmed_release(self):
        self.run_case(True)

    def test_rejected_release_preserves_config(self):
        self.run_case(False)

    def test_requires_shell_stopped_confirmation(self):
        result = subprocess.run(['python', str(SCRIPT)], capture_output=True, text=True, timeout=8)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
