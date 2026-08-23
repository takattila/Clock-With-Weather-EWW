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
multiplied by the panel scale. BOTH widgets scale their axes independently:
width uses `scale_x` / `panel_scale_x`, height uses `scale_y` /
`panel_scale_y` (each axis falls back to the shared `scale` when missing,
see scripts/core/config.py::resolve_axis_scales).

Usage:
  ./widget_rect.py --widget clock --monitor 0
  ./widget_rect.py --widget panel --monitor 1

Output (stdout, JSON):
  {
    "x": visible top-left x (workarea-local on Wayland, monitor-local on X11),
    "y": visible top-left y,
    "abs_x": absolute screen top-left x,
    "abs_y": absolute screen top-left y,
    "width": widget width (scale_x applied),
    "height": widget height (scale_y applied),
    "win_x"/"win_y"/"win_w"/"win_h": the eww window (canvas) geometry —
        max(natural, visible) per axis, positioned so the canvas always fits
        the monitor,
    "translate_x"/"translate_y": transform :translate values placing the
        scaled content exactly on the visible rectangle, already adjusted
        for the running binary's transform order (old builds apply :scale
        before :translate and need the value pre-divided by the axis scale;
        see _divide_translate_by_scale),
    "natural_w": natural (scale = 1.0) width,
    "natural_h": natural (scale = 1.0) height,
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


# Process-level caches: ctx.py now computes every rectangle in ONE process,
# so repeated ImageFont.truetype() parses (the dominant cost, ~0.2 s per
# open) and city measurements must be reused across calls.
_FONT_CACHE = {}
_NATURAL_SIZE_CACHE = {}


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
                key = (path, size)
                font = _FONT_CACHE.get(key)
                if font is None:
                    font = ImageFont.truetype(path, size)
                    _FONT_CACHE[key] = font
                return font.getlength(text)
            except Exception:
                continue
    return len(text) * size * 0.6


def clock_natural_size(monitor_index):
    """Natural (scale = 1.0) clock window size, ending at the city name."""
    key = (monitor_index,)
    if key in _NATURAL_SIZE_CACHE:
        return _NATURAL_SIZE_CACHE[key]
    city = config_value("city", monitor_index) or "Budapest"
    city_w = measure_text(city, CITY_FONT_SIZE, bold=CITY_FONT_BOLD)
    natural_w = max(CITY_X + city_w, RIGHT_FIXED_END) + CLOCK_PAD
    _NATURAL_SIZE_CACHE[key] = (int(round(natural_w)), CLOCK_H)
    return _NATURAL_SIZE_CACHE[key]


