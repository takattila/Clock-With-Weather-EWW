#!/usr/bin/env python3
"""Open the context menu for a widget.

Computes the menu position (scripts/move/menu_pos.py: cursor on X11, widget
corner on Wayland), closes any previously open menu and opens ctx_menu at
that spot.

Usage:
  ./ctx.py --widget clock --monitor 0
  ./ctx.py --widget panel --monitor 1
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

import session  # noqa: E402
import widget_rect as wr  # noqa: E402
import menu_pos  # noqa: E402
import submenu  # noqa: E402  (same directory: pane geometry for menu_h sizing)

# The monitor enumeration (xrandr) is the slowest piece of the right-click
# path (~250 ms on this machine). It only changes on hotplug, which
# monitor_watch.py handles separately, so a short-TTL cache file keeps
# consecutive clicks instant while staying self-healing.
MONITORS_CACHE = os.path.join(CONFIG_DIR, "generated", "monitors-cache.json")
MONITORS_TTL = 30.0


def run(cmd, capture=False):
    try:
        if capture:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ""
    except Exception:
        return ""


def get_monitors_cached():
    """monitors JSON from the TTL cache, refreshing it on expiry."""
    now = time.time()
    try:
        with open(MONITORS_CACHE) as fh:
            cached = json.load(fh)
        if now - float(cached.get("ts", 0)) < MONITORS_TTL \
                and cached.get("data", {}).get("monitors"):
            return cached["data"]
    except Exception:
        pass
    out = run(
        ["python3", os.path.join(CONFIG_DIR, "scripts", "core", "monitors.py")],
        capture=True,
    )
    data = json.loads(out)
    try:
        os.makedirs(os.path.dirname(MONITORS_CACHE), exist_ok=True)
        with open(MONITORS_CACHE, "w") as fh:
            json.dump({"ts": now, "data": data}, fh)
    except Exception:
        pass
    return data


def resolve_cursor(data):
    """Compositor-appropriate global cursor (px, py), or None.

    X11 trusts xdotool. On Wayland xdotool only tracks the pointer over
    XWayland surfaces -- above our native layer-shell widgets it returns a
    stale position, which once redirected EVERY panel right-click to the
    clock. KDE exposes the real global pointer through the KWin scripting
    API (workarea.kde_cursor); compositors without such an API yield None,
    in which case ownership forwarding must stay off (keep the claimed
    widget) instead of acting on garbage coordinates.
    """
    if data.get("compositor", "x11") == "wayland":
        try:
            import workarea as _wa

            return _wa.kde_cursor()
        except Exception:
            return None
    return cursor_position()


def collect_rects_data(screens, data, workarea):
    """Visible rectangles for BOTH widgets on every screen, in-process.

    Replaces the previous 4x widget_rect.py subprocess storm (~2.3 s): the
    module-level functions share one monitors fetch / PIL import.
    """
    rects = []
    compositor = data.get("compositor", "x11")
    mons = {int(m["index"]): m for m in data.get("monitors", [])}
    for wgt in ("clock", "panel"):
        for idx in screens:
            m = mons.get(idx)
            if m is None:
                continue
            r = wr.clock_rect(m, compositor, workarea, idx) if wgt == "clock" \
                else wr.panel_rect(m, compositor, workarea, idx)
            rects.append({"widget": wgt, "monitor": idx,
                          "x": int(r["abs_x"]), "y": int(r["abs_y"]),
                          "w": int(r["width"]), "h": int(r["height"])})
    return rects


def cursor_position():
    """Global cursor (px, py) via xdotool, or None (unavailable / Wayland)."""
    out = run(["xdotool", "getmouselocation"], capture=True)
    m = {}
    for part in out.split():
        if ":" in part:
            k, v = part.split(":", 1)
            m[k] = v
    try:
        return int(m["x"]), int(m["y"])
    except (KeyError, ValueError):
        return None


def choose_widget(claimed_widget, claimed_monitor, cursor, rects):
    """(widget, monitor) whose VISIBLE area actually sits under the cursor.

    The scaled content is drawn inside a larger transparent canvas window,
    so the X server may deliver a right-click aimed at one widget to the
    OTHER one's canvas overlapping it (measured: clicks on the clock's
    visible part that fell into the panel's transparent bottom strip opened
    the panel menu). If the claimed widget's visible rect does not contain
    the cursor but exactly one other candidate rect does, that other
    wins. Ambiguity keeps the claimed widget; unknown cursor / rects keep
    it too (behaviour identical to pre-forwarding).
    """
    if not cursor:
        return claimed_widget, claimed_monitor

    def contains(r):
        return bool(r) and r["x"] <= cursor[0] < r["x"] + r["w"] \
            and r["y"] <= cursor[1] < r["y"] + r["h"]

    claimed_rect = next((r for r in rects if r["widget"] == claimed_widget
                         and r["monitor"] == claimed_monitor), None)
    others = [r for r in rects
              if (r["widget"], r["monitor"]) != (claimed_widget, claimed_monitor)]
    if contains(claimed_rect) or not any(contains(r) for r in others):
        return claimed_widget, claimed_monitor
    hits = [r for r in others if contains(r)]
    # Deterministic pick: the SMALLEST containing rect (most specific hit).
    best = min(hits, key=lambda r: r["w"] * r["h"])
    return best["widget"], best["monitor"]


def widget_visible_rect(widget, monitor):
    """Absolute visible rectangle {x,y,w,h} or None (subprocess fallback)."""
    out = run(
        ["python3", os.path.join(CONFIG_DIR, "scripts", "move", "widget_rect.py"),
         "--widget", widget, "--monitor", str(monitor)],
        capture=True,
    )
    try:
        r = json.loads(out)
        return {"x": int(r["abs_x"]), "y": int(r["abs_y"]),
                "w": int(r["width"]), "h": int(r["height"])}
    except Exception:
        return None


def collect_rects(screens):
    """Legacy subprocess variant, kept as the fast path's fallback."""
    rects = []
    for widget in ("clock", "panel"):
        for idx in screens:
            r = widget_visible_rect(widget, idx)
            if r:
                rects.append({"widget": widget, "monitor": idx, **r})
    return rects


