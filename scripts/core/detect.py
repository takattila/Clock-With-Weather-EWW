#!/usr/bin/env python3
"""Compositor-session detection shared by monitors.py and workarea.py.

Both modules MUST agree on "wayland" vs "x11": eww opens native layer-shell
windows in the former (exact margin placement) and WM-managed XWayland
windows in the latter -- a mismatch silently breaks positioning on KWin,
which ignores client-requested X11 window positions (measured: widgets could
not be parked at screen edges when the stack was started without
WAYLAND_DISPLAY and fell back to X11-compat windows).

This process's environment is checked first, but it is NOT always complete:
shells launched via SSH or some autostart contexts carry DISPLAY (XWayland)
without WAYLAND_DISPLAY even on a Wayland desktop. The session's own
processes are therefore inspected as well:

  1. WAYLAND_DISPLAY / SWAYSOCK in this environment
  2. XDG_SESSION_TYPE == "wayland"
  3. any running compositor whose NAME is Wayland-only
     (kwin_wayland, sway, labwc, Hyprland, wayfire, river)
  4. gnome-shell with WAYLAND_DISPLAY in ITS environment (the binary name is
     ambiguous -- GNOME runs on X11 too)

Only when every probe fails is "x11" reported.
"""

import os

WAYLAND_COMPOSITORS = {
    "kwin_wayland",
    "sway",
    "labwc",
    "Hyprland",
    "wayfire",
    "river",
}


def _running_pids():
    try:
        return [p for p in os.listdir("/proc") if p.isdigit()]
    except Exception:
        return []


def _proc_comm(pid):
    try:
        with open("/proc/%s/comm" % pid, encoding="utf-8") as fh:
            return fh.read().strip()
    except Exception:
        return ""


def _proc_environ_has(pid, key):
    try:
        with open("/proc/%s/environ" % pid, "rb") as fh:
            raw = fh.read()
    except Exception:
        return False
    prefix = (key + "=").encode()
    return any(entry.startswith(prefix) for entry in raw.split(b"\0"))


def _real_session_procs():
    """(comm, environ_has_WAYLAND_DISPLAY) of candidate compositor procs."""
    out = []
    for pid in _running_pids():
        comm = _proc_comm(pid)
        if not comm:
            continue
        if comm in WAYLAND_COMPOSITORS or comm == "gnome-shell":
            out.append((comm, _proc_environ_has(pid, "WAYLAND_DISPLAY")))
    return out


def compositor(env=None, procs=None):
    """'wayland' | 'x11'.

    `env` defaults to os.environ; `procs` defaults to the real session
    process scan. Tests inject both.
    """
    env = dict(os.environ) if env is None else env
    if env.get("WAYLAND_DISPLAY") or env.get("SWAYSOCK"):
        return "wayland"
    if str(env.get("XDG_SESSION_TYPE", "")).strip().lower() == "wayland":
        return "wayland"
    for comm, has_wayland_display in (
        _real_session_procs() if procs is None else procs
    ):
        if comm in WAYLAND_COMPOSITORS:
            # The binary name itself is Wayland-only -- no env needed.
            return "wayland"
        if comm == "gnome-shell" and has_wayland_display:
            return "wayland"
    return "x11"
