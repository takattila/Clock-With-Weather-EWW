#!/usr/bin/env python3
"""Absolute screen rectangle of a widget on a monitor.

Used by the context menu actions (scripts/ctx.py / move.py) to draw the
move/resize overlay and to position the menu. The geometry follows the same
rules eww 0.5.0 uses (crates/eww/src/app.rs::get_window_rectangle), so the
reported rectangle matches what is actually on screen:

  x = frame.origin.x + offset_x + align_x(width, frame.width)
  y = frame.origin.y + offset_y + align_y(height, frame.height)

where the "frame" is:
  - Wayland: the taskbar-free WORKAREA (layer-shell margins are relative to
    the usable area left by exclusive zones, see gtk-layer-shell),
  - X11:     the MONITOR rectangle (eww positions windows with absolute
    coordinates there, no exclusive zone).

The clock widget is positioned with a "top left" anchor: its offsets are the
computed top-left corner (conky-style alignment + pixel offsets, resolved
per-monitor from config.yaml). The panel geometry (offsets/anchor/size) comes
from scripts/workarea.py --per-monitor via .layout.json, with the width/height
multiplied by the panel scale.

Usage:
  ./widget_rect.py --widget clock --monitor 0
  ./widget_rect.py --widget panel --monitor 1

Output (stdout, JSON):
  {
    "x": eww x offset (workarea-local on Wayland, monitor-local on X11),
    "y": eww y offset,
    "abs_x": absolute screen top-left x,
    "abs_y": absolute screen top-left y,
    "width": widget width (scaled),
    "height": widget height (scaled),
    "natural_w": natural (scale 1.0) width,
    "natural_h": natural (scale 1.0) height,
    "anchor": window anchor ("top left" for the clock; panel anchor on X11)
  }
"""

import json
import os
import re
import subprocess
import sys

import yaml

try:
    from PIL import ImageFont
except Exception:
    ImageFont = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/
# scripts/move/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
LAYOUT_FILE = os.path.join(CONFIG_DIR, ".layout.json")
# The clock widget's natural height equals the visible background (.widget-bg)
# height, so the Move/Resize rectangle matches the widget bottom exactly.
CLOCK_H = 247
PANEL_WIDTH = 250

# The clock widget's natural width is dynamic: it hugs the content and ends
# right after the city name (the rightmost element). Layout constants:
CITY_X = 465            # .city-label margin-left
CITY_FONT_SIZE = 30
CITY_FONT_BOLD = True
# Rightmost FIXED element: .stat-feels-label (x=550, font 15, e.g. "23°C").
RIGHT_FIXED_END = 584
CLOCK_PAD = 8           # small gap after the city name for the bg corner


def measure_text(text, size, bold=False):
    """Rendered width (px) of `text` at `size` in Noto Sans.

    Uses the system Noto Sans Bold for the bold labels, falling back to the
    repo-bundled Noto Sans Regular (close enough; eww synthesizes bold).
    """
    if ImageFont is not None:
        paths = []
        if bold:
            paths.append("/usr/share/fonts/noto/NotoSans-Bold.ttf")
        paths.append(os.path.join(CONFIG_DIR, "fonts", "NotoSans-Regular.ttf"))
        for path in paths:
            try:
                return ImageFont.truetype(path, size).getlength(text)
            except Exception:
                continue
    return len(text) * size * 0.6


def clock_natural_size(monitor_index):
    """Natural (scale = 1.0) clock window size, ending at the city name."""
    city = config_value("city", monitor_index) or "Budapest"
    city_w = measure_text(city, CITY_FONT_SIZE, bold=CITY_FONT_BOLD)
    natural_w = max(CITY_X + city_w, RIGHT_FIXED_END) + CLOCK_PAD
    return int(round(natural_w)), CLOCK_H


