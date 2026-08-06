#!/usr/bin/env python3
"""
WM-independent screen workarea detection.

The panel height must match the taskbar-free area under any window manager
(KDE, GNOME, XFCE, i3, ...). Every EWMH-compliant WM keeps the root window
property _NET_WORKAREA up to date (x, y, width, height of the area not
covered by taskbars/panels), so we read it via xprop.

Outputs two integers: "Y HEIGHT" (top edge of the usable area, and its
height) in pixels. Falls back to the PANEL_HEIGHT env override, then to the
xrandr full-screen resolution, then to 1080.

Usage: ./workarea.py [config_dir]
"""

import os
import re
import subprocess
import sys


def get_net_workarea():
    try:
        out = subprocess.check_output(
            ["xprop", "-root", "_NET_WORKAREA"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
        m = re.search(r"=\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)", out)
        if m:
            x, y, w, h = (int(v) for v in m.groups())
            if w > 0 and h > 0:
                return y, h
    except Exception:
        pass
    return None


def get_xrandr_resolution():
    try:
        out = subprocess.check_output(
            ["xrandr"], stderr=subprocess.DEVNULL, text=True, timeout=3
        )
        m = re.search(r"current\s+\d+\s*x\s*(\d+)", out)
        if m:
            return 0, int(m.group(1))
    except Exception:
        pass
    return None


def main():
    env_override = os.environ.get("PANEL_HEIGHT") or os.environ.get("EWW_PANEL_HEIGHT")
    res = get_net_workarea()
    if res is None:
        res = get_xrandr_resolution()
    if res is None:
        res = (0, int(env_override) if env_override else 1080)
    y, h = res
    print("%d %d" % (y, h))


if __name__ == "__main__":
    main()
