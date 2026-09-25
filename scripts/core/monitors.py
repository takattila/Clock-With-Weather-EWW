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

The `index` is the enumeration order and is what `eww open --screen N` uses, but
it must NOT be used to decide which physical monitor a widget belongs to: GDK
enumerates monitors in output-binding order, which can differ from the order
below after a hotplug (e.g. GDK: eDP-1=0, DP-1=1 vs xrandr: DP-1=0, eDP-1=1).
Use the connector `name` for placement; `index` is only for per-monitor config
keys, which are re-derived on every relayout anyway.

A cheap `--signature` mode reads only /sys/class/drm (no subprocess spawn) so
scripts/core/monitor_watch.py can poll for hotplug / mode changes almost for
free. `--topology` is the complementary, more expensive signature of the
ACTIVE monitor layout (compositor enumeration): it also sees a monitor that is
only disabled, or a resolution/position change, which leave /sys untouched.

Usage:
  ./monitors.py            # full JSON enumeration
  ./monitors.py --signature  # cheap connector+mode+enable signature string
  ./monitors.py --topology   # active monitor layout signature string
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
            enabled_file = os.path.join(SYSFS_DRM, entry, "enabled")
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
                # `enabled` is the kernel-side CRTC state of the connector:
                # "disabled" while the output is switched off (`xrandr --output
                # X --off`, "turn off display" in the settings dialog) even
                # though the cable is still plugged in. Older kernels may not
                # have the file -> treated as unknown.
                enabled = ""
                if os.path.isfile(enabled_file):
                    with open(enabled_file, encoding="utf-8") as f:
                        enabled = f.read().strip()
            except Exception:
                continue
            out.append(
                {"name": entry, "status": status, "mode": mode, "enabled": enabled}
            )
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


def get_net_workarea():
    """Read the _NET_WORKAREA rectangle(s) (EWMH) from the X11 root.

    Returns (x, y, w, h) of the first rectangle, or None when unavailable
    (no X / no EWMH-compliant window manager). The work area is the desktop
    minus the taskbar/panel exclusive zone, so it can be used to size a
    floating window as "screen height minus taskbar height".
    """
    try:
        out = subprocess.check_output(
            ["xprop", "-root", "_NET_WORKAREA"],
            stderr=subprocess.DEVNULL, text=True, timeout=3,
        )
        m = re.search(r"=\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)", out)
        if m:
            x, y, w, h = (int(v) for v in m.groups())
            if w > 0 and h > 0:
                return x, y, w, h
    except Exception:
        pass
    return None


def usable_height(mon, workarea=None):
    """Usable display height of one monitor = full height minus the taskbar
    inset it overlaps, derived from the _NET_WORKAREA rectangle.

    A work area that does not reach a monitor horizontally means that monitor
    sits outside the taskbar's span and keeps its full height.
    """
    height = int(mon.get("height", 0))
    if not height or not workarea:
        return height
    wax, way, waw, wah = (int(v) for v in workarea)
    mleft, mright = int(mon.get("x", 0)), int(mon.get("x", 0)) + int(mon.get("width", 0))
    if mleft >= wax + waw or mright <= wax:
        return height
    mtop, mbottom = int(mon.get("y", 0)), int(mon.get("y", 0)) + height
    top = max(0, way - mtop)
    bottom = max(0, mbottom - (way + wah))
    return max(0, height - top - bottom)


def adaptive_window_height(monitors, natural_h, workarea=None):
    """Window height that fits EVERY monitor.

    Uses the smallest per-monitor usable height as the basis (per the design,
    so a draggable window can be placed on the smallest screen), capped by the
    window's own natural height so a tall-enough desktop never stretches it.
    """
    heights = [usable_height(m, workarea) for m in monitors] or [natural_h]
    return min(int(natural_h), min(heights))


def desktop_bounds(monitors):
    """Bounding box (x0, y0, w, h) covering all monitors in global coords."""
    if not monitors:
        return 0, 0, 0, 0
    x0 = min(int(m.get("x", 0)) for m in monitors)
    y0 = min(int(m.get("y", 0)) for m in monitors)
    x1 = max(int(m.get("x", 0)) + int(m.get("width", 0)) for m in monitors)
    y1 = max(int(m.get("y", 0)) + int(m.get("height", 0)) for m in monitors)
    return x0, y0, x1 - x0, y1 - y0


def signature():
    parts = []
    for c in drm_connectors():
        parts.append("%s=%s:%s:%s" % (c["name"], c["status"], c["mode"], c.get("enabled", "")))
    if not parts:
        return "none"
    return "|".join(parts)


def topology_signature(monitors=None):
    """Signature of the ACTIVE monitor layout, from the compositor's own list.

    --signature (the DRM connector state) cannot see everything that changes
    the layout: a monitor that is merely DISABLED (cable still plugged in, the
    DRM status/modes stay the same) or a resolution/rotation/position change
    does not touch /sys at all. Without seeing those, the windows of the
    vanished monitor are never closed and the compositor clamps them onto the
    remaining screen.

    This signature is built from the real enumeration (`xrandr --listmonitors`
    on X11, `wayland-info` on Wayland), so it changes for every layout change.
    It costs a subprocess, hence it is polled slowly by monitor_watch.py as a
    safety net next to the cheap --signature poll.
    """
    if monitors is None:
        monitors = enumerate_monitors(detect_compositor())
    parts = [
        "%s:%dx%d+%d+%d"
        % (
            m.get("name", ""),
            int(m.get("width", 0)),
            int(m.get("height", 0)),
            int(m.get("x", 0)),
            int(m.get("y", 0)),
        )
        for m in monitors
    ]
    # Sorted: a pure ORDER change (e.g. `xrandr --primary` swapping the primary
    # monitor) keeps every index -> monitor mapping and therefore every window
    # and config key exactly where it is, so it must not trigger a relayout.
    return "|".join(sorted(parts)) if parts else "none"


def main():
    compositor = detect_compositor()
    if "--signature" in sys.argv:
        print(signature())
        return
    if "--topology" in sys.argv:
        print(topology_signature())
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
