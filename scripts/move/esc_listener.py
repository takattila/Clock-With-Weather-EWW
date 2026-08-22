#!/usr/bin/env python3
"""ESC / ENTER keyboard listener for the popup and Move/Resize sessions.

eww 0.5.0 cannot capture keyboard events, so this tiny GTK3 window (1x1 px,
undecorated, transparent) receives keyboard focus for the current session and
watches for ESC/ENTER.

The window runs on the X11 backend (XWayland when the desktop is Wayland):
  * skip-taskbar is honored for X11 windows, so KDE never lists it in the
    taskbar (native Wayland toplevels always show up there no matter the hints
    or window type),
  * keyboard focus works like on any X11 setup: the compositor gives focus to a
    window that is opened right after a user action (the right-click / Move /
    About button click), so ESC/ENTER reach it — the same mechanism the
    previous Wayland version relied on (which the user confirmed working).

It does not use XGrabKeyboard: the off-screen window it would need cannot hold
a grab reliably, and a grab at an on-screen position was unstable. The plain
focus path above is what worked all along.

The window sits off-screen (at -32000,-32000), fully transparent, so it is
invisible on screen and in the taskbar.

Modes:
  ctx   ESC runs scripts/close_popup.py (closes ctx_menu /
        dismiss_overlay; the GTK About window quits on its own).
  move  ESC runs move_ctl.py --action cancel, ENTER runs move_ctl.py --action
        save (closes the Move/Resize session); --widget/--monitor are passed
        through to move_ctl.py.

The listener writes its PID to run/esc_listener.pid. scripts/move_ctl.py
sends it SIGUSR1 after each button click so the window re-requests keyboard
focus (clicking a focusable eww window moves focus away, which would otherwise
break ESC/ENTER mid-session). On SIGUSR1 the window re-presents itself.

The popup scripts start it via start_new_session and kill any running instance
with `pkill -f esc_listener.py` when they open a popup or enter move mode, so
only one listener is alive at a time.

Usage:
  ./esc_listener.py --mode ctx
  ./esc_listener.py --mode move --widget clock --monitor 0
"""

import argparse
import atexit
import os
import signal
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/
# scripts/move/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
PIDFILE = os.path.join(CONFIG_DIR, "run", "esc_listener.pid")

# Run under XWayland (X11 backend): skip-taskbar is honored for X11 windows, so
# KDE never lists this helper in the taskbar (native Wayland toplevels always
# show up there no matter the hints or window type).
os.environ["GDK_BACKEND"] = "x11"

try:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk
except Exception as exc:
    sys.exit("esc_listener: GTK3 unavailable: %s" % exc)

_win = None


def write_pid():
    try:
        os.makedirs(os.path.dirname(PIDFILE), exist_ok=True)
        with open(PIDFILE, "w") as fh:
            fh.write(str(os.getpid()))
    except Exception:
        pass


def remove_pid():
    try:
        if os.path.exists(PIDFILE):
            os.unlink(PIDFILE)
    except Exception:
        pass


def refocus():
    # A focusable eww window (the control panel / overlay) grabbed keyboard
    # focus when its button was clicked; re-request it so ESC/ENTER keep
    # working until the session ends.
    if _win is None:
        return
    try:
        _win.present()
        if _win.get_window() is not None:
            _win.get_window().focus(Gdk.CURRENT_TIME)
            _win.get_window().raise_()
    except Exception:
        pass


def on_refocus(signum, frame):
    refocus()


def on_term(signum, frame):
    remove_pid()
    Gtk.main_quit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["ctx", "move"], default="ctx")
    ap.add_argument("--widget", choices=["clock", "panel"])
    ap.add_argument("--monitor", type=int, default=0)
    args = ap.parse_args()
    start = time.time()

    win = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
    global _win
    _win = win
    win.set_decorated(False)
    win.set_type_hint(Gdk.WindowTypeHint.UTILITY)
    win.set_skip_taskbar_hint(True)
    win.set_skip_pager_hint(True)
    win.set_accept_focus(True)
    win.set_keep_above(True)
    win.set_resizable(False)
    win.set_title("")
    win.set_default_size(1, 1)
    win.move(-32000, -32000)
    win.set_opacity(0.0)

    def handle(key):
        if args.mode == "move":
            action = "cancel" if key == "esc" else "save"
            subprocess.run(
                [
                    "python3", os.path.join(SCRIPT_DIR, "move_ctl.py"),
                    "--widget", args.widget,
                    "--monitor", str(args.monitor),
                    "--action", action,
                ],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=dict(os.environ, EWW_LISTENER_PID=str(os.getpid())),
            )
        else:
            subprocess.run(
                ["python3", os.path.join(SCRIPTS_DIR, "widgets", "close_popup.py")],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        Gtk.main_quit()

    def on_key(win, event):
        # Safety net: ignore key events in the first two seconds. This window is
        # opened right after the user's menu click, so a real ESC/ENTER press
        # cannot come that early; it also swallows any synthetic key event the
        # compositor may emit while the window is being focused/shown.
        if time.time() - start < 2.0:
            return False
        if event.keyval == Gdk.KEY_Escape:
            handle("esc")
            return True
        if args.mode == "move" and event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            handle("enter")
            return True
        return False

    win.connect("key-press-event", on_key)
    win.connect("destroy", lambda *_: Gtk.main_quit())
    win.realize()

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

    write_pid()
    signal.signal(signal.SIGUSR1, on_refocus)
    signal.signal(signal.SIGTERM, on_term)
    atexit.register(remove_pid)

    Gtk.main()


if __name__ == "__main__":
    main()