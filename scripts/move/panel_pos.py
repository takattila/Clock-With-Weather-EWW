#!/usr/bin/env python3
"""Widget-adjacent placement for the GTK control panels.

Shared by move.py (Move/Resize panel) and gap_ctl.py (panel-gap panel): the
panel opens JUST OUTSIDE the widget -- on the horizontal side with MORE free
space (right vs left of the widget), `gap` px away from its edge, vertically
centered on the widget. Everything is clamped so the panel stays fully inside
the frame.

The returned coordinates are FRAME-LOCAL (the same space the rectangle overlay
uses). X11 callers then add the frame's absolute origin (abs - frame-local) on
top, because GtkWindow.move() takes ABSOLUTE screen coordinates; on Wayland the
layer-shell margins are already frame/workarea-local and the value is used as
is.

Usage:
  from panel_pos import panel_position
  px, py = panel_position(rect, MC_W, MC_H, GAP)
"""


def clamp(value, lo, hi):
    return max(lo, min(value, hi))


def panel_position(rect, panel_w, panel_h, gap):
    """Frame-local (px, py) placing a panel_w x panel_h panel beside the widget.

    `rect` is the widget rectangle dict from widget_rect.py; `gap` is the pixel
    distance kept between the widget's edge and the panel.
    """
    left = int(round(rect["left"]))
    top = int(round(rect["top"]))
    w = int(round(rect["width"]))
    h = int(round(rect["height"]))
    frame_w = int(rect["frame_w"])
    frame_h = int(rect["frame_h"])

    py = clamp(top + (h - panel_h) // 2, 0, max(0, frame_h - panel_h))
    if frame_w - (left + w) >= left:
        px = min(left + w + gap, max(0, frame_w - panel_w))
    else:
        px = max(0, left - gap - panel_w)
    return px, py