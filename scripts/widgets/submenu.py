#!/usr/bin/env python3
"""Generic hover submenu for the selectable context-menu items.

Hovering one of the five quick-setting rows (AM/PM switch, Theme, Units,
Panel shown/hidden, Side right/left) opens a small eww window next to that
row listing the possible values; the active one is highlighted and clicking
an entry writes it via menu_toggle.py -> config_set.py into the git-ignored
config.local.yaml (the watcher applies the change live).

Mechanics:
  * ctx.py stores the context-menu position (x/y/screen) in the session file;
    this script anchors the submenu relative to it: right of the menu by
    default, flipped to its left side when it would not fit, clamped to the
    monitor frame.
  * The option list is pushed as JSON into the eww variables sub_col_a /
    sub_col_b (Theme is split across two balanced columns, everything else is
    a single column); sub_active carries the current value for highlighting.
  * Closing is hover-driven with a small delay: leaving a row schedules a
    close (a detached helper sleeps CLOSE_DELAY and only fires when the
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
CTX_MENU_W = 220   # ctx_menu :width
CTX_ROW_H = 42     # one context-menu row (button + margins)
MENU_PAD = 7       # ctx_menu top padding (+border)
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


def geometry_for(key, n_options, menu_x, menu_y, frame_w, frame_h):
    """Submenu window geometry anchored to the parent row (flip + clamp)."""
    columns = 2 if ROWS.get(key, 0) >= 0 and key == "appearance" else 1
    rows = (n_options + columns - 1) // columns
    w = SUB_W2 if columns == 2 else SUB_W1
    h = rows * SUB_ROW_H + SUB_PAD_V
    x = menu_x + CTX_MENU_W - OVERLAP
    if x + w > frame_w and menu_x - w + OVERLAP >= 0:
        x = menu_x - w + OVERLAP
    x = max(0, min(x, max(0, frame_w - w)))
    y = menu_y + MENU_PAD + ROWS[key] * CTX_ROW_H
    y = max(0, min(y, max(0, frame_h - h)))
    return int(x), int(y), int(w), int(h)


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


def open_item(key):
    bump_gen()  # invalidate any pending scheduled close
    cfg = load_merged(CONFIG_DIR)
    options = options_for(key, cfg)
    active = active_for(key, cfg)
    columns = 2 if key == "appearance" else 1
    col_a, col_b = split_columns(options, columns)

    sess = read_session()
    if sess and sess.get("mode") == "ctx":
        screen = int(sess.get("screen", 0))
        menu_x = int(sess.get("x", 0))
        menu_y = int(sess.get("y", 0))
    else:  # stale/no session: still show something usable near top-left
        screen, menu_x, menu_y = 0, 100, 100

    frame = frame_size(screen) or (1920, 1080)
    x, y, w, h = geometry_for(key, len(options), menu_x, menu_y, frame[0], frame[1])

    eww(
        "update",
        "sub_col_a=%s" % json.dumps(col_a, separators=(",", ":")),
        "sub_col_b=%s" % json.dumps(col_b, separators=(",", ":")),
        "sub_active=%s" % active,
        "sub_cols=%d" % columns,
    )
    eww(
        "open",
        "--id", "submenu",
        "--screen", str(screen),
        "--arg", "key=%s" % key,
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


def delayed_close(gen):
    time.sleep(CLOSE_DELAY)
    if read_gen() != gen:
        return  # a newer hover/open/cancel invalidated this timer
    eww("close", "submenu")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", choices=KEYS)
    ap.add_argument("--schedule-close", action="store_true")
    ap.add_argument("--_delayed-close", type=int, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args._delayed_close is not None:
        delayed_close(args._delayed_close)
        return
    if not args.item and not args.schedule_close:
        sys.exit("Usage: ./submenu.py --item <key> | --schedule-close")

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
    else:
        schedule_close()


if __name__ == "__main__":
    main()
