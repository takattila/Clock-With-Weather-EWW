#!/usr/bin/env python3
"""Raindrop-settings session launcher for the context menu (v5.0.0).

Opens the draggable GTK form (scripts/move/rain_panel.py) CENTERED ON the
monitor the menu was raised on, in the middle of the screen - the same
centering as the Weather settings form and the About dialog.

The form edits the global `weather.rain.*` settings (enabled, auto, count,
speed, opacity -> config.local.yaml via config_set.py), draft-only like the
Weather settings form: Save validates every field and commits the changed keys
in one pass (so the config watcher reloads the widget once instead of on every
slider tick) and closes; Reset drops the local overrides so the config.yaml
defaults win again; Cancel / ESC / click-outside discard. scripts/core/rain.py
polls the config every 2 s, so the new values hit the live rain layer right
after Save.

Like move.py / weather_ctl.py this script does NOT run an interactive loop: it
resolves the monitor, centers the form, closes the context menu and returns
immediately, so eww's command timeout (200ms) cannot kill it. ESC /
click-outside / Cancel / Reset / Save quit through close_popup.py.

Usage:
  ./rain_ctl.py --widget clock --monitor 0
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
import monitors as monmod

# Must match PANEL_W / PANEL_H in rain_panel.py (the measured content height).
POSE_W = 320
POSE_H = 343


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


def clamp(value, lo, hi):
    return max(lo, min(value, hi))


def load_monitors():
    """Monitor list from scripts/core/monitors.py (index, x, y, width, height)."""
    out = run(
        ["python3", os.path.join(CR_DIR, "core", "monitors.py")],
        capture=True,
    )
    try:
        return json.loads(out).get("monitors", [])
    except Exception:
        return []


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

    # Center the form in the middle of the monitor the menu was raised on, the
    # same way weather_ctl.py / about_win.py do it: geometry from monitors.py,
    # the center clamped to the frame, plus the X11 absolute screen origin for
    # win.move() (Wayland positions via the layer-shell margin instead).
    monitors = load_monitors()
    mon = next((m for m in monitors if m.get("index") == args.monitor), None)
    if mon is None:
        mon = {"index": args.monitor, "x": 0, "y": 0, "width": 1920, "height": 1080}
    frame_w, frame_h = mon["width"], mon["height"]
    win_h = monmod.adaptive_window_height(
        monitors, POSE_H, monmod.get_net_workarea())
    px = clamp((frame_w - POSE_W) // 2, 0, max(0, frame_w - POSE_W))
    py = clamp((frame_h - win_h) // 2, 0, max(0, frame_h - win_h))

    # Close the context menu, then the dismiss layers - exactly what
    # weather_ctl.py does. The per-monitor overlays ctx.py opened stay mapped
    # (they are instances named dismiss_overlay_<N>; this closes the legacy
    # single-instance name), and they are what makes a click OUTSIDE the panel
    # run close_popup.py, so the panel is closable four ways: click outside,
    # ESC, Cancel and Save/Reset.
    eww("close", "ctx_menu")
    eww("close", "dismiss_overlay")

    # Mark the session first: while it exists the keyboard daemon maps ESC to
    # close_popup.py and the GTK form keeps running.
    overlays = read_session().get("overlays") or connected_screens()
    session.set_session({
        "mode": "rain",
        "widget": args.widget,
        "monitor": args.monitor,
        "overlays": overlays,
    })

    WAYLAND = "WAYLAND_DISPLAY" in os.environ \
        and os.environ.get("GDK_BACKEND", "wayland") != "x11"
    if not WAYLAND:
        px += mon["x"]
        py += mon["y"]
    subprocess.Popen(
        [
            sys.executable, os.path.join(SCRIPT_DIR, "rain_panel.py"),
            "--monitor", str(args.monitor),
            "--x", str(px), "--y", str(py),
            "--frame-w", str(frame_w), "--frame-h", str(frame_h),
            "--win-h", str(win_h),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True, cwd=CONFIG_DIR,
    )


if __name__ == "__main__":
    main()
