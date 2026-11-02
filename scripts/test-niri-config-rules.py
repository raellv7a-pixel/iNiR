#!/usr/bin/env python3
"""Regression guard for scripts/niri-config.py: scoped window rules and on/off flags.

Runs the real script against a throwaway XDG_CONFIG_HOME, never the user's niri config.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "niri-config.py"

CONFIG = """include "config.d/20-layout-and-overview.kdl"
include "config.d/30-window-rules.kdl"
include "config.d/90-user-extra.kdl"
"""
LAYOUT = """layout {
    gaps 16
    shadow {
        off
        on
        softness 30
    }
    border {
        width 4
    }
}
"""
RULES = """// window-rule {
//     geometry-corner-radius 99
// }
window-rule {
    geometry-corner-radius 15
    clip-to-geometry true
}
window-rule {
    match app-id="^gamescope$"
    geometry-corner-radius 0
    clip-to-geometry false
}
"""

USER_EXTRA = """// Keep my own app-specific blur rule intact.
window-rule {
    match app-id="^kitty$"
    background-effect {
        blur true
        xray true
    }
}
"""


def run(env, *args):
    out = subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def main() -> int:
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        niri = Path(tmp) / "niri"
        (niri / "config.d").mkdir(parents=True)
        (niri / "config.kdl").write_text(CONFIG)
        (niri / "config.d" / "20-layout-and-overview.kdl").write_text(LAYOUT)
        (niri / "config.d" / "30-window-rules.kdl").write_text(RULES)
        extra_path = niri / "config.d" / "90-user-extra.kdl"
        extra_path.write_text(USER_EXTRA)
        env = dict(os.environ, XDG_CONFIG_HOME=tmp)
        effect_result = run(env, "sync-game-mode-window-effects", "on")
        if effect_result.get("success") is not True:
            failures.append(f"enabling Game Mode window effects failed: {effect_result}")
        active_rules = extra_path.read_text()
        if (active_rules.count("blur true") != 1
                or active_rules.count("blur false") != 1
                or active_rules.index("blur false") < active_rules.index("blur true")):
            failures.append("Game Mode did not append a later all-window blur override")
        active_again = run(env, "sync-game-mode-window-effects", "on")
        if active_again.get("changed") is not False or extra_path.read_text() != active_rules:
            failures.append("enabling Game Mode twice duplicated or rewrote its managed rule")
        off_result = run(env, "sync-game-mode-window-effects", "off")
        if off_result.get("success") is not True or extra_path.read_text() != USER_EXTRA:
            failures.append("disabling Game Mode did not restore the user's original window rules")
        off_again = run(env, "sync-game-mode-window-effects", "off")
        if off_again.get("changed") is not False:
            failures.append("disabling Game Mode twice was not idempotent")

        malformed = USER_EXTRA + "// >>> inir-game-mode-window-effects >>>\n"
        extra_path.write_text(malformed)
        malformed_result = run(env, "sync-game-mode-window-effects", "off")
        if "error" not in malformed_result or extra_path.read_text() != malformed:
            failures.append("a malformed managed block was not rejected without touching user config")

        rules = run(env, "get-window-rules")
        if rules.get("corner_radius") != 15 or rules.get("clip_to_geometry") is not True:
            failures.append(f"a game-scoped rule read back as the global one: {rules}")
        run(env, "set", "window-rules", "corner-radius", "12")
        text = (niri / "config.d" / "30-window-rules.kdl").read_text()
        if "geometry-corner-radius 99" not in text or text.count("geometry-corner-radius 0") != 1:
            failures.append("writing the radius touched a comment or a scoped rule")
        if run(env, "get-window-rules").get("corner_radius") != 12:
            failures.append("the written radius does not read back")

        layout = run(env, "get-layout")
        if layout["shadow"]["enabled"] is not True or layout["border"]["enabled"] is not False:
            failures.append(f"on/off flags misread (last flag wins, border is off by default): {layout}")
        run(env, "set", "layout", "shadow.enabled", "off")
        block = (niri / "config.d" / "20-layout-and-overview.kdl").read_text()
        if block.count(" on\n") or block.count("off\n") != 1:
            failures.append("turning the shadow off left more than one flag")
        if run(env, "get-layout")["shadow"]["enabled"] is not False:
            failures.append("the shadow did not read back off")
        run(env, "set", "layout", "border.enabled", "on")
        if run(env, "get-layout")["border"]["enabled"] is not True:
            failures.append("a border (off by default) could not be turned on")

    if failures:
        print("niri-config rules failures:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("niri-config rules: scoped rules, flags, and Game Mode effects round-trip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
