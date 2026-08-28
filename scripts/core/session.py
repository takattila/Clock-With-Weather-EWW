#!/usr/bin/env python3
"""Shared helpers for the invisible keyboard daemon (scripts/input_daemon.py).

The popup / Move-Resize scripts flip a session file (generated/input_session.json)
that tells the daemon which keys are relevant right now; the close scripts remove
it so the daemon goes back to idle:

  {"mode": "ctx"}                          -- ctx.py / about.py (popup open)
  {"mode": "move", "widget": "clock", "monitor": 0}   -- move.py (Move/Resize)
  {"mode": "gap", "widget": "clock", "monitor": 0}    -- gap_ctl.py (panel gap)
  {"mode": "weather", "widget": "clock", "monitor": 0} -- weather_ctl.py

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


DAEMON_MATCH = "scripts/move/input_daemon.py"


def _own_chain_pids():
    """PIDs of this process's ancestor chain (for pgrep self-exclusion)."""
    pids = set()
    pid = os.getpid()
    while pid and pid > 1 and pid not in pids:
        pids.add(pid)
        try:
            with open("/proc/%d/stat" % pid) as fh:
                pid = int(fh.read().split(") ", 1)[1].split()[0])
        except Exception:
            break
    return pids


def stray_daemon_pids():
    """Running input_daemon PIDs that are NOT on our own ancestor chain."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", DAEMON_MATCH], capture_output=True, text=True
        ).stdout
    except Exception:
        return []
    own = _own_chain_pids()
    return [int(p) for p in out.split() if p.isdigit() and int(p) not in own]


def daemon_alive():
    # Fast path: the pidfile written by the last spawn points at a live
    # process. Fallback: a running instance WITHOUT a valid pidfile entry
    # still counts (pidfiles get overwritten by later spawns, which is how
    # duplicate daemons used to accumulate unnoticed).
    try:
        with open(DAEMON_PIDFILE) as fh:
            pid = int(fh.read().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        pass
    return bool(stray_daemon_pids())


def sweep_stray_daemons():
    """TERM (then KILL) input_daemon instances not covered by the pidfile."""
    import time

    strays = stray_daemon_pids()
    for pid in strays:
        try:
            os.kill(pid, 15)
        except Exception:
            pass
    deadline = time.time() + 1.5
    while time.time() < deadline:
        strays = [p for p in strays if os.path.exists("/proc/%d" % p)]
        if not strays:
            break
        time.sleep(0.1)
    for pid in strays:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def start_daemon():
    """Start the input daemon via passwordless sudo if it is not running.

    Any leftover daemon instance is swept first: spawning without sweeping
    accumulated duplicates whenever the pidfile had been overwritten by a
    later start while an older daemon kept running.
    """
    if daemon_alive():
        return
    sweep_stray_daemons()
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