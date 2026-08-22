#!/usr/bin/env python3
"""Shared helpers for the invisible keyboard daemon (scripts/input_daemon.py).

The popup / Move-Resize scripts flip a session file (generated/input_session.json)
that tells the daemon which keys are relevant right now; the close scripts remove
it so the daemon goes back to idle:

  {"mode": "ctx"}                          -- ctx.py / about.py (popup open)
  {"mode": "move", "widget": "clock", "monitor": 0}   -- move.py (Move/Resize)

They also make sure the daemon is running: start.sh starts it via passwordless
sudo at startup, and these helpers restart it (lazy fallback) if it died.

Usage:
  import session
  session.set_session({"mode": "ctx"})
  session.clear_session()
"""

import json
import os
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/
# scripts/core/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
DAEMON_PIDFILE = os.path.join(CONFIG_DIR, "run", "input_daemon.pid")
DAEMON_SCRIPT = os.path.join(SCRIPTS_DIR, "move", "input_daemon.py")


def daemon_alive():
    try:
        with open(DAEMON_PIDFILE) as fh:
            pid = int(fh.read().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def start_daemon():
    """Start the input daemon via passwordless sudo if it is not running."""
    if daemon_alive():
        return
    env = {
        key: val for key, val in os.environ.items()
        if key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE") and val
    }
    cmd = ["sudo", "-n", "env"]
    cmd += ["%s=%s" % (key, val) for key, val in env.items()]
    cmd += ["setsid", "python3", DAEMON_SCRIPT]
    try:
        subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception:
        pass


def set_session(data):
    start_daemon()
    try:
        os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
        with open(SESSION_FILE, "w") as fh:
            json.dump(data, fh)
    except Exception:
        pass


def clear_session():
    try:
        if os.path.exists(SESSION_FILE):
            os.unlink(SESSION_FILE)
    except Exception:
        pass