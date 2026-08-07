#!/usr/bin/env python3
"""
WM-independent workarea detection and panel geometry computation.

The panel must stay inside the taskbar-free area (_NET_WORKAREA) on any window
manager (KDE, GNOME, XFCE, i3, ...), and it must be inset from the taskbar and
from the opposite screen edge by the **same gap** (Req 2), so the free spacing
stays symmetric no matter where the taskbar sits:

  taskbar at top    -> gap(panel top -> taskbar)   == gap(panel bottom -> screen edge)
  taskbar at bottom -> gap(panel bottom -> taskbar) == gap(panel top -> screen edge)
  taskbar at right  -> gap(panel -> taskbar)       == gap(panel -> left screen edge)
                       (the panel moves to the left edge)
  taskbar at left   -> gap(panel -> taskbar)       == gap(panel -> right screen edge)

The gap value comes from config.yaml -> panel.gap (default: 16 px). The panel
width is fixed at 250 px; the height is the workarea height minus the two gaps.

Output (stdout, JSON):
  {
    "screen":     {"width": .., "height": ..},
    "workarea":   {"x": .., "y": .., "width": .., "height": ..},
    "taskbar":    "top" | "bottom" | "left" | "right" | "none",
    "panel":      {"x": .., "y": .., "width": .., "height": .., "anchor": ".."},
    "panel_gap":  ..,
    "real_workarea": bool   # False when the X display was unreachable
  }

The panel x/y are the EWW :x / :y offsets (layer-shell margins) for the given
:anchor, ready to be written into eww.yuck by start.sh.

Usage: ./workarea.py [config_dir]
"""

import json
import os
import re
import subprocess
import sys

import yaml

PANEL_WIDTH = 250


def get_net_workarea():
    try:
        out = subprocess.check_output(
            ["xprop", "-root", "_NET_WORKAREA"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
        m = re.search(r"=\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)", out)
        if m:
            x, y, w, h = (int(v) for v in m.groups())
            if w > 0 and h > 0:
                return x, y, w, h
    except Exception:
        pass
    return None


def get_xrandr_resolution():
    try:
        out = subprocess.check_output(
            ["xrandr"], stderr=subprocess.DEVNULL, text=True, timeout=3
        )
        m = re.search(r"current\s+(\d+)\s*x\s*(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


def load_gap(config_dir):
    try:
        with open(os.path.join(config_dir, "config.yaml"), "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        panel = cfg.get("panel") or {}
        return int(panel.get("gap", 16))
    except Exception:
        return 16


def detect_taskbar(screen, workarea):
    sw, sh = screen
    wx, wy, ww, wh = workarea
    if wy > 0 and wx == 0 and ww == sw:
        return "top"
    if wy + wh < sh and wx == 0 and ww == sw:
        return "bottom"
    if wx + ww < sw:
        return "right"
    if wx > 0:
        return "left"
    return "none"


def compute_panel(screen, workarea, taskbar, gap):
    # NOTE: on KDE/wayland (gtk layer-shell) the :x/:y offsets are relative to
    # the WORKAREA top-left (the taskbar is an exclusive zone that shifts the
    # window down/right), i.e. screen_position = workarea_offset + offset.
    # So the top-anchored y offset is just `gap` (workarea top is the taskbar
    # bottom), and a `taskbar_h + gap` bottom margin only applies when the
    # taskbar sits on the bottom edge (workarea bottom == screen bottom).
    sw, sh = screen
    wx, wy, ww, wh = workarea
    width = PANEL_WIDTH
    height = max(wh - 2 * gap, 100)
    if taskbar == "bottom":
        anchor = "bottom right"
        x = 0
        y = (sh - (wy + wh)) + gap
    elif taskbar == "right":
        anchor = "top left"
        x = max((ww - width) // 2, 0)
        y = gap
    elif taskbar == "left":
        anchor = "top right"
        x = max((ww - width) // 2, 0)
        y = gap
    elif taskbar == "none":
        anchor = "top right"
        x = 0
        y = gap
        height = max(sh - 2 * gap, 100)
    else:  # taskbar == "top"
        anchor = "top right"
        x = 0
        y = gap
    return {"x": x, "y": y, "width": width, "height": height, "anchor": anchor}


def main():
    config_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    gap = load_gap(config_dir)

    screen = get_xrandr_resolution()
    workarea = get_net_workarea()
    real = screen is not None and workarea is not None
    if screen is None:
        screen = (1920, 1080)
    if workarea is None:
        workarea = (0, 0, screen[0], screen[1])

    taskbar = detect_taskbar(screen, workarea)
    panel = compute_panel(screen, workarea, taskbar, gap)

    # PANEL_HEIGHT env override still wins (used by panel.py to size the charts).
    env_override = os.environ.get("PANEL_HEIGHT") or os.environ.get("EWW_PANEL_HEIGHT")
    if env_override:
        panel["height"] = int(env_override)

    result = {
        "screen": {"width": screen[0], "height": screen[1]},
        "workarea": {
            "x": workarea[0],
            "y": workarea[1],
            "width": workarea[2],
            "height": workarea[3],
        },
        "taskbar": taskbar,
        "panel": panel,
        "panel_gap": gap,
        "real_workarea": real,
    }
    print(json.dumps(result))
    print(
        "screen=%dx%d workarea=%d,%d %dx%d taskbar=%s gap=%d panel=%s %dx%d+%d+%d"
        % (
            screen[0],
            screen[1],
            workarea[0],
            workarea[1],
            workarea[2],
            workarea[3],
            taskbar,
            gap,
            panel["anchor"],
            panel["width"],
            panel["height"],
            panel["x"],
            panel["y"],
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
