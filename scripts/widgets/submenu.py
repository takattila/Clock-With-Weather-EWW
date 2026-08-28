#!/usr/bin/env python3
"""Hover submenu pane for the selectable context-menu items.

Hovering one of the five quick-setting rows (AM/PM switch, Theme,
Units, Panel shown/hidden, Side right/left) shows a picker pane INSIDE the context
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
  ./submenu.py --item <key> [--widget clock|panel]
  (--widget scopes the row-offset math to the menu that is actually open:
   clock shows AM/PM, Theme, Units; panel shows Theme, Panel, Side.)
"""

import argparse
import json
import math
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
SUB_ROW_H = 30   # one picker row (deliberate over-estimate: clamps fire early)
SUB_PAD_V = 8    # picker vertical padding (top+bottom)

# The pane lives INSIDE the ctx_menu window. ctx.py opens that window with a
# height that already reaches the monitor bottom (menu_h = monitor_h - y -
# EDGE_MARGIN, floored at BASE_MENU_H) and stores menu_h / monitor_h / y in
# the input session; this script then keeps the pane inside the window and
# on the screen purely with eww variables (sub_top clamp + adaptive column
# count), because `eww update` cannot change window-arg variables (menu_h,
# pos_y) of a running window. EDGE_MARGIN is the gap kept above the bottom
# screen edge. PANE_W is the FIXED width of the picker pane strip in the
# yuck (both the left and the right instance): the submenu hugs the menu
# side of the strip, so the menu column never moves when the hovered
# submenu changes width.
BASE_MENU_H = 550
EDGE_MARGIN = 8
PANE_W = 375
MENU_COL_W = 290  # exact pinned width of the ctx-menu column (eww.yuck :width 290)


def horizontal_layout(x, monitor_w, pane_w_max=PANE_W):
    """(x_open, sub_left) for the ctx_menu window on `monitor_w` px.

    The picker pane renders RIGHT of the menu column by default. When that
    would cross the right monitor edge but the pane fits on the left, the
    window opens pane_w_max further left and the pane FLIPS to the left
    side of the menu column (sub_left=true) — so even the widest (3-column)
    theme picker stays fully on-screen. As a last resort (pane fits on
    neither side) the window just shifts left, clamped to the monitor.
    """
    if not monitor_w:
        return x, False
    fits_right = x + MENU_COL_W + pane_w_max + EDGE_MARGIN <= monitor_w
    fits_left = x - pane_w_max >= 0
    if fits_right:
        return x, False
    if fits_left:
        return x - pane_w_max, True
    return max(0, min(x, monitor_w - MENU_COL_W - pane_w_max - EDGE_MARGIN)), False

# Row index (0-based) of every selectable item inside widget_ctx_menu, PER
# the widget whose menu is open. These are VISIBLE column positions: the
# context-filtered (hidden) rows are plain-box wrapped (:visible) in the
# yuck and COLLAPSE - the hidden markup slots take no space - so the indices
# must match the order of the COLLAPSED column, not the markup order (see
# eww.yuck). The clock menu drops Panel/Side/Panel-gap/its sep; the panel
# menu drops AM/PM/sep/Units/Weather - so in the panel menu, e.g., Theme
# sits ONE row higher (4) and Panel/Side at 6/7.
CONTEXT_ROWS = {
    "clock": {
        "hour_format": 4,   # 0 Move,1 Resize,2 Reset,3 sep -> 4 is AM/PM
        "appearance": 5,
        "units": 7,         # 6 is the clock-only sep after Theme
    },
    "panel": {
        "appearance": 4,       # AM/PM is hidden -> Theme one row higher
        "panel_enabled": 6,    # 5 is the panel-only sep after Theme
        "panel_alignment": 7,
    },
}
# Default scope for bare callers / the legacy ROWS accessor.
ROWS = CONTEXT_ROWS["clock"]
KEYS = tuple(sorted({key for rows in CONTEXT_ROWS.values() for key in rows}))


def rows_for(widget):
    """Row-index map of the selectable items for the open widget's menu."""
    return CONTEXT_ROWS.get(widget) or CONTEXT_ROWS["clock"]


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
    """Split the option list into `columns` balanced column lists."""
    columns = max(1, int(columns))
    per_col = math.ceil(len(options) / float(columns)) if options else 0
    return [options[i * per_col:(i + 1) * per_col] for i in range(columns)]


