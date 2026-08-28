#!/usr/bin/env python3
"""Panel-gap session launcher for the context menu.

Opens the draggable GTK control panel (scripts/gap_panel.py) NEXT TO the
system-monitor PANEL widget (regardless of which widget's menu was opened) on
the monitor the menu was raised on, exactly like the Move/Resize panel: the
panel_position() helper picks the horizontal side with more free space and
keeps it GAP px away from the panel's edge - the SAME GAP px the Move/Resize
panel keeps when it is raised on the system monitor panel (both launchers
call panel_position(rect, 200, 320, 10)). The /+/-/ buttons and the editable
fields only change the DRAFT values in the control panel; the Save button
writes the changed sides of the global `panel.gap` (the spacing between the
system-monitor panel and the screen/taskbar edges) through config_set.py, so
the config watcher relays out the panel exactly once.

Like move.py this script does NOT run an interactive loop: it resolves the
panel rectangle, positions the panel just outside its edge (panel_pos.py),
closes the context menu and returns immediately, so eww's command timeout
(200ms) cannot kill it. The buttons live in the GTK panel itself; ESC /
click-outside / Close quit the session through close_popup.py (the invisible
keyboard daemon maps ESC while the session file exists).

The per-monitor dismiss layers deliberately STAY OPEN like in Move/Resize:
they are the click-outside-to-cancel surface for the whole session (outside
click -> close_popup.py -> closes the recorded layers and clears the session
file -> the GTK panel quits when it disappears).

Usage:
  ./gap_ctl.py --widget clock --monitor 0
"""

import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CR_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/
# scripts/move/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
sys.path.insert(0, os.path.join(CR_DIR, "core"))

import session
from panel_pos import panel_position

POSE_W = 200
POSE_H = 320
GAP = 10  # gap between the widget and the control panel


def run(cmd, capture=False, timeout=15):
    try:
        if capture:
            return subprocess.check_output(
                cmd, stderr=subprocess.DEVNULL, text=True, timeout=timeout,
            ).strip()
        subprocess.run(
            cmd, check=False, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout,
        )
        return ""
    except Exception:
        return ""


def eww(*args):
    run(["eww", "--config", EWW_CONFIG_DIR] + list(args))


def widget_rect(widget, monitor):
    out = run(
        ["python3", os.path.join(SCRIPT_DIR, "widget_rect.py"),
         "--widget", widget, "--monitor", str(monitor)],
        capture=True,
    )
    try:
        return json.loads(out)
    except Exception:
        sys.exit("ERROR: widget_rect.py failed:\n%s" % out)


def read_session():
    try:
        with open(SESSION_FILE) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def connected_screens():
    """All connected monitor indices (best effort)."""
    out = run(
        ["python3", os.path.join(CR_DIR, "core", "monitors.py")],
        capture=True,
    )
    try:
        return sorted(int(m["index"])
                      for m in json.loads(out).get("monitors", []))
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", required=True, choices=["clock", "panel"])
    ap.add_argument("--monitor", type=int, default=0)
    args = ap.parse_args()

    # The control panel always opens NEXT TO the system-monitor PANEL widget
    # (it is the thing the gap config affects), on the monitor the menu was
    # raised on - even when the menu was opened on the clock widget.
    rect = widget_rect("panel", args.monitor)
    frame_w, frame_h = rect["frame_w"], rect["frame_h"]

    # Close the context menu; the per-monitor dismiss layers stay open (the
    # click-outside-to-cancel surface), like in the Move/Resize session.
    eww("close", "ctx_menu")
    eww("close", "dismiss_overlay")

    # Activate the keyboard daemon first and mark the session: while it exists
    # the daemon maps ESC to close_popup.py and the GTK panel keeps running.
    overlays = read_session().get("overlays") or connected_screens()
    session.set_session({
        "mode": "gap",
        "widget": "panel",
        "monitor": args.monitor,
        "overlays": overlays,
    })

    # Panel just outside the panel widget (see move.py): frame-local
    # coordinates, with the X11 absolute screen origin added.
    px, py = panel_position(rect, POSE_W, POSE_H, GAP)
    WAYLAND = "WAYLAND_DISPLAY" in os.environ \
        and os.environ.get("GDK_BACKEND", "wayland") != "x11"
    if not WAYLAND:
        px += int(round(rect["abs_x"] - rect["left"]))
        py += int(round(rect["abs_y"] - rect["top"]))
    subprocess.Popen(
        [
            sys.executable, os.path.join(SCRIPT_DIR, "gap_panel.py"),
            "--monitor", str(args.monitor),
            "--x", str(px), "--y", str(py),
            "--frame-w", str(frame_w), "--frame-h", str(frame_h),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True, cwd=CONFIG_DIR,
    )


if __name__ == "__main__":
    main()