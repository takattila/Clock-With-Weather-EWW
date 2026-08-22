#!/usr/bin/env python3
"""Move / Resize session launcher for the context menu.

Opens the full-monitor transparent rectangle overlay (scripts/move_rect.py)
with the rectangle pre-set to the widget's current position/size, plus the
draggable GTK control panel (scripts/move_panel.py) with buttons (arrows, +/-
zoom, Save, Cancel).

Unlike the old arrow-key version this script does NOT run an interactive loop:
it sets the overlay values, starts the rectangle window + control panel and
returns immediately, so eww's command timeout (200ms) cannot kill it. The
buttons are handled by scripts/move_ctl.py; the arrow keys / +/- / ENTER / ESC
by the invisible evdev daemon (scripts/input_daemon.py); dragging/resizing the
rectangle with the mouse directly (scripts/move_rect.py); clicking anywhere
outside the rectangle cancels the session.

The overlay values are written BEFORE opening the windows so the rectangle
renders at the widget's size right away (previously the overlay appeared with
the 100x100 defvar defaults until the update propagated -> looked like a
square). The rectangle window is spawned before the control panel so the panel
stacks above it and stays clickable.

Usage:
  ./move.py --widget clock --monitor 0 --mode move
  ./move.py --widget panel --monitor 1 --mode resize
"""

import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/
# scripts/move/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
sys.path.insert(0, os.path.join(SCRIPTS_DIR, "core"))

import session

MC_W = 200
MC_H = 250

# Natural (scale = 1.0) panel width. The clock's natural width is dynamic
# (ends at the city name) and comes from widget_rect.py ("natural_w").
PANEL_WIDTH = 250


def run(cmd, capture=False):
    try:
        if capture:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ""
    except Exception:
        return ""


def eww(*args):
    run(["eww", "--config", EWW_CONFIG_DIR] + list(args))


def clamp(value, lo, hi):
    return max(lo, min(value, hi))


def widget_rect(widget, monitor):
    out = run(
        ["python3", os.path.join(SCRIPT_DIR, "widget_rect.py"), "--widget", widget, "--monitor", str(monitor)],
        capture=True,
    )
    try:
        return json.loads(out)
    except Exception:
        sys.exit("ERROR: widget_rect.py failed:\n%s" % out)


def cursor_position():
    out = run(["xdotool", "getmouselocation"], capture=True)
    m = {}
    for part in out.split():
        if ":" in part:
            k, v = part.split(":", 1)
            m[k] = v
    try:
        return int(m.get("x", 0)), int(m.get("y", 0))
    except ValueError:
        return 0, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", required=True, choices=["clock", "panel"])
    ap.add_argument("--monitor", type=int, default=0)
    ap.add_argument("--mode", required=True, choices=["move", "resize"])
    args = ap.parse_args()

    rect = widget_rect(args.widget, args.monitor)
    frame_w, frame_h = rect["frame_w"], rect["frame_h"]
    w = int(round(rect["width"]))
    h = int(round(rect["height"]))

    # Close popups and any stale session windows; the rectangle window + the
    # control panel own the Move/Resize session.
    eww("close", "ctx_menu")
    eww("close", "dismiss_overlay")

    # Activate the keyboard daemon first (scripts/session.py starts it if
    # needed and writes generated/input_session.json): the daemon then maps
    # arrows / +/- / ENTER / ESC to move_ctl.py actions, and the rectangle +
    # control panel watch the same file to know when to close.
    session.set_session({"mode": "move", "widget": args.widget, "monitor": args.monitor})

    # Set the overlay values BEFORE opening the windows so the rectangle has the
    # correct size/position on the first frame.
    if args.widget == "clock":
        base_w = rect["natural_w"]
        base_h = rect["natural_h"]
    else:
        base_w = PANEL_WIDTH
        scale = w / base_w if base_w else 1.0
        base_h = int(round(h / scale)) if scale else h
    pct = int(round(w / base_w * 100)) if base_w else 100
    eww(
        "update",
        "move_x=%d" % int(round(rect["left"])),
        "move_y=%d" % int(round(rect["top"])),
        "move_w=%d" % w,
        "move_h=%d" % h,
        "move_pct=%d" % pct,
    )

    # Rectangle overlay first, so the control panel stacks above it. base_w/
    # base_h are the NATURAL (scale 1.0) sizes, used by the mouse resize to
    # keep the aspect ratio; ox/oy is the frame's top-left inside the monitor
    # (workarea vs monitor on Wayland, 0/0 on X11).
    subprocess.Popen(
        [
            sys.executable, os.path.join(SCRIPT_DIR, "move_rect.py"),
            "--widget", args.widget,
            "--monitor", str(args.monitor),
            "--x", str(int(round(rect["left"]))),
            "--y", str(int(round(rect["top"]))),
            "--w", str(w), "--h", str(h),
            "--ox", str(int(round(rect["frame_ox"]))),
            "--oy", str(int(round(rect["frame_oy"]))),
            "--base-w", str(int(base_w)), "--base-h", str(int(base_h)),
            "--frame-w", str(frame_w), "--frame-h", str(frame_h),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True, cwd=CONFIG_DIR,
    )

    # Control panel near the cursor (the user just clicked the menu button);
    # fall back to the widget's corner when the cursor cannot be read. It is a
    # GTK window (scripts/move_panel.py) so it can be dragged around with the
    # mouse; its position is clamped to the monitor frame.
    px, py = cursor_position()
    if px <= 0 and py <= 0:
        px, py = int(round(rect["left"])), int(round(rect["top"]))
    px = clamp(px, 0, max(0, frame_w - MC_W))
    py = clamp(py, 0, max(0, frame_h - MC_H))
    subprocess.Popen(
        [
            sys.executable, os.path.join(SCRIPT_DIR, "move_panel.py"),
            "--widget", args.widget,
            "--monitor", str(args.monitor),
            "--x", str(px), "--y", str(py),
            "--frame-w", str(frame_w), "--frame-h", str(frame_h),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True, cwd=CONFIG_DIR,
    )


if __name__ == "__main__":
    main()
