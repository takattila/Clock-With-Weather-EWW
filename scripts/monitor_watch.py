#!/usr/bin/env python3
"""Monitor hotplug watcher.

Detects display changes (monitor connect/disconnect, resolution changes) and
re-lays-out the widget windows by calling `start.sh --relayout`.

It is event-driven: a background thread streams `udevadm monitor` (DRM events)
and a cheap ~5s signature poll of /sys/class/drm (no subprocess spawn) acts as
a safety net. Steady-state CPU is effectively zero.
"""

import os
import queue
import subprocess
import sys
import threading
import time

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONITORS = os.path.join(DIR, "scripts", "monitors.py")
START = os.path.join(DIR, "scripts", "start.sh")

POLL_INTERVAL = 5
SETTLE = 0.8


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


def relayout():
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

    last = signature()
    while True:
        if proc is not None and proc.poll() is None:
            try:
                q.get(timeout=POLL_INTERVAL)
            except queue.Empty:
                pass
        else:
            time.sleep(POLL_INTERVAL)

        now = signature()
        if now != last:
            last = now
            time.sleep(SETTLE)
            last = signature()
            log("monitor change detected; re-laying-out")
            relayout()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
