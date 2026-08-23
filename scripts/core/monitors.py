#!/usr/bin/env python3
"""Compositor detection and per-compositor monitor enumeration.

Output (stdout, JSON):
  {
    "compositor": "wayland" | "x11",
    "count": N,
    "monitors": [
      {"index": 0, "name": "HDMI-A-1", "width": 1920, "height": 1080,
       "x": 0, "y": 0, "scale": 1},
      ...
    ]
  }

The `index` matches the GDK monitor index used by `eww open --screen N`:
  - Wayland: wl_output binding order (wayland-info enumeration order).
  - X11:     xrandr --listmonitors order.

A cheap `--signature` mode reads only /sys/class/drm (no subprocess spawn) so
scripts/monitor_watch.py can poll for hotplug / mode changes almost for free.

Usage:
  ./monitors.py            # full JSON enumeration
  ./monitors.py --signature  # cheap connector+mode signature string
"""

import json
import os
import re
import subprocess
import sys

from detect import compositor as detect_compositor

SYSFS_DRM = "/sys/class/drm"


def drm_connectors():
    out = []
    try:
        for entry in sorted(os.listdir(SYSFS_DRM)):
            if not entry.startswith("card"):
                continue
            status_file = os.path.join(SYSFS_DRM, entry, "status")
            modes_file = os.path.join(SYSFS_DRM, entry, "modes")
            if not os.path.isfile(status_file):
                continue
            try:
                with open(status_file, encoding="utf-8") as f:
                    status = f.read().strip()
                mode = ""
                if os.path.isfile(modes_file):
                    with open(modes_file, encoding="utf-8") as f:
                        first = f.readline().strip()
                        if first:
                            mode = first
            except Exception:
                continue
            out.append({"name": entry, "status": status, "mode": mode})
    except Exception:
        pass
    return out


def _run(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=5)
    except Exception:
        return ""


def wayland_monitors():
    raw = _run(["wayland-info"])
    outputs = []  # (global_id, dict) in bind order
    zgxd = {}     # global_id -> zxdg data
    cur = None
    cur_id = None
    in_output = False
    mode = None
    for line in raw.splitlines():
        m = re.match(r"interface: 'wl_output',.*name:\s*(\d+)", line)
        if m:
            cur_id = int(m.group(1))
            cur = {
                "name": "",
                "x": 0,
                "y": 0,
                "scale": 1,
                "modes": [],
            }
            outputs.append((cur_id, cur))
            in_output = True
            continue
        if re.match(r"interface: 'zxdg_output_v1',", line):
            in_output = False
            continue
        if not in_output and cur_id is not None:
            zm = re.match(r"\s*output:\s*(\d+)", line)
            if zm:
                zgxd[int(zm.group(1))] = {"name": "", "x": None, "y": None, "w": None, "h": None}
                continue
            z = zgxd.get(cur_id)
            if z:
                nm = re.match(r"\s*name:\s*'([^']+)'", line)
                if nm:
                    z["name"] = nm.group(1)
                    continue
                lm = re.match(r"\s*logical_x:\s*(-?\d+),\s*logical_y:\s*(-?\d+)", line)
                if lm:
                    z["x"], z["y"] = int(lm.group(1)), int(lm.group(2))
                    continue
                lw = re.match(r"\s*logical_width:\s*(\d+),\s*logical_height:\s*(\d+)", line)
                if lw:
                    z["w"], z["h"] = int(lw.group(1)), int(lw.group(2))
                    continue
        if in_output and cur is not None:
            nm = re.match(r"\s*name:\s*(\S+)", line)
            if nm:
                cur["name"] = nm.group(1)
                continue
            xy = re.match(r"\s*x:\s*(-?\d+),\s*y:\s*(-?\d+),\s*scale:\s*(\d+)", line)
            if xy:
                cur["x"], cur["y"], cur["scale"] = int(xy.group(1)), int(xy.group(2)), int(xy.group(3))
                continue
            if re.match(r"\s*mode:\s*$", line):
                mode = {"width": 0, "height": 0, "flags": ""}
                cur["modes"].append(mode)
                continue
            if mode is not None:
                mm = re.match(r"\s*width:\s*(\d+)\s*px,\s*height:\s*(\d+)\s*px", line)
                if mm:
                    mode["width"], mode["height"] = int(mm.group(1)), int(mm.group(2))
                    continue
                fm = re.match(r"\s*flags:\s*(.+)", line)
                if fm:
                    mode["flags"] = fm.group(1)

    monitors = []
    index = 0
    for gid, mon in outputs:
        z = zgxd.get(gid, {})
        current = [m for m in mon["modes"] if "current" in m["flags"]]
        selected = (current or mon["modes"] or [None])[0]
        if selected is None:
            continue
        width = z.get("w") or (selected["width"] // mon["scale"] if selected["width"] else 0)
        height = z.get("h") or (selected["height"] // mon["scale"] if selected["height"] else 0)
        if not width or not height:
            continue
        monitors.append(
            {
                "index": index,
                "name": z.get("name") or mon["name"],
                "width": width,
                "height": height,
                "x": z.get("x") if z.get("x") is not None else mon["x"],
                "y": z.get("y") if z.get("y") is not None else mon["y"],
                "scale": mon["scale"],
            }
        )
        index += 1
    return monitors


def x11_monitors():
    raw = _run(["xrandr", "--listmonitors"])
    monitors = []
    for line in raw.splitlines():
        m = re.match(r"\s*(\d+):\s*([+*]*)(\S+)\s+(\d+)/[^x]*x(\d+)/[^+]*([+-]\d+)([+-]\d+)", line)
        if not m:
            continue
        monitors.append(
            {
                "index": int(m.group(1)),
                "name": m.group(3),
                "width": int(m.group(4)),
                "height": int(m.group(5)),
                "x": int(m.group(6)),
                "y": int(m.group(7)),
                "scale": 1,
            }
        )
    return monitors


def fallback_monitors():
    conn = [c for c in drm_connectors() if c["status"] == "connected"]
    if not conn:
        return [{"index": 0, "name": "default", "width": 1920, "height": 1080, "x": 0, "y": 0, "scale": 1}]
    monitors = []
    for index, c in enumerate(conn):
        w, h = 1920, 1080
        mm = re.match(r"(\d+)x(\d+)", c["mode"])
        if mm:
            w, h = int(mm.group(1)), int(mm.group(2))
        monitors.append({"index": index, "name": c["name"], "width": w, "height": h, "x": 0, "y": 0, "scale": 1})
    return monitors


def enumerate_monitors(compositor):
    if compositor == "wayland":
        monitors = wayland_monitors()
        if monitors:
            return monitors
    else:
        monitors = x11_monitors()
        if monitors:
            return monitors
    return fallback_monitors()


def signature():
    parts = []
    for c in drm_connectors():
        parts.append("%s=%s:%s" % (c["name"], c["status"], c["mode"]))
    if not parts:
        return "none"
    return "|".join(parts)


def main():
    compositor = detect_compositor()
    if "--signature" in sys.argv:
        print(signature())
        return
    monitors = enumerate_monitors(compositor)
    print(
        json.dumps(
            {"compositor": compositor, "count": len(monitors), "monitors": monitors},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
