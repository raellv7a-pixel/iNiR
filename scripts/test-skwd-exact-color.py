#!/usr/bin/env python3
"""Run the real colour script with disposable configuration and command stubs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExactColorSourceTest(unittest.TestCase):
    def test_external_colour_neither_switches_nor_stops_a_renderer(self):
        if not shutil.which("jq"):
            self.skipTest("jq is not installed")
        with tempfile.TemporaryDirectory(prefix="inir-skwd-color-") as tmp:
            base = Path(tmp)
            for name in ("home", "config/inir", "cache/quickshell/scripts", "state", "bin", "venv/bin", "source/scripts/colors", "source/scripts/lib"):
                (base / name).mkdir(parents=True, exist_ok=True)
            script = base / "source/scripts/colors/switchwall.sh"
            shutil.copy(ROOT / "scripts/colors/switchwall.sh", script)
            shutil.copy(ROOT / "scripts/lib/config-path.sh", base / "source/scripts/lib/config-path.sh")
            stub = base / "source/scripts/colors/system24_palette.sh"
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
            for executable, body in {
                "gsettings": "exit 0",
                "pkill": 'printf invoked > "$TEST_PKILL"; exit 0',
            }.items():
                path = base / "bin" / executable
                path.write_text("#!/bin/sh\n" + body + "\n")
                path.chmod(0o755)
            python = base / "venv/bin/python3"
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$TEST_GENERATOR_ARGS"\nexit 1\n')
            python.chmod(0o755)
            source = base / "wallpaper.png"
            backdrop = base / "backdrop.png"
            source.write_bytes(b"fixture")
            backdrop.write_bytes(b"backdrop")
            restore = base / "cache/quickshell/scripts/__restore_video_wallpaper.sh"
            restore.write_text("preserve")
            config = {
                "appearance": {"theme": "auto", "wallpaperTheming": {"useBackdropForColors": True}},
                "background": {"wallpaperPath": "original", "hideUpscaleNotification": True,
                               "backdrop": {"useMainWallpaper": False, "wallpaperPath": str(backdrop)}},
                "panelFamily": "iris",
            }
            config_file = base / "config/inir/config.json"
            config_file.write_text(json.dumps(config))
            before = config_file.read_bytes()
            env = dict(os.environ, HOME=str(base / "home"), XDG_CONFIG_HOME=str(base / "config"),
                       XDG_CACHE_HOME=str(base / "cache"), XDG_STATE_HOME=str(base / "state"),
                       INIR_VENV=str(base / "venv"), PATH=str(base / "bin") + ":/usr/bin:/bin",
                       TEST_GENERATOR_ARGS=str(base / "args"), TEST_PKILL=str(base / "pkill"))
            for key in ("DBUS_SESSION_BUS_ADDRESS", "NIRI_SOCKET", "WAYLAND_DISPLAY"):
                env.pop(key, None)
            proc = subprocess.run(["bash", str(script), "--image", str(source), "--mode", "dark",
                                   "--exact-color-source"], env=env, text=True, capture_output=True, timeout=15)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            args = (base / "args").read_text().splitlines()
            self.assertEqual(args[args.index("--path") + 1], str(source))
            self.assertNotIn(str(backdrop), args)
            self.assertEqual(config_file.read_bytes(), before)
            self.assertTrue(restore.exists())
            self.assertFalse((base / "pkill").exists())


if __name__ == "__main__":
    unittest.main()
