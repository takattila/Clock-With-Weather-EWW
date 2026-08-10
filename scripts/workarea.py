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

The panel x/y are the EWW :x / :y offsets for the given :anchor, ready to be
written into eww.yuck by start.sh. The offsets are interpreted differently
depending on the compositor:
  - Wayland (gtk layer-shell): relative to the WORKAREA top-left (the taskbar
    is an exclusive zone that shifts the window down/right).
  - X11: ABSOLUTE screen coordinates (no layer-shell exclusive zone), so the
    top-anchored y offset must include the workarea origin (wy). The horizontal
    offset stays (ww - width)//2 because the "top right" anchor measures from
    the screen right edge (== workarea right) and the "top left" anchor is only
    used when workarea.x == 0.

Per-monitor mode (--per-monitor) reads a monitors JSON on stdin (from
scripts/monitors.py) and computes the panel geometry for every monitor:

  ./monitors.py | ./workarea.py --per-monitor [config_dir]

Output (stdout, JSON):
  {
    "compositor": "wayland" | "x11",
    "monitors": [
      {"index": 0, "name": "..", "width": .., "height": ..,
       "panel": {"x": .., "y": .., "width": .., "height": .., "anchor": ".."}},
      ...
    ],
    "heights": [ .. ]    # distinct panel heights (for panel.py)
  }

The taskbar workarea is read through XWayland on Wayland too (KDE exposes
_NET_WORKAREA there, see find_xwayland_env), so the primary monitor (the one
under the _NET_WORKAREA origin) keeps the taskbar inset on both compositors.
Secondary monitors use the symmetric-gap full-height geometry.

