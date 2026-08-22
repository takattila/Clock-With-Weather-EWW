#!/usr/bin/env python3
"""Hover submenu pane for the selectable context-menu items.

Hovering one of the five quick-setting rows (AM/PM switch, Theme, Units,
Panel shown/hidden, Side right/left) shows a picker pane INSIDE the context
menu window, right of the item rows and vertically aligned with the hovered
row. The active value is highlighted; clicking an entry writes it via
menu_toggle.py -> config_set.py into the git-ignored config.local.yaml (the
watcher applies the change live).

Why a pane instead of a separate window (all measured on eww 0.6.0/X11):
  * event handlers on widgets created inside `(for ...)` loops never fire;
  * re-opening the same window id quickly leaves the previous override-
    redirect X window behind — invisible copies stack up and swallow every
    pointer event, which made the whole menu feel dead;
  * an extra input-transparent window cannot be dismissed by outside clicks.

Rendering the picker as a prebuilt static yuck definition (real values,
active-state class and the click handler baked in) pushed into the `sub_yuck`
variable and displayed via `(literal ...)` inside the ctx_menu window avoids
all three. The pane is shown/hidden purely with eww variables, so behavior is
identical on X11 and Wayland.

Usage:
  ./submenu.py --item hour_format|appearance|units|panel_enabled|panel_alignment
"""

import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# scripts/widgets/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

from config_io import load_merged

APPEARANCE_THEMES_DIR = os.path.join(CONFIG_DIR, "assets", "themes", "appearance")

# Pane geometry (kept in sync with eww.yuck / eww.scss).
MENU_PAD = 7     # ctx_menu top padding (+border)
ROW_H = 42.6     # calibrated pitch of one context-menu row
SUB_ROW_H = 30   # one picker row
SUB_PAD_V = 8    # picker vertical padding (top+bottom)

# Row index of every selectable item inside widget_ctx_menu (0-based).
ROWS = {
    "hour_format": 4,       # +1: actions|settings separator
    "appearance": 5,
    "units": 6,
    "panel_enabled": 7,
    "panel_alignment": 8,   # settings|system separator follows
}
KEYS = tuple(ROWS)


def run(cmd):
    try:
        subprocess.run(
            cmd, check=False, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=20,
        )
    except Exception:
        pass


def eww(*args):
    run(["eww", "--config", EWW_CONFIG_DIR] + list(args))


def available_themes():
    """Sorted appearance-theme directory names ('light' as safe fallback)."""
    try:
        names = [
            n for n in sorted(os.listdir(APPEARANCE_THEMES_DIR))
            if os.path.isdir(os.path.join(APPEARANCE_THEMES_DIR, n))
        ]
    except OSError:
        names = []
    return names or ["light"]


def options_for(key, cfg):
    """The [{label, value}, ...] entries shown for `key`."""
    if key == "hour_format":
        return [{"label": "24h", "value": "24"},
                {"label": "12h", "value": "12"}]
    if key == "appearance":
        return [{"label": name, "value": name} for name in available_themes()]
    if key == "units":
        return [{"label": "°C (metric)", "value": "metric"},
                {"label": "°F (imperial)", "value": "imperial"}]
    if key == "panel_enabled":
        return [{"label": "shown", "value": "true"},
                {"label": "hidden", "value": "false"}]
    if key == "panel_alignment":
        return [{"label": "right", "value": "right"},
                {"label": "left", "value": "left"}]
    raise SystemExit("ERROR: unknown submenu item: %s" % key)


def active_for(key, cfg):
    """Current value of `key` from the merged view ('' = nothing matches)."""
    system = cfg.get("system") or {}
    weather = cfg.get("weather") or {}
    panel = cfg.get("panel") or {}
    if key == "hour_format":
        return str(system.get("hour_format", "24"))
    if key == "appearance":
        current = cfg.get("appearance", "light")
        # A custom inline appearance map is an OBJECT: no theme matches.
        return str(current) if isinstance(current, str) else "__none__"
    if key == "units":
        return str(weather.get("units") or "metric")
    if key == "panel_enabled":
        return str(panel.get("enabled", True)).strip().lower()
    if key == "panel_alignment":
        return str((panel.get("window") or {}).get("alignment", "right")).strip().lower()
    return ""


def split_columns(options, columns):
    """Split the option list into balanced column lists."""
    if columns <= 1:
        return options, []
    half = (len(options) + 1) // 2
    return options[:half], options[half:]


def build_yuck(key, options, active, columns):
    """Render the whole picker as one static yuck definition.

    Real values, the active-state class and the click handler are baked in:
    eww 0.6.0 does not wire handlers onto widgets created inside `(for ...)`
    loops, so the definition is generated here instead of looped in yuck.
    """
    col_a, col_b = split_columns(options, columns)

    def row(o):
        cls = "sub-btn active" if o["value"] == str(active) else "sub-btn"
        return (
            '(eventbox :class "%s" :timeout "10s" '
            ':onclick {"../scripts/widgets/close_popup.py && nohup '
            '../scripts/widgets/menu_toggle.py --key %s --value %s '
            '>/dev/null 2>&1 &"} '
            '(box :class "sub-btn-box" (label :text "%s")))'
            % (cls, key, o["value"], o["label"])
        )

    parts = ['(box :class "submenu" :orientation "h" :space-evenly false']
    for col in (col_a, col_b):
        if not col:
            continue
        parts.append(
            '(box :orientation "v" :space-evenly false %s)' % "".join(row(o) for o in col)
        )
    parts.append(")")
    return " ".join(parts)


def pane_top_for(key):
    """Vertical offset of the picker inside the ctx_menu window."""
    return int(MENU_PAD + ROWS[key] * ROW_H)


def open_item(key):
    cfg = load_merged(CONFIG_DIR)
    options = options_for(key, cfg)
    active = active_for(key, cfg)
    columns = 2 if key == "appearance" else 1
    top = pane_top_for(key)

    eww(
        "update",
        "sub_yuck=%s" % build_yuck(key, options, active, columns),
        "sub_top=%d" % top,
        "sub_cols=%d" % columns,
        "sub_show=true",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", choices=KEYS)
    args = ap.parse_args()

    if not args.item:
        sys.exit("Usage: ./submenu.py --item <key>")

    # eww kills widget commands whose runtime exceeds its timeout even when
    # :timeout is set on the eventbox; re-spawn detached like ctx.py does so
    # the hover handler returns immediately.
    if os.environ.get("EWW_SUBMENU_BG") != "1":
        env = dict(os.environ, EWW_SUBMENU_BG="1")
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__)] + sys.argv[1:],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
        return

    open_item(args.item)


if __name__ == "__main__":
    main()
