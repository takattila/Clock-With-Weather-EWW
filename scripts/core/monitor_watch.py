#!/usr/bin/env python3
"""Monitor hotplug watcher.

Detects display changes (monitor connect/disconnect, resolution changes) and
re-lays-out the widget windows by calling `start.sh --relayout`.

It is event-driven: a background thread streams `udevadm monitor` (DRM events)
and a cheap ~5s signature poll of /sys/class/drm (no subprocess spawn) acts as
a safety net. Steady-state CPU is effectively zero.

A /sys-only poll cannot see every layout change: disabling a monitor
(`xrandr --output X --off`, "turn off display" in the settings dialog) or
changing a resolution/position leaves the DRM connector state untouched, and
then the windows of the vanished monitor are never re-laid-out (the compositor
clamps them onto the remaining screen). So the ACTIVE layout is polled too:

  - X11 with python-xlib (optional dependency, `apt install python3-xlib`):
    the monitor list is read straight from the X server, ~0.2 ms per poll on a
    warm connection, so every POLL_INTERVAL it sees every layout change
    (hotplug, disable, resolution, position, rotation).
  - Otherwise (Wayland, or no python-xlib) the compositor's own monitor list
    is re-read through `monitors.py --topology` every TOPOLOGY_INTERVAL
    seconds. That spawns a subprocess (~0.3 s), hence the slow cadence.
"""

import os
import queue
import subprocess
import sys
import threading
import time

try:  # optional: enables the ~free X11 topology poll
    from Xlib import display as _xdisplay
    from Xlib.ext import randr as _xrandr
except ImportError:  # pragma: no cover - depends on the host packages
    _xdisplay = None
    _xrandr = None

# scripts/core/ -> repo (widget) root
DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MONITORS = os.path.join(DIR, "scripts", "core", "monitors.py")
START = os.path.join(DIR, "scripts", "bin", "start.sh")
# ctx.py caches the monitor enumeration for fast right-clicks; a hotplug
# must invalidate it so the next click sees the new topology.
MONITORS_CACHE = os.path.join(DIR, "generated", "monitors-cache.json")

POLL_INTERVAL = 5
# Fallback for when the X11 topology poll is unavailable: the compositor
# enumeration subprocess runs at most this often.
TOPOLOGY_INTERVAL = 30
SETTLE = 0.8

# Persistent X connection for the topology poll (see x11_topology).
_x_conn = None


def signature():
    try:
        out = subprocess.check_output(
            [sys.executable, MONITORS, "--signature"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except Exception:
        return ""


def topology_signature():
    """Signature of the active monitor layout (see monitors.py --topology)."""
    try:
        out = subprocess.check_output(
            [sys.executable, MONITORS, "--topology"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        return out.strip()
    except Exception:
        return ""


def _x_monitor_signature(dpy, root):
    """Monitor list of an X server as "name:WxH+X+Y|...", sorted.

    Split out from x11_topology so it can be tested without an X server.
    """
    out = []
    for mon in _xrandr.get_monitors(root).monitors:
        out.append(
            "%s:%dx%d+%d+%d"
            % (
                dpy.get_atom_name(mon.name),
                mon.width_in_pixels,
                mon.height_in_pixels,
                mon.x,
                mon.y,
            )
        )
    return "|".join(sorted(out))


def x11_topology():
    """Live monitor layout from the X server, or "" when unavailable.

    One XRRGetMonitors round trip on a warm connection costs ~0.2 ms versus
    ~220 ms for the `xrandr` subprocess, so this can run on every poll and it
    reflects the ACTIVE layout: hotplug, `xrandr --off`, resolution, position
    and rotation changes all change it. Returns "" on Wayland, when python-xlib
    is not installed, or without a usable X connection -- the caller then falls
    back to topology_signature() on its slow cadence.
    """
    global _x_conn
    if _xdisplay is None:
        return ""
    try:
        if _x_conn is None:
            _x_conn = _xdisplay.Display()
        dpy = _x_conn
        return _x_monitor_signature(dpy, dpy.screen().root)
    except Exception:
        # Dead connection (X server restarted, DISPLAY gone): drop it so the
        # next poll reconnects instead of silently reporting nothing.
        if _x_conn is not None:
            try:
                _x_conn.close()
            except Exception:
                pass
        _x_conn = None
        return ""


def relayout():
    try:
        os.remove(MONITORS_CACHE)
    except OSError:
        pass
    try:
        subprocess.run([START, "--relayout"], timeout=120)
    except Exception:
        pass


def udev_reader(proc, q):
    try:
        for line in iter(proc.stdout.readline, ""):
            if line:
                q.put(line)
    except Exception:
        pass


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)


def main():
    config_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    log("watching for monitor changes (%s)" % config_dir)

    proc = None
    q = queue.Queue()
    try:
        proc = subprocess.Popen(
            ["udevadm", "monitor", "--subsystem-match=drm"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        threading.Thread(target=udev_reader, args=(proc, q), daemon=True).start()
    except Exception:
        proc = None

    # Detection state: the cheap DRM signature plus the ACTIVE layout. On X11
    # the layout comes from the X server on every poll; the subprocess check
    # only runs (and its value is only kept) when that is unavailable.
    last_cheap = signature()
    last_topo = x11_topology() or topology_signature()
    # Value of the slow compositor check; only consulted when the X11 fast path
    # is unavailable, so it starts out as whatever the initial sample was.
    last_slow = last_topo
    next_slow = time.monotonic() + TOPOLOGY_INTERVAL
    while True:
        if proc is not None and proc.poll() is None:
            try:
                q.get(timeout=POLL_INTERVAL)
            except queue.Empty:
                pass
        else:
            time.sleep(POLL_INTERVAL)

        now_cheap = signature()
        now_topo = x11_topology()
        if not now_topo:  # no X11 fast path: slow compositor check on its own
            if time.monotonic() >= next_slow:
                next_slow = time.monotonic() + TOPOLOGY_INTERVAL
                last_slow = now_topo = topology_signature()
            else:
                now_topo = last_slow
        if (now_cheap, now_topo) == (last_cheap, last_topo):
            continue
        last_cheap, last_topo = now_cheap, now_topo
        time.sleep(SETTLE)
        last_cheap = signature()
        last_topo = x11_topology() or topology_signature()
        log("monitor change detected; re-laying-out")
        relayout()
        next_slow = time.monotonic() + TOPOLOGY_INTERVAL


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
