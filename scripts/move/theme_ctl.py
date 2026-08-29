#!/usr/bin/env python3
"""Theme-editor session launcher for the context menu.

Opens the draggable GTK theme editor (scripts/move/theme_panel.py) CENTERED
ON the monitor the menu was raised on (same centering as the About dialog
and the Weather-settings form). The editor edits every field an appearance
definition carries (theme, icon set/tint/transparency, fonts, background,
chart colors/glow, panel background/gradient, corner radius).

Editing only changes the DRAFT values in the window. The footer buttons
commit it:
  * Save    -> writes the whole normalized appearance map + system.corner_radius
               inline into the git-ignored config.local.yaml (the shipped
               theme files stay untouched; the watcher reloads the widget
               live) and closes,
  * Save As -> asks for a name, creates assets/themes/appearance/<name>/
               appearance.yaml (minimalized like the checked-in themes),
               activates it and closes,
  * Preview -> applies the DRAFT to the LIVE widget right now (colors, fonts,
               radius, glow, panel + re-tinted icons) WITHOUT saving;
               config.local.yaml stays untouched, so only Save makes it
               permanent (theme_preview.py). Un-saved previews revert on
               Reset / Cancel / editor close,
  * Reset   -> refills the form from the loaded source (and reverts any
               un-saved Preview),
  * Cancel  -> discards (reverting any un-saved Preview) and closes.

Like weather_ctl.py this script does NOT run an interactive loop: it resolves
the monitor the menu was opened on, centers the form on it, closes the context
menu and returns immediately, so eww's command timeout (200ms) cannot kill it.
ESC / click-outside / the footer buttons quit the session through
close_popup.py (the invisible keyboard daemon maps ESC while the session file
exists).

The per-monitor dismiss layers deliberately STAY OPEN like in Move/Resize /
Weather settings (the click-outside-to-cancel surface for the whole session).

The window HEIGHT is adapted so it also fits the smallest connected screen
(screen height minus taskbar; see monitors.adaptive_window_height) and the
editor is centered using that resolved height, so it can be dragged onto any
monitor.

Usage:
  ./theme_ctl.py --widget clock --monitor 0
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

POSE_W = 560
POSE_H = 760


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

    monitors = load_monitors()
    mon = next((m for m in monitors if m.get("index") == args.monitor), None)
    if mon is None:
        mon = {"index": args.monitor, "x": 0, "y": 0, "width": 1920, "height": 1080}
    frame_w, frame_h = mon["width"], mon["height"]
    # Adapt the window height so it also fits the smallest connected screen
    # (its usable height minus the taskbar) -> it can be dragged to every
    # monitor. Centering uses the RESOLVED height, not the natural POSE_H.
    win_h = monmod.adaptive_window_height(
        monitors, POSE_H, monmod.get_net_workarea())
    px = clamp((frame_w - POSE_W) // 2, 0, max(0, frame_w - POSE_W))
    py = clamp((frame_h - win_h) // 2, 0, max(0, frame_h - win_h))

    # Close the context menu; the per-monitor dismiss layers stay open (the
    # click-outside-to-cancel surface), like the other GTK panels.
    eww("close", "ctx_menu")
    eww("close", "dismiss_overlay")

    overlays = read_session().get("overlays") or connected_screens()
    session.set_session({
        "mode": "theme",
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
            sys.executable, os.path.join(SCRIPT_DIR, "theme_panel.py"),
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