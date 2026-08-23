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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# scripts/widgets/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

import session


def run(cmd, capture=False):
    try:
        if capture:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ""
    except Exception:
        return ""


def list_monitor_indices():
    """Connected monitor indices from scripts/core/monitors.py ([] on failure)."""
    out = run(
        ["python3", os.path.join(CONFIG_DIR, "scripts", "core", "monitors.py")],
        capture=True,
    )
    try:
        data = json.loads(out)
        return sorted(int(m["index"]) for m in data.get("monitors", []))
    except Exception:
        return []


def widget_visible_rect(widget, monitor):
    """Absolute visible rectangle {x,y,w,h} or None (widget_rect failed)."""
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


def collect_rects(screens):
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

    # Ownership forwarding (see choose_widget): the click may have been
    # delivered by the OTHER widget's transparent canvas overlapping this
    # one -- redirect the menu to whichever widget is visibly under the
    # cursor so its Move/Resize rectangle matches what the user clicked.
    widget, monitor = args.widget, args.monitor
    try:
        screens = list_monitor_indices()
        if screens:
            widget, monitor = choose_widget(
                args.widget, args.monitor, cursor_position(), collect_rects(screens))
    except Exception:
        widget, monitor = args.widget, args.monitor

    out = run(
        ["python3", os.path.join(CONFIG_DIR, "scripts", "move", "menu_pos.py"),
         "--widget", widget, "--monitor", str(monitor)],
        capture=True,
    )
    try:
        pos = json.loads(out)
    except Exception:
        sys.exit("ERROR: menu_pos.py failed:\n%s" % out)

    # Open the transparent dismiss layers FIRST (so the menu stacks above
    # them): one per connected monitor, so clicking anywhere on ANY screen —
    # not just the menu's own one — closes the popups. Then the context menu.
    # A leftover submenu from an earlier session is closed as well.
    screens = list_monitor_indices() or [int(pos["screen"])]
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
    run(
        [
            "eww", "--config", EWW_CONFIG_DIR, "open",
            "--id", "ctx_menu",
            "--screen", str(pos["screen"]),
            "--arg", "widget=%s" % widget,
            "--arg", "monitor=%d" % monitor,
            "--arg", "pos_x=%d" % pos["x"],
            "--arg", "pos_y=%d" % pos["y"],
            "ctx_menu",
        ]
    )
    # The invisible keyboard daemon (scripts/input_daemon.py) reads the session
    # file: while it exists, ESC closes the popups. The menu position is stored
    # as well so the hover submenus (scripts/widgets/submenu.py) can anchor
    # themselves next to their parent row, and the opened dismiss-overlay ids
    # so close_popup.py can take down every instance on every monitor.
    session.set_session({
        "mode": "ctx",
        "x": int(pos["x"]),
        "y": int(pos["y"]),
        "screen": int(pos["screen"]),
        "overlays": screens,
    })


if __name__ == "__main__":
    main()