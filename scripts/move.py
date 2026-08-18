#!/usr/bin/env python3
"""Move / Resize session launcher for the context menu.

Opens the full-monitor transparent overlay (move_overlay) with the rectangle
pre-set to the widget's current position/size, plus the draggable GTK control
panel (scripts/move_panel.py) with buttons (arrows, +/- zoom, Save, Cancel).

Unlike the old arrow-key version this script does NOT run an interactive loop:
it sets the overlay values, opens the overlay, starts the control panel and
returns immediately, so eww's command timeout (200ms) cannot kill it. The
buttons are handled by scripts/move_ctl.py; the arrow keys / +/- / ENTER / ESC
by the invisible evdev daemon (scripts/input_daemon.py); clicking anywhere
outside the panel (on the overlay) cancels the session.

The overlay values are written BEFORE opening move_overlay so the rectangle
renders at the widget's size right away (previously the overlay appeared with
the 100x100 defvar defaults until the update propagated -> looked like a
square).

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
CONFIG_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)

import session

MC_W = 200
MC_H = 250

# Natural (scale = 1.0) sizes, used to show the resize scale percentage.
CLOCK_W, CLOCK_H = 745, 250
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
    run(["eww", "--config", CONFIG_DIR] + list(args))


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

    # Close popups and any stale session windows; the control panel owns the
    # Move/Resize session.
    eww("close", "ctx_menu")
    eww("close", "dismiss_overlay")
    eww("close", "move_overlay")

    # Activate the keyboard daemon first (scripts/session.py starts it if
    # needed and writes generated/input_session.json): the daemon then maps
    # arrows / +/- / ENTER / ESC to move_ctl.py actions, and the control panel
    # watches the same file to know when to close.
    session.set_session({"mode": "move", "widget": args.widget, "monitor": args.monitor})

    # Regenerate the rectangle SVG with the widget's aspect ratio: the overlay
    # renders it via Pixbuf::from_file_at_size(move_w, move_h), which FITS the
    # image into that box preserving the aspect ratio. A square SVG would
    # therefore always render as a square regardless of move_w/move_h.
    run(["python3", os.path.join(SCRIPT_DIR, "gen_rect_svg.py"), "--width", str(w), "--height", str(h)])

    # Set the overlay values BEFORE opening the window so the rectangle has the
    # correct size/position on the first frame.
    base_w = CLOCK_W if args.widget == "clock" else PANEL_WIDTH
    pct = int(round(w / base_w * 100)) if base_w else 100
    eww(
        "update",
        "move_x=%d" % int(round(rect["left"])),
        "move_y=%d" % int(round(rect["top"])),
        "move_w=%d" % w,
        "move_h=%d" % h,
        "move_pct=%d" % pct,
    )
    eww(
        "open", "--id", "move_overlay", "--screen", str(args.monitor),
        "--arg", "screen=%d" % args.monitor,
        "--arg", "widget=%s" % args.widget,
        "--arg", "monitor=%d" % args.monitor,
        "move_overlay",
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