def main():
    if os.environ.get("EWW_CTX_BG") != "1":
        # eww kills widget commands whose runtime exceeds its timeout (default
        # 200ms) even when :timeout is set on the widget. ctx.py spawns several
        # subprocesses (menu_pos + eww calls) and can take ~300ms, so re-spawn
        # ourselves detached: the eww command returns immediately and the work
        # keeps running in the background.
        env = dict(os.environ, EWW_CTX_BG="1")
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__)] + sys.argv[1:],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
        return

    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", required=True, choices=["clock", "panel"])
    ap.add_argument("--monitor", type=int, default=0)
    args = ap.parse_args()

    # FAST PATH (single process): one cached monitors fetch + one workarea
    # read feed BOTH the ownership resolution and the menu placement. The
    # previous flow spawned 6 helper processes (~3.5 s); this one stays
    # in-process (~0.1 s warm / ~0.5 s cold). Any failure falls back to the
    # old subprocess pipeline for the claimed widget.
    widget, monitor = args.widget, args.monitor
    screens = []
    pos = None
    try:
        data = get_monitors_cached()
        workarea = wr.get_workarea()
        screens = sorted(int(m["index"]) for m in data.get("monitors", []))
        rects = collect_rects_data(screens, data, workarea)
        cursor = resolve_cursor(data)
        widget, monitor = choose_widget(
            args.widget, args.monitor, cursor, rects)
        pos = menu_pos.menu_position(widget, monitor, data, workarea,
                                     cursor=cursor)
    except Exception:
        widget, monitor = args.widget, args.monitor
        pos = None

    if pos is None:
        out = run(
            ["python3", os.path.join(CONFIG_DIR, "scripts", "move", "menu_pos.py"),
             "--widget", widget, "--monitor", str(monitor)],
            capture=True,
        )
        try:
            pos = json.loads(out)
        except Exception:
            sys.exit("ERROR: menu_pos.py failed:\n%s" % out)
        if not screens:
            screens = [int(pos["screen"])]

    # Open the transparent dismiss layers FIRST (so the menu stacks above
    # them): one per connected monitor, so clicking anywhere on ANY screen —
    # not just the menu's own one — closes the popups. Then the context menu.
    # A leftover submenu from an earlier session is closed as well.
    if not screens:
        screens = [int(pos["screen"])]
    run(["eww", "--config", EWW_CONFIG_DIR, "close", "dismiss_overlay"])
    for idx in screens:
        run(["eww", "--config", EWW_CONFIG_DIR, "close",
             "dismiss_overlay_%d" % idx])
    run(["eww", "--config", EWW_CONFIG_DIR, "close", "submenu"])
    try:
        os.remove(os.path.join(CONFIG_DIR, "generated", "submenu_open"))
    except OSError:
        pass
    run(["eww", "--config", EWW_CONFIG_DIR, "close", "ctx_menu"])
    for idx in screens:
        run(["eww", "--config", EWW_CONFIG_DIR, "open",
             "--id", "dismiss_overlay_%d" % idx,
             "--screen", str(idx),
             "--arg", "screen=%d" % idx,
             "dismiss_overlay"])
    run(["eww", "--config", EWW_CONFIG_DIR, "close", "ctx_menu"])
    # Window height: at open time the window is sized so its CONTENT never
    # gets clipped (menu_h >= column height). Near the bottom edge the menu
    # anchors flush to the screen bottom and grows upward (starts from the
    # screen bottom); otherwise it may grow up to needed_h (the theme picker's
    # worst case) and the bottom idle area is click-through like the dismiss
    # overlays. The hover submenu pane keeps itself inside this window with eww
    # variables only (sub_top clamp + adaptive columns, see submenu.py) --
    # `eww update` cannot change window-arg variables of a running window, so
    # the sizing must happen HERE, before the open.
    mon_h = None
    try:
        mon_h = int(next(
            m["height"] for m in (data or {}).get("monitors", [])
            if int(m["index"]) == int(pos["screen"])
        ))
    except Exception:
        mon_h = None
    needed_h = submenu.THEME_ROW_TOP + submenu.max_pane_height(2) + submenu.MENU_PAD
    content_h = submenu.menu_content_height(widget)
    if mon_h:
        pos["y"], menu_h = submenu.menu_layout(
            pos["y"], mon_h, content_h, needed_h)
    else:
        menu_h = int(max(submenu.BASE_MENU_H, needed_h))

    # Horizontal flip: near the RIGHT monitor edge (e.g. the panel side) the
    # picker pane would be clipped, so the window opens shifted left and the
    # pane renders on the LEFT of the menu column (sub_left=true, see
    # submenu.horizontal_layout). sub_left is a plain global variable — it
    # must be pushed BEFORE the open (window-arg variables of a RUNNING
    # window cannot be changed by `eww update`, and the decision is per-open).
    mon_w = None
    try:
        mon_w = int(next(
            m["width"] for m in (data or {}).get("monitors", [])
            if int(m["index"]) == int(pos["screen"])
        ))
    except Exception:
        mon_w = None
    pos["x"], sub_left = submenu.horizontal_layout(pos["x"], mon_w)
    # All pane flags are plain globals pushed as ONE update BEFORE the open
    # (window-arg variables of a RUNNING window cannot be changed by
    # `eww update`, and the pair must be decided per-open): exactly one of the
    # two pane instances is visible at any time, and the picker pane starts
    # CLOSED -- if a previous hover left sub_show=true, sub_yuck holds that
    # picker and the pane would pop open on every right-click (sticky state).
    run(["eww", "--config", EWW_CONFIG_DIR, "update",
         "sub_left=%s" % ("true" if sub_left else "false"),
         "sub_right=%s" % ("false" if sub_left else "true"),
         "sub_show=false",
         "sub_yuck="])
    run(
        [
            "eww", "--config", EWW_CONFIG_DIR, "open",
            "--id", "ctx_menu",
            "--screen", str(pos["screen"]),
            "--arg", "widget=%s" % widget,
            "--arg", "monitor=%d" % monitor,
            "--arg", "pos_x=%d" % pos["x"],
            "--arg", "pos_y=%d" % pos["y"],
            "--arg", "menu_h=%dpx" % menu_h,
            "ctx_menu",
        ]
    )
    # Measure the REAL row offsets of the just-opened menu while the column is
    # still clean (no hover pane): submenu.py then anchors the picker to the
    # actual pixel geometry instead of the ROW_BTN/ROW_SEP model, whose guess
    # drifts wherever the desktop's label metrics differ. Detached + no wait:
    # if it lands after the first hover, that hover falls back to the model.
    subprocess.Popen(
        [sys.executable,
         os.path.join(SCRIPT_DIR, "measure_menu.py"),
         "--widget", widget],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    # The invisible keyboard daemon (scripts/input_daemon.py) reads the session
    # file: while it exists, ESC closes the popups. The menu position is stored
    # as well so the hover submenus (scripts/widgets/submenu.py) can anchor
    # themselves next to their parent row and clamp to the screen bottom, and
    # the opened dismiss-overlay ids so close_popup.py can take down every
    # instance on every monitor.
    session.set_session({
        "mode": "ctx",
        "x": int(pos["x"]),
        "y": int(pos["y"]),
        "screen": int(pos["screen"]),
        "menu_h": menu_h,
        "monitor_h": mon_h if mon_h else 0,
        "overlays": screens,
    })


if __name__ == "__main__":
    main()