def _run(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
    except Exception:
        return ""


# Whether the running eww binary applies :scale BEFORE :translate inside its
# transform widget (so the emitted :translate must be pre-divided by the axis
# scale), cached per compositor. The order is a property of the BINARY, not of
# the compositor — identify it from the git hash embedded in `eww --version`:
#   - d87c2fdb... is the v0.6.0 TAG build (its stale Cargo version string
#     prints "eww 0.5.0"): cr.scale() runs before cr.translate(), cairo
#     composes S·R·T and the on-screen offset is scale × translate,
#   - any other identified build (e.g. 48f5aa8b..., newer master) already uses
#     the fixed translate-after-scale order: :translate is unscaled device px.
# A per-monitor config key `translate_divide_scale` ("yes" | "no" | "auto",
# default) overrides the detection; with an unparseable probe the fleet
# heuristic falls back to wayland → divide.
_EWW_TRANSLATE_ORDER_CACHE = {}


def _divide_translate_by_scale(compositor):
    key = str(compositor)
    if key in _EWW_TRANSLATE_ORDER_CACHE:
        return _EWW_TRANSLATE_ORDER_CACHE[key]
    override = (config_value("translate_divide_scale") or "auto").strip().lower()
    if override == "yes":
        result = True
    elif override == "no":
        result = False
    else:
        out = _run(["eww", "--version"])
        if "d87c2fdb" in out:
            result = True
        elif re.search(r"\b[0-9a-f]{40}\b", out):
            result = False
        else:
            result = compositor == "wayland"
    _EWW_TRANSLATE_ORDER_CACHE[key] = result
    return result


def _emit_translate(delta, scale, compositor):
    """Transform :translate value for `delta` device px at axis `scale`."""
    if _divide_translate_by_scale(compositor):
        return int(round(delta / max(scale, 0.05)))
    return int(round(delta))


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


_MERGED_CONFIG_CACHE = {}


def config_value(key, monitor=None):
    """Merged config value as a string, resolved IN-PROCESS with caching.

    The old implementation spawned `config.py --key ...` per call (~100 ms
    each, several calls per rectangle) which dominated the right-click
    latency once ctx.py computes every rect in one process. Here the merged
    view (config.load_config) is built at most once per monitor and reused;
    the returned representation matches the CLI's printed output.
    """
    cache_key = "-1" if monitor is None else str(monitor)
    merged = _MERGED_CONFIG_CACHE.get(cache_key)
    if merged is None:
        sys.path.insert(0, os.path.join(SCRIPTS_DIR, "core"))
        import config as _config  # noqa: E402

        old_argv = sys.argv
        sys.argv = ["config.py"] + (["--monitor", cache_key]
                                    if monitor is not None else [])
        try:
            merged = _config.load_config()
        finally:
            sys.argv = old_argv
        _MERGED_CONFIG_CACHE[cache_key] = merged
    val = merged.get(key)
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


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
    # Independent axis scales: width follows scale_x, height follows scale_y
    # (each falls back to the shared `scale` when missing).
    scale_x = float(config_value("scale_x", monitor_index) or 1.0)
    scale_y = float(config_value("scale_y", monitor_index) or 1.0)
    natural_w, natural_h = clock_natural_size(monitor_index)
    w = natural_w * scale_x
    h = natural_h * scale_y
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
    vis_w = int(round(w))
    vis_h = int(round(h))
    top_left_x = int(round(align_pos(vis_w, frame_w, h_align) + pos_x))
    top_left_y = int(round(align_pos(vis_h, frame_h, v_align) + pos_y))

    # --- render canvas (the GTK window) vs the visible content ---------------
    # The transform only scales the DRAWING inside a fixed-size transparent
    # canvas; the :translate unit depends on the binary's internal matrix
    # order (see _divide_translate_by_scale): v0.6.0-tag builds (d87c2fdb)
    # call cr.scale() BEFORE cr.translate(), so cairo composes S·R·T, the
    # on-screen offset is scale × translate and we emit delta / scale
    # (guarded against a degenerate 0 scale); newer builds use the fixed
    # translate-after-scale order and get the plain delta. Per axis:
    #   canvas    = max(natural, visible)   (>100% grows the canvas: no clip)
    #   canvas_tl = clamp(visible_tl, 0, frame - canvas)
    #   delta     = visible_tl - canvas_tl  (0 when visible >= natural)
    # so the scaled content lands exactly on the visible rectangle while the
    # canvas itself always fits the monitor — an overflowing managed window
    # would be relocated by the X11 WM, dragging the widget off its spot.
    win_w = max(int(natural_w), vis_w)
    win_h = max(int(natural_h), vis_h)
    win_x = min(max(top_left_x, 0), max(0, frame_w - win_w))
    win_y = min(max(top_left_y, 0), max(0, frame_h - win_h))
    return {
        "x": top_left_x,
        "y": top_left_y,
        "left": top_left_x,
        "top": top_left_y,
        "abs_x": int(frame_x) + top_left_x,
        "abs_y": int(frame_y) + top_left_y,
        "width": vis_w,
        "height": vis_h,
        "win_x": win_x,
        "win_y": win_y,
        "win_w": win_w,
        "win_h": win_h,
        "translate_x": _emit_translate(top_left_x - win_x, scale_x, compositor),
        "translate_y": _emit_translate(top_left_y - win_y, scale_y, compositor),
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

    scale_x = float(config_value("panel_scale_x", monitor_index) or 1.0)
    scale_y = float(config_value("panel_scale_y", monitor_index) or 1.0)
    natural_h = int(round(p["height"]))
    w = PANEL_WIDTH * scale_x
    h = natural_h * scale_y
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
    vis_w = int(round(w))
    vis_h = int(round(h))
    # Visible top-left from the eww margins. Compositor-specific sign quirks
    # preserved: an X11 right-anchor margin ADDS to frame_w - width while the
    # Wayland one subtracts; left/bottom anchors measure inward.
    if h_align == "left":
        top_left_x = int(round(off_x))
    elif compositor == "wayland":
        top_left_x = int(round(frame_w - vis_w - off_x))
    else:
        top_left_x = int(round(frame_w - vis_w + off_x))
    if v_align == "bottom":
        top_left_y = int(round(frame_h - vis_h + off_y))
    else:
        top_left_y = int(round(off_y))
    abs_x = frame_x + top_left_x
    abs_y = frame_y + top_left_y

    # --- render canvas: the same rule as for the clock -----------------------
    # The transform scales only the drawing inside a fixed-size canvas; the
    # :translate unit depends on the binary's transform order (see
    # _divide_translate_by_scale): v0.6.0-tag builds need delta / scale per
    # axis, newer builds the plain delta. Per axis: canvas =
    # max(natural, visible), canvas_tl = clamp(visible_tl, 0, frame - canvas).
    # This keeps the scaled content exactly on the visible rectangle while the
    # oversized transparent canvas never leaves the monitor (an overflowing
    # managed X11 window gets relocated by the WM, which previously dragged a
    # moved panel back / clipped >100% panels).
    nat_w = PANEL_WIDTH
    win_w = max(nat_w, vis_w)
    win_h = max(natural_h, vis_h)
    win_x = min(max(top_left_x, 0), max(0, frame_w - win_w))
    win_y = min(max(top_left_y, 0), max(0, frame_h - win_h))
    return {
        "x": off_x,
        "y": off_y,
        "left": top_left_x,
        "top": top_left_y,
        "abs_x": abs_x,
        "abs_y": abs_y,
        "width": vis_w,
        "height": vis_h,
        "win_x": win_x,
        "win_y": win_y,
        "win_w": win_w,
        "win_h": win_h,
        "translate_x": _emit_translate(top_left_x - win_x, scale_x, compositor),
        "translate_y": _emit_translate(top_left_y - win_y, scale_y, compositor),
        "natural_w": nat_w,
        "natural_h": natural_h,
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