Usage: ./workarea.py [config_dir]
"""

import json
import os
import re
import subprocess
import sys

import yaml

PANEL_WIDTH = 250


def find_xwayland_env():
    """Locate DISPLAY/XAUTHORITY for the running XWayland instance.

    The panel geometry scripts may run without the X environment exported
    (start.sh is often launched from the desktop session), while the taskbar
    workarea (_NET_WORKAREA) is only readable through XWayland. The compositor
    exposes its Xwayland display + auth file on the command line, so scan /proc
    for it instead of requiring the session to export DISPLAY/XAUTHORITY.
    Existing environment values always win.
    """
    env = {}
    try:
        import glob
        markers = (b"kwin_wayland", b"Xwayland", b"mutter", b"gnome-shell", b"weston")
        for path in glob.glob("/proc/[0-9]*/cmdline"):
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            parts = data.split(b"\0")
            if not parts or not any(m in parts[0] for m in markers):
                continue
            argv = [p.decode("utf-8", "replace") for p in parts if p]
            for idx, arg in enumerate(argv):
                if arg == "--xwayland-display" and idx + 1 < len(argv):
                    env.setdefault("DISPLAY", argv[idx + 1])
                elif arg == "--xwayland-xauthority" and idx + 1 < len(argv):
                    env.setdefault("XAUTHORITY", argv[idx + 1])
    except Exception:
        pass
    return env


def get_net_workarea():
    for key in ("DISPLAY", "XAUTHORITY"):
        if key not in os.environ:
            discovered = find_xwayland_env().get(key)
            if discovered:
                os.environ[key] = discovered
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


def detect_compositor():
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("SWAYSOCK"):
        return "wayland"
    return "x11"


def compute_panel(screen, workarea, taskbar, gap, compositor):
    # NOTE: on KDE/wayland (gtk layer-shell) the :x/:y offsets are margins
    # measured relative to the WORKAREA (the taskbar is an exclusive zone that
    # shifts the window down/right): screen_position = workarea_edge + offset.
    # So the top-anchored y offset is just `gap` (workarea top is the taskbar
    # bottom), and a `taskbar_h + gap` bottom margin applies when the taskbar
    # sits on the bottom edge (workarea bottom == screen bottom).
    # On X11 (see eww display_backend.rs -> get_window_rectangle) there is no
    # layer-shell: the :x/:y are ABSOLUTE offsets from the monitor edge given by
    # the anchor, so a top-anchored panel must be offset below the taskbar by
    # workarea.y (wy). The horizontal offset stays (ww - width)//2 because the
    # "top right" anchor measures from the right edge (workarea right == screen
    # right) and the "top left" anchor is used only when workarea.x == 0.
    sw, sh = screen
    wx, wy, ww, wh = workarea
    width = PANEL_WIDTH
    height = max(wh - 2 * gap, 100)
    x11 = compositor == "x11"
    top_origin = wy if x11 else 0
    if taskbar == "bottom":
        anchor = "bottom right"
        x = 0
        y = (sh - (wy + wh)) + gap
    elif taskbar == "right":
        anchor = "top left"
        x = max((ww - width) // 2, 0)
        y = top_origin + gap
    elif taskbar == "left":
        anchor = "top right"
        x = max((ww - width) // 2, 0)
        y = top_origin + gap
    elif taskbar == "none":
        anchor = "top right"
        x = 0
        y = top_origin + gap
        height = max(sh - 2 * gap, 100)
    else:  # taskbar == "top"
        anchor = "top right"
        x = 0
        y = top_origin + gap
    return {"x": x, "y": y, "width": width, "height": height, "anchor": anchor}


def monitor_screen(m):
    return m["width"], m["height"]


def global_bounds(monitors):
    tw = max(m["x"] + m["width"] for m in monitors) if monitors else 0
    th = max(m["y"] + m["height"] for m in monitors) if monitors else 0
    return tw, th


def compute_per_monitor(monitors, gap, compositor):
    result = []
    workarea = get_net_workarea()
    global_screen = global_bounds(monitors)
    global_workarea = workarea if workarea else (0, 0, global_screen[0], global_screen[1])
    taskbar = detect_taskbar(global_screen, global_workarea)

    primary = 0
    if workarea:
        for i, m in enumerate(monitors):
            if m["x"] <= workarea[0] < m["x"] + m["width"] and m["y"] <= workarea[1] < m["y"] + m["height"]:
                primary = i
                break

    for i, m in enumerate(monitors):
        screen = monitor_screen(m)
        # The taskbar workarea is applied to the monitor that holds it on both
        # X11 and Wayland (KDE exposes _NET_WORKAREA through XWayland, see
        # find_xwayland_env). On Wayland eww's layer-shell offsets are relative
        # to that workarea (the exclusive zone shifts the window), so the panel
        # height must be the workarea height minus two gaps, otherwise the
        # bottom gap would be eaten by the taskbar's exclusive zone.
        if i == primary and workarea:
            local_workarea = (0, workarea[1], screen[0], workarea[3])
            panel = compute_panel(screen, local_workarea, taskbar, gap, compositor)
        else:
            panel = compute_panel(screen, (0, 0, screen[0], screen[1]), "none", gap, compositor)
        result.append(
            {
                "index": m["index"],
                "name": m["name"],
                "width": screen[0],
                "height": screen[1],
                "panel": panel,
            }
        )

    heights = sorted({r["panel"]["height"] for r in result}, reverse=True)
    return {"compositor": compositor, "monitors": result, "heights": heights}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    config_dir = os.path.abspath(args[-1] if args else os.getcwd())
    gap = load_gap(config_dir)

    if "--per-monitor" in sys.argv:
        compositor = detect_compositor()
        monitors = json.load(sys.stdin).get("monitors", [])
        print(json.dumps(compute_per_monitor(monitors, gap, compositor)))
        return

    screen = get_xrandr_resolution()
    workarea = get_net_workarea()
    real = screen is not None and workarea is not None
    if screen is None:
        screen = (1920, 1080)
    if workarea is None:
        workarea = (0, 0, screen[0], screen[1])

    compositor = detect_compositor()
    taskbar = detect_taskbar(screen, workarea)
    panel = compute_panel(screen, workarea, taskbar, gap, compositor)

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
        "compositor": compositor,
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
