#!/usr/bin/env python3
"""Generic hover submenu for the selectable context-menu items.

Hovering one of the five quick-setting rows (AM/PM switch, Theme, Units,
Panel shown/hidden, Side right/left) opens a small eww window next to that
row listing the possible values; the active one is highlighted and clicking
an entry writes it via menu_toggle.py -> config_set.py into the git-ignored
config.local.yaml (the watcher applies the change live).

Mechanics:
  * ctx.py stores the fact that the context menu is open in the session file;
    this script additionally reads the menu's REAL X11 geometry (xwininfo)
    and anchors the submenu RELATIVE to it: right of the menu by default,
    flipped to its left side when it would not fit, clamped to the monitor
    frame. Without a live ctx_menu nothing is opened (no orphans).
  * The whole picker is prebuilt as a static yuck definition with real
    values, the active-state class and hover/click handlers baked in, pushed
    into the `sub_yuck` eww variable and rendered via `(literal ...)`.
    Theme is split across two balanced columns; everything else is a single
    column. (Handlers on widgets created inside `(for ...)` loops never fire
    on eww 0.6.0, which rules out looping over JSON in yuck.)
  * Closing is hover-driven with a small delay: leaving a row schedules a
    close (a detached helper sleeps CLOSE_DELAY and closes only when the
    generation counter still matches), entering any row / the submenu again
    cancels pending timers by bumping the counter. ESC / outside clicks go
    through close_popup.py which closes the submenu unconditionally.

Usage:
  ./submenu.py --item hour_format|appearance|units|panel_enabled|panel_alignment
  ./submenu.py --schedule-close
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# scripts/widgets/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "move"))

from config_io import load_merged

APPEARANCE_THEMES_DIR = os.path.join(CONFIG_DIR, "assets", "themes", "appearance")
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
GEN_FILE = os.path.join(CONFIG_DIR, "generated", "submenu_gen")

# Geometry constants (kept in sync with eww.yuck / eww.scss).
MENU_PAD = 7       # ctx_menu top/bottom padding (+border)
SUB_ROW_H = 30     # one submenu row
SUB_PAD_V = 8      # submenu vertical padding (top+bottom)
SUB_W1 = 150       # single-column submenu width
SUB_W2 = 244       # two-column submenu width (Theme)
OVERLAP = 4        # horizontal overlap with the parent menu edge
CLOSE_DELAY = 0.3  # seconds before a scheduled close fires

# Row index of every selectable item inside widget_ctx_menu (0-based).
ROWS = {
    "hour_format": 3,
    "appearance": 4,
    "units": 5,
    "panel_enabled": 6,
    "panel_alignment": 7,
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


def read_session():
    try:
        with open(SESSION_FILE) as fh:
            return json.load(fh)
    except Exception:
        return None


def read_gen():
    try:
        with open(GEN_FILE) as fh:
            return int(fh.read().strip() or 0)
    except Exception:
        return 0


def bump_gen():
    gen = read_gen() + 1
    try:
        os.makedirs(os.path.dirname(GEN_FILE), exist_ok=True)
        with open(GEN_FILE, "w") as fh:
            fh.write(str(gen))
    except Exception:
        pass
    return gen


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


def geometry_for(key, n_options, menu_x, menu_y, menu_w, menu_h, frame_w, frame_h):
    """Submenu geometry RELATIVE to the parent menu's real rect (flip+clamp).

    The vertical anchor is calibrated from the parent window's ACTUAL height
    (the ten rows share menu_h - 2*MENU_PAD evenly), so font/padding changes
    can never skew it; horizontally the submenu hugs the parent's right edge
    with a small overlap and flips to its left side when it would not fit.
    """
    columns = 2 if key == "appearance" else 1
    rows = (n_options + columns - 1) // columns
    w = SUB_W2 if columns == 2 else SUB_W1
    h = rows * SUB_ROW_H + SUB_PAD_V
    row_h = max(1.0, (menu_h - 2 * MENU_PAD) / 10.0)
    x = menu_x + menu_w - OVERLAP
    if x + w > frame_w and menu_x - w + OVERLAP >= 0:
        x = menu_x - w + OVERLAP
    x = max(0, min(x, max(0, frame_w - w)))
    y = int(menu_y + MENU_PAD + ROWS[key] * row_h)
    y = max(0, min(y, max(0, frame_h - h)))
    return int(x), int(y), int(w), int(h)


def build_yuck(key, options, active, columns):
    """Render the whole picker as a static yuck string.

    Eww 0.6.0 does not wire event handlers onto widgets created inside a
    `(for ...)` loop (hover/click silently dead there — measured on this
    machine), so instead of looping over JSON data in yuck, this bakes the
    real option values straight into a literal definition that eww renders
    exactly like hand-written config.
    """
    col_a, col_b = split_columns(options, columns)

    def row(o):
        cls = "sub-btn active" if o["value"] == str(active) else "sub-btn"
        return (
            '(eventbox :class "%s" :timeout "10s" '
            ':onhover "../scripts/widgets/submenu.py --cancel-close" '
            ':onhoverlost "../scripts/widgets/submenu.py --schedule-close" '
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


def frame_size(screen):
    """(width, height) of the monitor frame in eww-coordinate basis."""
    import widget_rect as wr  # scripts/move helper set
    data = wr.get_monitors()
    monitors = data.get("monitors") or []
    mon = next((m for m in monitors if m.get("index") == screen), None)
    if mon is None:
        return None
    workarea = wr.get_workarea()
    wx = max(workarea[0], mon["x"])
    wy = max(workarea[1], mon["y"])
    ww = min(workarea[0] + workarea[2], mon["x"] + mon["width"]) - wx
    wh = min(workarea[1] + workarea[3], mon["y"] + mon["height"]) - wy
    if ww <= 0 or wh <= 0:
        ww, wh = mon["width"], mon["height"]
    return max(1, int(ww)), max(1, int(wh))


CTX_MENU_XNAME = '"Eww - ctx_menu"'
XENV_KEYS = ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR")


def ctx_menu_rect():
    """Absolute X11 rect of the parent ctx_menu window, or None.

    The submenu is positioned RELATIVE to this real geometry (not to cached
    estimates): xwininfo reports both the local and the absolute placement,
    so this also pins the correct monitor no matter how the indices map.
    """
    env = {k: v for k, v in os.environ.items() if k in XENV_KEYS}
    try:
        out = subprocess.run(
            ["xwininfo", "-root", "-tree"], capture_output=True, text=True,
            timeout=5, env=env,
        ).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if CTX_MENU_XNAME not in line:
            continue
        m = re.search(
            r"(\d+)x(\d+)\+\d+\+\d+\s+\+(\d+)\+(\d+)", line
        )
        if m:
            w, h, ax, ay = (int(g) for g in m.groups())
            return {"w": w, "h": h, "ax": ax, "ay": ay}
    return None


def monitor_at(ax, ay):
    """monitors.py entry covering the absolute point (ax, ay), or None."""
    import widget_rect as wr
    data = wr.get_monitors()
    for mon in data.get("monitors") or []:
        if mon["x"] <= ax < mon["x"] + mon["width"] and \
           mon["y"] <= ay < mon["y"] + mon["height"]:
            return mon
    return None


def open_item(key):
    bump_gen()  # invalidate any pending scheduled close
    cfg = load_merged(CONFIG_DIR)
    options = options_for(key, cfg)
    active = active_for(key, cfg)
    columns = 2 if key == "appearance" else 1

    # Position RELATIVE to the parent menu's REAL on-screen geometry. The
    # session file is only used as a liveness check: without an open ctx_menu
    # there is nothing to anchor to (prevents orphaned submenus).
    sess = read_session()
    if not sess or sess.get("mode") != "ctx":
        return
    rect = ctx_menu_rect()
    if rect is None:
        return

    mon = monitor_at(rect["ax"], rect["ay"])
    if mon is None:
        return
    screen = int(mon["index"])
    lx = rect["ax"] - mon["x"]          # parent menu in monitor-local coords
    ly = rect["ay"] - mon["y"]

    frame = frame_size(screen) or (mon["width"], mon["height"])
    x, y, w, h = geometry_for(
        key, len(options), lx, ly, rect["w"], rect["h"], frame[0], frame[1],
    )

    eww("update", "sub_yuck=%s" % build_yuck(key, options, active, columns))
    eww(
        "open",
        "--id", "submenu",
        "--screen", str(screen),
        "--arg", "sx=%d" % x,
        "--arg", "sy=%d" % y,
        "--arg", "sw=%d" % w,
        "--arg", "sh=%d" % h,
        "submenu",
    )


def schedule_close():
    """Remember the generation, then close after CLOSE_DELAY unless superseded."""
    gen = read_gen()
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--_delayed-close", str(gen)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )


def cancel_close():
    """Entering any row / the submenu itself invalidates pending timers."""
    bump_gen()


def delayed_close(gen):
    time.sleep(CLOSE_DELAY)
    if read_gen() != gen:
        return  # a newer hover/open/cancel invalidated this timer
    eww("close", "submenu")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", choices=KEYS)
    ap.add_argument("--schedule-close", action="store_true")
    ap.add_argument("--cancel-close", action="store_true")
    ap.add_argument("--_delayed-close", type=int, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args._delayed_close is not None:
        delayed_close(args._delayed_close)
        return
    if not args.item and not args.schedule_close and not args.cancel_close:
        sys.exit("Usage: ./submenu.py --item <key> | --schedule-close | --cancel-close")

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

    if args.item:
        open_item(args.item)
    elif args.cancel_close:
        cancel_close()
    else:
        schedule_close()


if __name__ == "__main__":
    main()
