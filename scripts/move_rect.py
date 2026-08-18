#!/usr/bin/env python3
"""Full-monitor rectangle overlay for the Move / Resize session.

Replaces the eww move_overlay window (eww 0.5.0 cannot drag/resize anything):
this GTK3 window covers the target monitor, draws the dashed rectangle (the
former generated/move_rect.svg) and lets the mouse act on it:

  * drag inside     -> move the rectangle (updates move_x/move_y)
  * drag a corner/edge -> resize it keeping the opposite corner/edge fixed,
    aspect ratio preserved (scale 0.3..1.5, like the +/- panel buttons)
  * click outside   -> cancel the session (move_ctl.py --action cancel)

The move_x/move_y/move_w/move_h/move_pct eww defvars stay the single shared
state with the keyboard daemon and the control panel (scripts/move_panel.py):
while not dragging, this window re-syncs from them every 250 ms, so the arrow
keys and the +/- buttons keep working and stay in sync with the drawn
rectangle.

  * X11     - undecorated keep_above toplevel at the monitor geometry. The
              control panel is override-redirect, so it still stacks above and
              stays clickable.
  * Wayland - layer-shell OVERLAY surface anchored to all four edges of the
              monitor (GtkLayerShell, same dependency as eww); the panel is
              mapped afterwards, so it stacks above.

The rectangle coordinates (move_x/move_y) are FRAME-relative (workarea-local
on Wayland, monitor-local on X11). --ox/--oy is the frame's top-left inside
the monitor, so the drawing is offset into this full-monitor window's own
coordinate space (0/0 on X11 where the frame IS the monitor).

Usage:
  ./move_rect.py --widget clock --monitor 0 --x 100 --y 50 --w 745 --h 250 \
                 --ox 0 --oy 0 --base-w 745 --base-h 250 \
                 --frame-w 1920 --frame-h 1080
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time

import cairo

try:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk, GLib
except Exception as exc:
    sys.exit("move_rect: GTK3 unavailable: %s" % exc)

WAYLAND = "WAYLAND_DISPLAY" in os.environ and os.environ.get("GDK_BACKEND", "wayland") != "x11"

if WAYLAND:
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except Exception as exc:
        sys.exit("move_rect: GtkLayerShell unavailable: %s" % exc)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")

HIT = 10          # px tolerance for corners/edges
MIN_SCALE = 0.3   # same bounds as scripts/move_ctl.py
MAX_SCALE = 1.5
FLUSH_INTERVAL = 0.05   # seconds between `eww update` calls while dragging


def run(cmd):
    try:
        subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True, cwd=CONFIG_DIR,
        )
    except Exception:
        pass


def eww(*args):
    run(["eww", "--config", CONFIG_DIR] + list(args))


def eww_get(name):
    try:
        out = subprocess.check_output(
            ["eww", "--config", CONFIG_DIR, "get", name],
            stderr=subprocess.DEVNULL, text=True,
        )
        return out.strip()
    except Exception:
        return None


def eww_get_int(name, fallback=0):
    try:
        return int(round(float(eww_get(name) or fallback)))
    except (TypeError, ValueError):
        return fallback


def session_active():
    try:
        with open(SESSION_FILE) as fh:
            data = json.load(fh)
        return data.get("mode") == "move"
    except Exception:
        return False


def clamp(value, lo, hi):
    return max(lo, min(value, hi))


def rounded_rect(cr, x, y, w, h, r):
    r = max(1, int(r))
    r = min(r, w // 2, h // 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class MoveRect:
    """Full-monitor transparent overlay that draws + manipulates the rect."""

    def __init__(self, widget, monitor, x, y, w, h, ox, oy, base_w, base_h,
                 frame_w, frame_h):
        self.widget = widget
        self.monitor = monitor
        # Rectangle position/size in FRAME coordinates (the shared state).
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        # Frame origin inside the monitor (window coordinate space).
        self.ox = ox
        self.oy = oy
        self.base_w = base_w or 1
        self.base_h = base_h or 1
        self.frame_w = frame_w
        self.frame_h = frame_h

        self.drag = None          # None | "inside" | corner | edge zone
        self.px0 = self.py0 = 0.0 # press position (window coords)
        self.sx = self.sy = 0     # rect state at press (frame coords)
        self.sw = self.sh = 0
        self.off_x = 0.0          # press offset inside the rect (move mode)
        self.off_y = 0.0
        self.anchor = None        # fixed corner/edge point (frame coords)
        self.s0 = 1.0             # scale at press
        self.d0 = 1.0             # pointer distance to the anchor at press
        self.last_flush = 0.0
        self.flush_id = 0

        self.win = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
        self.win.set_title("")
        self.win.set_decorated(False)
        self.win.set_resizable(False)
        self.win.set_accept_focus(False)
        self.win.set_app_paintable(True)
        self.win.set_skip_taskbar_hint(True)
        self.win.set_skip_pager_hint(True)
        self.win.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        screen = self.win.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.win.set_visual(visual)

        if WAYLAND:
            try:
                GtkLayerShell.init_for_window(self.win)
                # TOP (NOT OVERLAY): the control panel is an OVERLAY surface and
                # the layer-shell protocol guarantees OVERLAY > TOP, so the panel
                # is ALWAYS above this full-monitor window regardless of the map
                # order. With both in OVERLAY the slower-starting rectangle
                # window mapped LAST (on top), swallowed every panel click and
                # turned Save/Cancel/arrows into "click outside -> cancel".
                GtkLayerShell.set_layer(self.win, GtkLayerShell.Layer.TOP)
                for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                             GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
                    GtkLayerShell.set_anchor(self.win, edge, True)
                GtkLayerShell.set_keyboard_mode(self.win, GtkLayerShell.KeyboardMode.ON_DEMAND)
                display = Gdk.Display.get_default()
                if display is not None and monitor < display.get_n_monitors():
                    GtkLayerShell.set_monitor(self.win, display.get_monitor(monitor))
            except Exception:
                pass
        else:
            try:
                display = Gdk.Display.get_default()
                if display is not None and monitor < display.get_n_monitors():
                    geo = display.get_monitor(monitor).get_geometry()
                    self.win.move(geo.x, geo.y)
                    self.win.set_default_size(geo.width, geo.height)
                self.win.set_keep_above(True)
            except Exception:
                pass
            # The eww widgets are override-redirect windows on X11, so they
            # always stack above normal toplevels; this rectangle must be
            # override-redirect too to float above them and receive the drag.
            self.win.connect("realize", self.on_realize)

        self.area = Gtk.DrawingArea()
        self.area.set_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.area.connect("draw", self.on_draw)
        self.area.connect("button-press-event", self.on_press)
        self.area.connect("button-release-event", self.on_release)
        self.area.connect("motion-notify-event", self.on_motion)
        self.win.add(self.area)
        self.win.connect("destroy", lambda *_: Gtk.main_quit())

    def on_realize(self, widget):
        if not WAYLAND:
            try:
                widget.get_window().set_override_redirect(True)
            except Exception:
                pass

    # ---- drawing -----------------------------------------------------------
    def on_draw(self, area, cr):
        # Transparent background (rgba visual; a no-op fallback is opaque).
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        rx = self.x + self.ox
        ry = self.y + self.oy
        rw, rh = self.w, self.h

        cr.set_source_rgba(1, 1, 1, 0.08)
        rounded_rect(cr, rx, ry, rw, rh, 4)
        cr.fill()

        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.set_line_width(2)
        cr.set_dash([10, 6], 0)
        rounded_rect(cr, rx, ry, rw, rh, 4)
        cr.stroke()
        return False

    # ---- hit testing / cursor ----------------------------------------------
    @staticmethod
    def _within(v, edge, tol):
        return abs(v - edge) <= tol

    def hit_test(self, px, py):
        """Zone at window (monitor) coords, or None when outside the rect."""
        x = px - self.ox
        y = py - self.oy
        w, h = self.w, self.h
        if (self._within(x, self.x, HIT) and self._within(y, self.y, HIT)):
            return "tl"
        if (self._within(x, self.x + w, HIT) and self._within(y, self.y, HIT)):
            return "tr"
        if (self._within(x, self.x, HIT) and self._within(y, self.y + h, HIT)):
            return "bl"
        if (self._within(x, self.x + w, HIT) and self._within(y, self.y + h, HIT)):
            return "br"
        if self._within(y, self.y, HIT) and self.x <= x <= self.x + w:
            return "top"
        if self._within(y, self.y + h, HIT) and self.x <= x <= self.x + w:
            return "bottom"
        if self._within(x, self.x, HIT) and self.y <= y <= self.y + h:
            return "left"
        if self._within(x, self.x + w, HIT) and self.y <= y <= self.y + h:
            return "right"
        if self.x <= x <= self.x + w and self.y <= y <= self.y + h:
            return "inside"
        return None

    CURSORS = {
        "inside": "move",
        "tl": "nwse-resize", "br": "nwse-resize",
        "tr": "nesw-resize", "bl": "nesw-resize",
        "top": "ns-resize", "bottom": "ns-resize",
        "left": "ew-resize", "right": "ew-resize",
    }

    def _set_cursor(self, zone):
        name = self.CURSORS.get(zone, "default")
        try:
            window = self.area.get_window()
            if window is not None:
                window.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), name))
        except Exception:
            pass

    # ---- drag --------------------------------------------------------------
    def on_press(self, widget, event):
        if event.button != 1:
            return False
        zone = self.hit_test(event.x, event.y)
        if zone is None:
            # Click outside the rectangle cancels the whole session.
            run([sys.executable, os.path.join(SCRIPT_DIR, "move_ctl.py"),
                 "--widget", self.widget, "--monitor", str(self.monitor),
                 "--action", "cancel"])
            Gtk.main_quit()
            return False

        self.drag = zone
        self.px0, self.py0 = event.x, event.y
        self.sx, self.sy, self.sw, self.sh = self.x, self.y, self.w, self.h
        if zone == "inside":
            self.off_x = (event.x - self.ox) - self.x
            self.off_y = (event.y - self.oy) - self.y
        else:
            self.s0 = self.w / self.base_w
            self.anchor = self._anchor_for(zone)
            self.d0 = max(self._distance((event.x - self.ox), (event.y - self.oy),
                                         self.anchor, zone), 1.0)
        self.last_flush = 0.0
        self._set_cursor(zone)
        return False

    def _anchor_for(self, zone):
        """Fixed corner (x, y) or fixed edge (None, y) / (x, None), frame coords."""
        x, y, w, h = self.sx, self.sy, self.sw, self.sh
        if zone == "tl":
            return (x + w, y + h)
        if zone == "tr":
            return (x, y + h)
        if zone == "bl":
            return (x + w, y)
        if zone == "br":
            return (x, y)
        if zone == "top":
            return (None, y + h)
        if zone == "bottom":
            return (None, y)
        if zone == "left":
            return (x + w, None)
        if zone == "right":
            return (x, None)
        return (x, y)

    @staticmethod
    def _distance(px, py, anchor, zone):
        ax, ay = anchor
        if ax is None:
            return abs(py - ay)
        if ay is None:
            return abs(px - ax)
        return math.hypot(px - ax, py - ay)

    def on_motion(self, widget, event):
        if self.drag:
            if self.drag == "inside":
                nx = (event.x - self.ox) - self.off_x
                ny = (event.y - self.oy) - self.off_y
                self.x = int(round(clamp(nx, 0, max(0, self.frame_w - self.w))))
                self.y = int(round(clamp(ny, 0, max(0, self.frame_h - self.h))))
            else:
                self._resize_to(event.x, event.y)
            self.area.queue_draw()
            self._schedule_flush()
        else:
            self._set_cursor(self.hit_test(event.x, event.y))
        return False

    def _resize_to(self, px, py):
        pfx = px - self.ox
        pfy = py - self.oy
        d = self._distance(pfx, pfy, self.anchor, self.drag)
        s = clamp(self.s0 * d / self.d0, MIN_SCALE, MAX_SCALE)
        w = int(round(self.base_w * s))
        h = int(round(self.base_h * s))
        self.x, self.y, self.w, self.h = self._recompute(w, h)

    def _recompute(self, w, h):
        """Rect top-left from the fixed anchor for the current drag zone."""
        zone = self.drag
        ax, ay = self.anchor
        if zone in ("tl", "tr", "bl", "br"):
            x = ax - w if zone in ("tl", "bl") else ax
            y = ay - h if zone in ("tl", "tr") else ay
        elif zone == "top":
            x, y = self.sx, ay - h
        elif zone == "bottom":
            x, y = self.sx, ay
        elif zone == "left":
            x, y = ax - w, self.sy
        elif zone == "right":
            x, y = ax, self.sy
        else:
            x, y = self.sx, self.sy
        x = int(round(clamp(x, 0, max(0, self.frame_w - w))))
        y = int(round(clamp(y, 0, max(0, self.frame_h - h))))
        return x, y, w, h

    def on_release(self, widget, event):
        if event.button != 1:
            return False
        self.drag = None
        self.flush()
        return False

    # ---- shared-state updates (throttled) ----------------------------------
    def _schedule_flush(self):
        now = time.monotonic()
        if now - self.last_flush >= FLUSH_INTERVAL:
            self.flush()
        elif not self.flush_id:
            delay = int((FLUSH_INTERVAL - (now - self.last_flush)) * 1000) + 1
            self.flush_id = GLib.timeout_add(delay, self.flush)

    def flush(self):
        self.flush_id = 0
        self.last_flush = time.monotonic()
        pct = int(round((self.w / self.base_w) * 100))
        eww("update",
            "move_x=%d" % self.x,
            "move_y=%d" % self.y,
            "move_w=%d" % self.w,
            "move_h=%d" % self.h,
            "move_pct=%d" % pct)
        return False

    # ---- periodic session watch + sync -------------------------------------
    def tick(self):
        if not session_active():
            Gtk.main_quit()
            return False
        if not self.drag:
            x = eww_get_int("move_x", self.x)
            y = eww_get_int("move_y", self.y)
            w = eww_get_int("move_w", self.w)
            h = eww_get_int("move_h", self.h)
            if (x, y, w, h) != (self.x, self.y, self.w, self.h):
                self.x, self.y, self.w, self.h = x, y, w, h
                self.area.queue_draw()
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", required=True, choices=["clock", "panel"])
    ap.add_argument("--monitor", type=int, default=0)
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--w", type=int, default=100)
    ap.add_argument("--h", type=int, default=100)
    ap.add_argument("--ox", type=int, default=0)
    ap.add_argument("--oy", type=int, default=0)
    ap.add_argument("--base-w", type=int, default=100)
    ap.add_argument("--base-h", type=int, default=100)
    ap.add_argument("--frame-w", type=int, default=0)
    ap.add_argument("--frame-h", type=int, default=0)
    args = ap.parse_args()

    if not session_active():
        sys.exit(0)

    rect = MoveRect(
        args.widget, args.monitor, args.x, args.y, args.w, args.h,
        args.ox, args.oy, args.base_w, args.base_h,
        args.frame_w, args.frame_h,
    )
    rect.win.show_all()
    rect.win.present()
    GLib.timeout_add(250, rect.tick)
    Gtk.main()


if __name__ == "__main__":
    main()