def build_yuck(key, options, active, columns):
    """Render the whole picker as one static yuck definition.

    Real values, the active-state class and the click handler are baked in:
    eww 0.6.0 does not wire handlers onto widgets created inside `(for ...)`
    loops, so the definition is generated here instead of looped in yuck.
    """
    chunks = split_columns(options, columns)

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
    for col in chunks:
        if not col:
            continue
        parts.append(
            '(box :orientation "v" :space-evenly false %s)' % "".join(row(o) for o in col)
        )
    parts.append(")")
    return " ".join(parts)


def pane_top_for(key, widget="clock"):
    """Vertical offset of the picker inside the ctx_menu window."""
    return int(MENU_PAD + rows_for(widget)[key] * ROW_H)


THEME_ROW_TOP = int(MENU_PAD + CONTEXT_ROWS["clock"]["appearance"] * ROW_H)

# Number of ctx-menu column rows VISIBLE per widget (markup rows minus the
# context-filtered ones). Drives menu_content_height() so ctx.py never sizes
# the window below its column content - keep in sync with widget_ctx_menu.
VISIBLE_ROW_COUNTS = {"clock": 12, "panel": 12}


def menu_content_height(widget="clock"):
    """Height the ctx-menu COLUMN occupies: visible rows + vertical padding.

    Both menus show 12 rows; the helper stays widget-scoped so a future
    layout drift cannot silently clip one menu's content.
    """
    rows = VISIBLE_ROW_COUNTS.get(widget, VISIBLE_ROW_COUNTS["clock"])
    return int(rows * ROW_H + 2 * MENU_PAD)


def menu_layout(y, monitor_h, content_h, needed_h):
    """(y, menu_h) sizing for the ctx_menu window on `monitor_h` tall screen.

    The column must NEVER be clipped: the window is at least as tall as the
    column itself (content_h). When y + content_h would run past the screen
    bottom (y near the bottom edge), the menu is anchored flush to the bottom
    and grows upward - i.e. it starts from the screen bottom - so all visible
    rows stay on-screen. Otherwise y is kept and the window may grow up to
    needed_h (the theme picker's worst case) without mutating the window.
    """
    available = monitor_h - EDGE_MARGIN
    if y + content_h > available:
        y = max(0, available - content_h)
    window_h = int(max(
        content_h,
        min(max(BASE_MENU_H, needed_h), available - y),
    ))
    return y, window_h


def pane_height(options, columns):
    """Total picker pane height in px (rows * pitch + vertical padding)."""
    rows = math.ceil(len(options) / float(columns)) if columns > 0 else len(options)
    return int(rows * SUB_ROW_H + SUB_PAD_V)


def max_pane_height(columns=2):
    """Worst-case theme picker pane height for the CURRENT theme count.

    ctx.py uses it at menu-open time to size the ctx_menu window so the
    theme picker always fits without any runtime window mutation.
    """
    return pane_height([None] * len(available_themes()), columns)


def session_geometry():
    """{y, monitor_h, menu_h} of the open ctx_menu window (fallbacks when
    the input session file is missing: menu at the top of a 1080p screen
    with the default window height)."""
    path = os.path.join(CONFIG_DIR, "generated", "input_session.json")
    geo = {"y": 0, "monitor_h": 1080, "menu_h": BASE_MENU_H}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        geo["y"] = int(data.get("y", 0))
        geo["monitor_h"] = int(data.get("monitor_h", 1080))
        geo["menu_h"] = int(data.get("menu_h", BASE_MENU_H))
    except Exception:
        pass
    return geo


def open_item(key, widget="clock"):
    cfg = load_merged(CONFIG_DIR)
    options = options_for(key, cfg)
    active = active_for(key, cfg)

    # Everything the pane may need is known at menu-open time: ctx.py sized
    # the window to reach the monitor bottom (session menu_h) and stored the
    # monitor height. The pane is kept inside BOTH purely with eww variables:
    # `eww update` cannot change window-arg variables (menu_h, pos_y) of a
    # running window, so the window itself is never mutated here.
    geo = session_geometry()
    limit = max(
        MENU_PAD,
        min(geo["menu_h"], geo["monitor_h"] - EDGE_MARGIN - geo["y"]) - MENU_PAD,
    )
    row_top = pane_top_for(key, widget)

    columns = 2 if key == "appearance" else 1
    while key == "appearance" and columns < 3 and \
            pane_height(options, columns) > limit - row_top:
        columns += 1  # long list + little room: trade width for height
    pane_h = pane_height(options, columns)
    top = int(max(MENU_PAD, min(row_top, limit - pane_h)))

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
    ap.add_argument("--widget", choices=sorted(CONTEXT_ROWS), default="clock")
    args = ap.parse_args()

    if not args.item:
        sys.exit("Usage: ./submenu.py --item <key> [--widget clock|panel]")

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

    open_item(args.item, args.widget)


if __name__ == "__main__":
    main()
