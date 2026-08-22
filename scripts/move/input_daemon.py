#!/usr/bin/env python3
"""Invisible keyboard daemon for the popup / Move-Resize sessions.

eww 0.5.0 cannot capture keyboard events, and any helper *window* (GTK grab,
off-screen toplevel, ...) ends up visible on the screen or in the taskbar. This
daemon instead reads the physical keyboard straight from the kernel via evdev
(/dev/input/event*) and creates NO window at all, so nothing ever appears.

evdev reads are passive: the keys still reach the normally focused application,
the daemon only watches. It acts while a session is active, signalled by a
small file generated/input_session.json:

  {"mode": "ctx"}                          <- ctx.py / about.py (popup open)
  {"mode": "move", "widget": "clock", "monitor": 0}   <- move.py (Move/Resize)

Actions (only while that file exists):
  ctx:
    ESC                -> scripts/close_popup.py (closes the popups)
  move:
    Arrow keys         -> move_ctl.py --action left/right/up/down
    Shift+3 / numpad + -> move_ctl.py --action zoom_in   (Hungarian layout)
    Minus / numpad -   -> move_ctl.py --action zoom_out
    Enter              -> move_ctl.py --action save
    ESC                -> move_ctl.py --action cancel

move_ctl.py --action save/cancel and close_popup.py delete the session file, so
the daemon goes back to idle. Key auto-repeat (holding a key) is ignored: one
action per press.

The daemon needs read access to /dev/input/event* (root or the 'input' group).
scripts/start.sh launches it through passwordless sudo; it opens the devices as
root and then drops back to the invoking user (SUDO_UID/SUDO_GID) so the eww
commands it spawns run with the user's privileges and display access.

Usage:
  python3 input_daemon.py          (as root / via `sudo -n`)
"""

import glob
import json
import os
import select
import signal
import struct
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/
# scripts/move/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
PIDFILE = os.path.join(CONFIG_DIR, "run", "input_daemon.pid")

# evdev input event codes (linux/input-event-codes.h)
EV_KEY = 1
KEY_ESC = 1
KEY_3 = 4            # Hungarian layout: Shift+3 = plus
KEY_MINUS = 12       # Hungarian layout: bottom-right '-' key (AB10)
KEY_ENTER = 28
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54
KEY_KPMINUS = 74
KEY_KPPLUS = 87
KEY_KPENTER = 96
KEY_UP = 103
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_DOWN = 108

EV_FMT = "llHHi"
EV_SIZE = struct.calcsize(EV_FMT)


def log(msg):
    print("%s %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def open_devices():
    """Open every /dev/input/event* device read-only (returns fds)."""
    fds = []
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            fds.append(fd)
        except Exception:
            continue
    return fds


def drop_privileges():
    """If we started as root (via sudo), drop to the invoking user so spawned
    eww commands run with the user's display access."""
    if os.getuid() != 0:
        return
    try:
        uid = int(os.environ.get("SUDO_UID") or os.environ.get("SUDO_GID") or 0)
        gid = int(os.environ.get("SUDO_GID") or uid)
    except Exception:
        uid = gid = 1000
    if uid and gid:
        try:
            os.setgroups([])
            os.setgid(gid)
            os.setuid(uid)
        except Exception:
            pass


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


def on_term(signum, frame):
    remove_pid()
    sys.exit(0)


def read_session():
    try:
        with open(SESSION_FILE) as fh:
            return json.load(fh)
    except Exception:
        return None


def run_script(args):
    try:
        subprocess.run(
            [sys.executable] + args,
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15, cwd=CONFIG_DIR,
        )
    except Exception:
        pass


def handle_key(code, shift, session):
    mode = session.get("mode")
    if mode == "ctx":
        if code == KEY_ESC:
            run_script([os.path.join(SCRIPTS_DIR, "widgets", "close_popup.py")])
        return
    if mode != "move":
        return

    # While the hand-typed resize field of the GTK control panel owns the
    # keyboard (move_panel.py sets session["typing"] on entry focus), every
    # key is ignored here: Enter would otherwise SAVE the session and -/+
    # would zoom in/out while the user is just typing a percentage. ESC is
    # ignored too -- click outside the entry first, then ESC cancels.
    if session.get("typing"):
        return

    widget = str(session.get("widget", "clock"))
    monitor = str(session.get("monitor", 0))
    action = None
    if code == KEY_LEFT:
        action = "left"
    elif code == KEY_RIGHT:
        action = "right"
    elif code == KEY_UP:
        action = "up"
    elif code == KEY_DOWN:
        action = "down"
    elif code == KEY_KPPLUS or (shift and code == KEY_3):
        action = "zoom_in"
    elif code in (KEY_MINUS, KEY_KPMINUS):
        action = "zoom_out"
    elif code in (KEY_ENTER, KEY_KPENTER):
        action = "save"
    elif code == KEY_ESC:
        action = "cancel"
    if action:
        run_script([
            os.path.join(SCRIPT_DIR, "move_ctl.py"),
            "--widget", widget, "--monitor", monitor, "--action", action,
        ])


def main():
    log("starting input daemon (pid %d)" % os.getpid())
    fds = open_devices()
    if not fds:
        log("ERROR: no /dev/input/event* devices could be opened (need root or the 'input' group)")
        return 1
    log("watching %d input device(s)" % len(fds))

    drop_privileges()
    write_pid()
    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)

    shift = False
    while True:
        try:
            ready, _, _ = select.select(fds, [], [], 1.0)
        except (OSError, ValueError):
            return 1
        for fd in ready:
            try:
                data = os.read(fd, EV_SIZE)
            except (BlockingIOError, OSError):
                continue
            if len(data) != EV_SIZE:
                continue
            _, _, ev_type, code, value = struct.unpack(EV_FMT, data)
            if ev_type != EV_KEY:
                continue
            if code == KEY_LEFTSHIFT:
                shift = value == 1
                continue
            if code == KEY_RIGHTSHIFT:
                shift = value == 1
                continue
            if value != 1:  # ignore releases and auto-repeat
                continue
            session = read_session()
            if session:
                handle_key(code, shift, session)


if __name__ == "__main__":
    sys.exit(main())