#!/usr/bin/env python3
"""Keyboard helper window for the Move / Resize mode.

eww 0.5.0 cannot capture arrow keys / ENTER / ESC, so this tiny GTK3 window
(1x1 px, undecorated, placed at the cursor on X11) grabs the keyboard and
prints one line per key press to stdout:

  left | right | up | down         (Shift variants: "shift+left", ...)
  enter | esc

scripts/move.py reads these lines and drives the on-screen overlay.

On X11 the window performs a keyboard grab (arrows arrive immediately). On
Wayland the compositor decides keyboard focus, so one click on the window may
be needed first (see PLAN.md section 9).

Usage: ./move_keys.py [--x PX --y PY]
"""

import argparse
import os
import sys

try:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk
except Exception as exc:
    print("esc", flush=True)
    sys.exit("move_keys: GTK3 unavailable: %s" % exc)


def key_label(keyval, state):
    if keyval in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down):
        names = {
            Gdk.KEY_Left: "left",
            Gdk.KEY_Right: "right",
            Gdk.KEY_Up: "up",
            Gdk.KEY_Down: "down",
        }
        shift = "shift+" if state & Gdk.ModifierType.SHIFT_MASK else ""
        return shift + names[keyval]
    if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
        return "enter"
    if keyval == Gdk.KEY_Escape:
        return "esc"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    args = ap.parse_args()

    win = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
    win.set_decorated(False)
    win.set_skip_taskbar_hint(True)
    win.set_skip_pager_hint(True)
    win.set_accept_focus(True)
    win.set_keep_above(True)
    win.set_resizable(False)
    win.set_default_size(1, 1)
    win.move(args.x, args.y)
    win.set_opacity(0.0)

    def on_key(win, event):
        label = key_label(event.keyval, event.state)
        if label:
            print(label, flush=True)
        if label == "esc":
            Gtk.main_quit()
        return label is not None

    win.connect("key-press-event", on_key)
    win.connect("destroy", lambda *_: Gtk.main_quit())
    win.realize()

    # X11: grab the keyboard so arrows arrive immediately. On Wayland this is
    # a no-op/refused by the compositor; focus is requested instead.
    try:
        if win.get_window() is not None:
            win.get_window().keyboard_grab(False, Gdk.CURRENT_TIME)
    except Exception:
        pass
    try:
        win.get_window().focus(Gdk.CURRENT_TIME)
    except Exception:
        pass

    win.show_all()
    win.present()
    try:
        win.get_window().raise_()
    except Exception:
        pass

    Gtk.main()


if __name__ == "__main__":
    main()