def _run(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
    except Exception:
        return ""


def get_monitors():
    out = _run(["python3", os.path.join(SCRIPTS_DIR, "core", "monitors.py")])
    if not out:
        sys.exit("ERROR: monitors.py failed")
    data = json.loads(out)
    return data


def get_workarea():
    """Global _NET_WORKAREA (absolute coords), or None when unavailable.

    Reuses scripts/workarea.py, which locates the XWayland display/auth when
    the session does not export DISPLAY (KDE/Plasma on Wayland).
    """
    try:
        sys.path.insert(0, os.path.join(SCRIPTS_DIR, "core"))
        import workarea as _wa
        return _wa.get_net_workarea()
    except Exception:
        return None


def config_value(key, monitor=None):
    cmd = ["python3", os.path.join(SCRIPTS_DIR, "core", "config.py"), "--key", key]
    if monitor is not None:
        cmd += ["--monitor", str(monitor)]
    return _run(cmd)


def split_anchor(alignment):
    """Turn 'top_right' / 'middle_middle' ... into (h, v) with h/v in
    left|center|right / top|middle|bottom."""
    if not alignment:
        return "center", "middle"
    if "left" in alignment:
        h = "left"
    elif "right" in alignment:
        h = "right"
    else:
        h = "center"
    if "top" in alignment:
        v = "top"
    elif "bottom" in alignment:
        v = "bottom"
    else:
        v = "middle"
    return h, v


def align_pos(size, frame_size, alignment):
    if alignment == "left" or alignment == "top":
        return 0
    if alignment == "right" or alignment == "bottom":
        return frame_size - size
    return (frame_size - size) / 2


def clock_rect(monitor, compositor, workarea, monitor_index):
    scale = float(config_value("scale", monitor_index) or 1.0)
    natural_w, natural_h = clock_natural_size(monitor_index)
    w = natural_w * scale
    h = natural_h * scale
    alignment = config_value("alignment") or "middle_middle"
    pos_x = int(float(config_value("position_x", monitor_index) or 0))
    pos_y = int(float(config_value("position_y", monitor_index) or 0))

    mx, my, mw, mh = monitor["x"], monitor["y"], monitor["width"], monitor["height"]
    if compositor == "wayland" and workarea:
        fx, fy, fw, fh = workarea
        frame_x, frame_y = max(fx, mx), max(fy, my)
        frame_w = min(fx + fw, mx + mw) - frame_x
        frame_h = min(fy + fh, my + mh) - frame_y
    else:
        frame_x, frame_y, frame_w, frame_h = mx, my, mw, mh

    h_align, v_align = split_anchor(alignment)
    top_left_x = align_pos(w, frame_w, h_align) + pos_x
    top_left_y = align_pos(h, frame_h, v_align) + pos_y
    return {
        "x": top_left_x,
        "y": top_left_y,
        "left": top_left_x,
        "top": top_left_y,
        "abs_x": frame_x + top_left_x,
        "abs_y": frame_y + top_left_y,
        "width": int(round(w)),
        "height": int(round(h)),
        "natural_w": int(natural_w),
        "natural_h": int(natural_h),
        "frame_w": int(frame_w),
        "frame_h": int(frame_h),
        # ox/oy are the frame's top-left inside the Move/Resize rectangle
        # window's own coordinate space. On Wayland that window is a layer-shell
        # surface covering the WORKAREA (same frame the widget uses), so its
        # coordinates are already workarea-local: 0. On X11 the rectangle window
        # covers the whole monitor, so the workarea->monitor offset applies.
        "frame_ox": 0 if compositor == "wayland" else frame_x - mx,
        "frame_oy": 0 if compositor == "wayland" else frame_y - my,
        "right_gap": None,
        "anchor": "top left",
    }


def panel_rect(monitor, compositor, workarea, monitor_index):
    try:
        with open(LAYOUT_FILE, "r", encoding="utf-8") as f:
            layout = json.load(f)
    except Exception:
        sys.exit("ERROR: .layout.json missing; run start.sh first")
    p = None
    for m in layout.get("monitors", []):
        if m["index"] == monitor_index:
            p = m["panel"]
            break
    if p is None:
        sys.exit("ERROR: monitor %d not in .layout.json" % monitor_index)

    scale = float(config_value("panel_scale", monitor_index) or 1.0)
    w = PANEL_WIDTH * scale
    h = p["height"] * scale
    off_x = p["x"]
    off_y = p["y"]
    anchor = p["anchor"]

    mx, my, mw, mh = monitor["x"], monitor["y"], monitor["width"], monitor["height"]
    if compositor == "wayland" and workarea:
        fx, fy, fw, fh = workarea
        frame_x, frame_y = max(fx, mx), max(fy, my)
        frame_w = min(fx + fw, mx + mw) - frame_x
        frame_h = min(fy + fh, my + mh) - frame_y
    else:
        frame_x, frame_y, frame_w, frame_h = mx, my, mw, mh

    h_align = "right" if "right" in anchor else "left"
    v_align = "top" if "top" in anchor else "bottom"
    abs_x = frame_x + off_x + align_pos(w, frame_w, h_align)
    abs_y = frame_y + off_y + align_pos(h, frame_h, v_align)

    # eww offsets: for the panel keep workarea.py's values as-is (they are the
    # margins/gaps; the anchor is unchanged).
    if compositor == "wayland":
        left = frame_w - w - off_x
    else:
        left = frame_w - w + off_x
    return {
        "x": off_x,
        "y": off_y,
        "left": int(round(left)),
        "top": int(round(off_y)),
        "abs_x": int(round(abs_x)),
        "abs_y": int(round(abs_y)),
        "width": int(round(w)),
        "height": int(round(h)),
        "frame_w": int(frame_w),
        "frame_h": int(frame_h),
        "frame_ox": 0 if compositor == "wayland" else frame_x - mx,
        "frame_oy": 0 if compositor == "wayland" else frame_y - my,
        "right_gap": int(off_x),
        "anchor": anchor,
    }


def main():
    args = sys.argv[1:]
    widget = None
    monitor_index = 0
    for i, a in enumerate(args):
        if a == "--widget" and i + 1 < len(args):
            widget = args[i + 1]
        elif a == "--monitor" and i + 1 < len(args):
            monitor_index = int(args[i + 1])
    if widget not in ("clock", "panel"):
        sys.exit("Usage: ./widget_rect.py --widget clock|panel --monitor N")

    data = get_monitors()
    compositor = data.get("compositor", "x11")
    monitor = next((m for m in data["monitors"] if m["index"] == monitor_index), None)
    if monitor is None:
        sys.exit("ERROR: monitor %d not found" % monitor_index)
    workarea = get_workarea()

    rect = clock_rect(monitor, compositor, workarea, monitor_index) if widget == "clock" \
        else panel_rect(monitor, compositor, workarea, monitor_index)
    print(json.dumps(rect))


if __name__ == "__main__":
    main()