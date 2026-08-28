#!/usr/bin/env python3
"""Weather-settings session launcher for the context menu.

Opens the draggable GTK settings form (scripts/weather_panel.py) CENTERED ON
the monitor the menu was raised on (same centering as the About dialog), in
contrast to the Move/Resize and Panel-gap panels which hug the widget.

The form edits the global `weather:` settings (city, language_code, lang,
units, api_url -> config.local.yaml via config_set.py, api_key -> the
git-ignored .api_key file). Editing only changes the DRAFT values in the
window; the Save button validates everything, writes the changed fields in
ONE go, immediately refreshes the on-screen weather (weather.py + `eww
update weather_info=...`, so the change needs no 10-minute defpoll) and then
closes. The Reset button removes the local weather overrides (so the
config.yaml / weather-theme values take effect again) and also refreshes and
closes. Cancel discards and closes.

Like move.py / gap_ctl.py this script does NOT run an interactive loop: it
resolves the monitor the menu was opened on, centers the form on it (the
same monitors.py geometry + clamp as about_win.py), closes the context menu
and returns immediately, so eww's command timeout (200ms) cannot kill it.
ESC / click-outside / Cancel / Reset / Save quit the session through
close_popup.py (the invisible keyboard daemon maps ESC while the session file
exists).

The per-monitor dismiss layers deliberately STAY OPEN like in Move/Resize /
Panel-gap: they are the click-outside-to-cancel surface for the whole session.

Usage:
  ./weather_ctl.py --widget clock --monitor 0
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

POSE_W = 300
POSE_H = 380


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

    # Center the form on the monitor the menu was raised on, EXACTLY like the
    # About dialog (about_win.py): monitor geometry from monitors.py, the
    # center clamped to the frame. The X11 absolute screen origin is added so
    # win.move() (absolute coordinates) lands in the frame center.
    monitors = load_monitors()
    mon = next((m for m in monitors if m.get("index") == args.monitor), None)
    if mon is None:
        mon = {"index": args.monitor, "x": 0, "y": 0, "width": 1920, "height": 1080}
    frame_w, frame_h = mon["width"], mon["height"]
    px = clamp((frame_w - POSE_W) // 2, 0, max(0, frame_w - POSE_W))
    py = clamp((frame_h - POSE_H) // 2, 0, max(0, frame_h - POSE_H))

    # Close the context menu; the per-monitor dismiss layers stay open (the
    # click-outside-to-cancel surface), like in the Move/Resize session.
    eww("close", "ctx_menu")
    eww("close", "dismiss_overlay")

    # Activate the keyboard daemon first and mark the session: while it exists
    # the daemon maps ESC to close_popup.py and the GTK form keeps running.
    overlays = read_session().get("overlays") or connected_screens()
    session.set_session({
        "mode": "weather",
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
            sys.executable, os.path.join(SCRIPT_DIR, "weather_panel.py"),
            "--monitor", str(args.monitor),
            "--x", str(px), "--y", str(py),
            "--frame-w", str(frame_w), "--frame-h", str(frame_h),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True, cwd=CONFIG_DIR,
    )


if __name__ == "__main__":
    main()