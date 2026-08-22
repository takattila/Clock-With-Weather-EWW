#!/usr/bin/env python3
"""Compute where to open the context menu (ctx_menu window).

- On X11 the menu is placed exactly at the cursor (xdotool getmouselocation),
  on the monitor that contains the cursor.
- On Wayland the global cursor is read through the KWin scripting API (KDE
  only, scripts/workarea.py kde_cursor; xdotool is stale over the native
  layer-shell widgets), so the menu opens at the click point. On non-KDE
  compositors there is no cursor API, so the menu is anchored to the widget's
  top-left corner (from scripts/widget_rect.py).

Output (stdout, JSON):
  {"x": eww x offset, "y": eww y offset, "screen": monitor index,
   "anchor": "top left"}

The offsets are workarea-local on Wayland and monitor-local (absolute) on X11,
i.e. exactly what `eww open --screen N --arg pos=... --arg anchor=...` expects.
"""

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import widget_rect as wr  # noqa: E402

MENU_W, MENU_H = 180, 190


def get_cursor():
    out = wr._run(["xdotool", "getmouselocation"])
    m = {}
    for part in out.split():
        if ":" in part:
            k, v = part.split(":", 1)
            m[k] = v
    try:
        return int(m.get("x", -1)), int(m.get("y", -1))
    except ValueError:
        return None


def monitor_for_point(monitors, px, py):
    for mon in monitors:
        if mon["x"] <= px < mon["x"] + mon["width"] and mon["y"] <= py < mon["y"] + mon["height"]:
            return mon
    return None


def clamp(value, lo, hi):
    return max(lo, min(value, hi))


def frame_for(mon, workarea):
    """(wx, wy, ww, wh): the workarea intersected with monitor `mon` in the
    monitor's local coordinates (falls back to the full monitor)."""
    if workarea:
        wx = max(workarea[0], mon["x"])
        wy = max(workarea[1], mon["y"])
        ww = min(workarea[0] + workarea[2], mon["x"] + mon["width"]) - wx
        wh = min(workarea[1] + workarea[3], mon["y"] + mon["height"]) - wy
        return wx, wy, ww, wh
    return mon["x"], mon["y"], mon["width"], mon["height"]


def main():
    args = sys.argv[1:]
    widget = None
    monitor = 0
    for i, a in enumerate(args):
        if a == "--widget" and i + 1 < len(args):
            widget = args[i + 1]
        elif a == "--monitor" and i + 1 < len(args):
            monitor = int(args[i + 1])
    if widget not in ("clock", "panel"):
        sys.exit("Usage: ./menu_pos.py --widget clock|panel --monitor N")

    data = wr.get_monitors()
    compositor = data.get("compositor", "x11")
    monitors = data["monitors"]
    wmon = next((m for m in monitors if m["index"] == monitor), None)
    if wmon is None:
        sys.exit("ERROR: monitor %d not found" % monitor)
    workarea = wr.get_workarea()

    if compositor == "x11":
        cursor = get_cursor()
        if cursor is None:
            cursor = (wmon["x"] + 8, wmon["y"] + 8)
        mon = monitor_for_point(monitors, cursor[0], cursor[1]) or wmon
        x = clamp(cursor[0] - mon["x"], 0, mon["width"] - MENU_W)
        y = clamp(cursor[1] - mon["y"], 0, mon["height"] - MENU_H)
        print(json.dumps({"x": x, "y": y, "screen": mon["index"], "anchor": "top left"}))
        return

    # Wayland: open at the click point when KDE exposes the global pointer
    # (KWin scripting, workarea.kde_cursor). The cursor can sit on a different
    # monitor than the widget, so its own monitor is used. On non-KDE
    # compositors there is no cursor API -> fall back to the widget corner.
    try:
        import workarea as _wa
        cursor = _wa.kde_cursor()
    except Exception:
        cursor = None
    if cursor:
        mon = monitor_for_point(monitors, cursor[0], cursor[1]) or wmon
        wx, wy, ww, wh = frame_for(mon, workarea)
        x = clamp(cursor[0] - wx, 0, ww - MENU_W)
        y = clamp(cursor[1] - wy, 0, wh - MENU_H)
        print(json.dumps({"x": x, "y": y, "screen": mon["index"], "anchor": "top left"}))
        return

    # Fallback: widget corner (workarea-relative margins).
    rect = wr.clock_rect(wmon, compositor, workarea, monitor) if widget == "clock" \
        else wr.panel_rect(wmon, compositor, workarea, monitor)
    wx, wy, ww, wh = frame_for(wmon, workarea)
    x = clamp(rect["abs_x"] - wx + 4, 0, ww - MENU_W)
    y = clamp(rect["abs_y"] - wy + 4, 0, wh - MENU_H)
    print(json.dumps({"x": x, "y": y, "screen": monitor, "anchor": "top left"}))


if __name__ == "__main__":
    main()