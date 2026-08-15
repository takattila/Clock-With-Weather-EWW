#!/usr/bin/env python3
"""
WM-independent workarea detection and panel geometry computation.

The panel must stay inside the taskbar-free area (_NET_WORKAREA) on any window
manager (KDE, GNOME, XFCE, i3, ...), and it must be inset from the taskbar,
from the opposite screen edge AND from the lateral screen edge by the
configured gap (Req 2), so the free spacing stays symmetric no matter where
the taskbar sits:

  taskbar at top    -> panel top / bottom / right all gapped from their edges
  taskbar at bottom -> panel bottom / top / right all gapped from their edges
  taskbar at right  -> panel left / top / bottom all gapped (the panel moves
                       to the left edge)
  taskbar at left   -> panel right / top / bottom all gapped

The gap(s) come from config.yaml -> panel.gap (default: 16 px). panel.gap may
be a single number (all sides get the same gap) or a map with per-side keys,
e.g.:

  panel:
    gap: { top: 16, right: 16, bottom: 16, left: 16 }

Missing sides default to 16 px. The panel width is fixed at 250 px; the height
is the workarea height minus the top and bottom gaps.

Output (stdout, JSON):
  {
    "screen":     {"width": .., "height": ..},
    "workarea":   {"x": .., "y": .., "width": .., "height": ..},
    "taskbar":    "top" | "bottom" | "left" | "right" | "none",
    "panel":      {"x": .., "y": .., "width": .., "height": .., "anchor": ".."},
    "panel_gap":  {"top": .., "right": .., "bottom": .., "left": ..},
    "real_workarea": bool   # False when the X display was unreachable
  }

The panel x/y are the EWW :x / :y offsets for the given :anchor, ready to be
written into eww.yuck by start.sh. The offsets are interpreted differently
depending on the compositor:
  - Wayland (gtk layer-shell): relative to the WORKAREA top-left (the taskbar
    is an exclusive zone that shifts the window down/right).
  - X11: ABSOLUTE screen coordinates (no layer-shell exclusive zone), so the
    top-anchored y offset must include the workarea origin (wy). The "top
    right" anchor measures from the screen right edge (== workarea right) and
    the "top left" anchor is only used when the taskbar sits on the right edge.

Per-monitor mode (--per-monitor) reads a monitors JSON on stdin (from
scripts/monitors.py) and computes the panel geometry for every monitor:

  ./monitors.py | ./workarea.py --per-monitor --align right [config_dir]

`--align left|right` (default: right) forces the full-height panel onto the
left or right screen edge, overriding the taskbar-derived horizontal side
while keeping the height and the taskbar gaps.

Output (stdout, JSON):
  {
    "compositor": "wayland" | "x11",
    "monitors": [
      {"index": 0, "name": "..", "width": .., "height": ..,
       "panel": {"x": .., "y": .., "width": .., "height": .., "anchor": ".."}},
      ...
    ],
    "heights": [ .. ]    # distinct panel heights (for panel.py)
  }

The taskbar workarea is read through XWayland on Wayland too (KDE exposes
_NET_WORKAREA there, see find_xwayland_env). The taskbar workarea is
intersected with each monitor's rectangle, so every monitor the taskbar
overlaps keeps the taskbar inset while monitors outside the taskbar keep the
symmetric-gap full-height geometry. The panel height always stays inside the
monitor's own height, so a smaller secondary monitor gets a matching panel.

Usage: ./workarea.py [config_dir]
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time

import yaml

PANEL_WIDTH = 250


def find_xwayland_env():
    """Locate DISPLAY/XAUTHORITY for the running XWayland instance.

    The panel geometry scripts may run without the X environment exported
    (start.sh is often launched from the desktop session), while the taskbar
    workarea (_NET_WORKAREA) is only readable through XWayland. The compositor
    exposes its Xwayland display + auth file on the command line, so scan /proc
    for it instead of requiring the session to export DISPLAY/XAUTHORITY.
    Existing environment values always win.
    """
    env = {}
    try:
        import glob
        markers = (b"kwin_wayland", b"Xwayland", b"mutter", b"gnome-shell", b"weston")
        for path in glob.glob("/proc/[0-9]*/cmdline"):
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            parts = data.split(b"\0")
            if not parts or not any(m in parts[0] for m in markers):
                continue
            argv = [p.decode("utf-8", "replace") for p in parts if p]
            for idx, arg in enumerate(argv):
                if arg == "--xwayland-display" and idx + 1 < len(argv):
                    env.setdefault("DISPLAY", argv[idx + 1])
                elif arg == "--xwayland-xauthority" and idx + 1 < len(argv):
                    env.setdefault("XAUTHORITY", argv[idx + 1])
    except Exception:
        pass
    return env


def get_net_workarea():
    for key in ("DISPLAY", "XAUTHORITY"):
        if key not in os.environ:
            discovered = find_xwayland_env().get(key)
            if discovered:
                os.environ[key] = discovered
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
                return x, y, w, h
    except Exception:
        pass
    return None


def kde_panel_frame(screen):
    """Query the KDE Plasma taskbar's visual frame via the KWin scripting API.

    _NET_WORKAREA only reports the taskbar's exclusive zone, which is smaller
    than the panel's actual frame (floating panels add margins around it). The
    widget must keep `gap` away from the *frame*, so the top/bottom gap matches
    the config value on screen. Returns (x, y, w, h) of the largest non-desktop
    plasmashell surface, or None when unavailable (non-KDE, no qdbus6/journald
    ...), in which case the caller falls back to the exclusive zone.
    """
    try:
        script = os.path.join(tempfile.gettempdir(), "kwin_panel_dump.js")
        with open(script, "w", encoding="utf-8") as f:
            f.write(
                "var wl = workspace.windowList();\n"
                "for (var i = 0; i < wl.length; i++) {\n"
                "  var w = wl[i];\n"
                "  var g = w.frameGeometry;\n"
                "  if (w.resourceClass === 'plasmashell' && g.width > 200 && g.height > 10) {\n"
                "    console.log('KPANEL ' + g.x + ',' + g.y + ',' + g.width + ',' + g.height);\n"
                "  }\n"
                "}\n"
                "console.log('KPANEL DONE');\n"
            )
        env = dict(os.environ)
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/%d/bus" % os.getuid())
        env.setdefault("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
        subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", script],
            env=env, capture_output=True, text=True, timeout=5,
        )
        subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.start"],
            env=env, capture_output=True, text=True, timeout=5,
        )
        sw, sh = screen
        best = None
        for _ in range(3):
            time.sleep(1.0)
            try:
                out = subprocess.check_output(
                    ["journalctl", "--user", "-o", "cat", "--since", "15 seconds ago"],
                    stderr=subprocess.DEVNULL, text=True, timeout=5,
                )
            except Exception:
                continue
            for line in out.splitlines():
                m = re.match(r"^KPANEL\s+(-?\d+),(-?\d+),(\d+),(\d+)$", line.strip())
                if not m:
                    continue
                x, y, w, h = (int(v) for v in m.groups())
                if w >= sw - 1 and h >= sh - 1:
                    continue
                if best is None or w * h > best[2] * best[3]:
                    best = (x, y, w, h)
            if best is not None:
                break
        return best
    except Exception:
        return None


def get_xrandr_resolution():
    try:
        out = subprocess.check_output(
            ["xrandr"], stderr=subprocess.DEVNULL, text=True, timeout=3
        )
        m = re.search(r"current\s+(\d+)\s*x\s*(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


def _parse_gap_value(value):
    """Coerce a panel.gap value to an int, tolerating '5,' / ' 5 ' forms.

    PyYAML parses block-style `top: 5,` as the string "5,"; strip separators
    and whitespace so the comma form works like the flow-style map.
    """
    try:
        return int(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def load_gaps(config_dir):
    """Read the per-side panel gaps from config.yaml -> panel.gap.

    panel.gap may be a single number (all sides get it) or a map with any of
    the top/right/bottom/left keys (missing sides default to 16 px). Invalid
    values fall back to the default on each side.
    """
    default = 16
    gaps = {"top": default, "right": default, "bottom": default, "left": default}
    try:
        with open(os.path.join(config_dir, "config.yaml"), "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        panel = cfg.get("panel") or {}
        raw = panel.get("gap", default)
        if isinstance(raw, dict):
            for side in gaps:
                if side in raw:
                    v = _parse_gap_value(raw[side])
                    gaps[side] = v if v is not None else default
        else:
            v = _parse_gap_value(raw)
            if v is not None:
                gaps = dict.fromkeys(gaps, v)
    except Exception:
        pass
    return gaps


def detect_taskbar(screen, workarea):
    sw, sh = screen
    wx, wy, ww, wh = workarea
    if wy > 0 and wx == 0 and ww == sw:
        return "top"
    if wy + wh < sh and wx == 0 and ww == sw:
        return "bottom"
    if wx + ww < sw:
        return "right"
    if wx > 0:
        return "left"
    return "none"


def detect_compositor():
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("SWAYSOCK"):
        return "wayland"
    return "x11"


def compute_panel(screen, workarea, taskbar, gaps, compositor, kde_frame=None):
    # NOTE: on KDE/wayland (gtk layer-shell) the :x/:y offsets are margins
    # measured relative to the WORKAREA (the taskbar is an exclusive zone that
    # shifts the window down/right): screen_position = workarea_edge + offset.
    # So the top-anchored y offset is just the top gap (workarea top is the
    # taskbar bottom), and a `taskbar_h + bottom_gap` bottom margin applies when
    # the taskbar sits at the bottom (the bottom exclusive zone shifts the
    # window up).
    # On X11 (see eww display_backend.rs -> get_window_rectangle) there is no
    # layer-shell: the :x/:y are ABSOLUTE offsets from the monitor edge given by
    # the anchor, so a top-anchored panel must be offset below the taskbar by
    # workarea.y (wy). The "top right" anchor measures from the right edge
    # (workarea right == screen right) and the "top left" anchor is used only
    # when the taskbar sits on the right edge.
    # The panel is inset from the taskbar and from the opposite screen edge by
    # the corresponding per-side gap and from the lateral screen edge by the
    # lateral gap, so the free spacing around the panel is configurable on
    # every side (Req 2).
    sw, sh = screen
    wx, wy, ww, wh = workarea
    gt, gr, gb, gl = gaps["top"], gaps["right"], gaps["bottom"], gaps["left"]
    width = PANEL_WIDTH
    height = max(wh - gt - gb, 100)
    x11 = compositor == "x11"
    top_origin = wy if x11 else 0

    # The Plasma taskbar's visual frame may extend beyond the exclusive zone
    # reported by _NET_WORKAREA (floating-panel margins), so the panel must be
    # inset by the top/bottom gap from the *frame* edge, not from the exclusive
    # zone, to match the config value on screen. frame_edge is that taskbar-side
    # edge.
    frame_edge = None
    if kde_frame:
        fx, fy, fw, fh = kde_frame
        if taskbar == "top":
            frame_edge = fy + fh
        elif taskbar == "bottom":
            frame_edge = fy

    if taskbar == "bottom":
        anchor = "bottom right"
        x = gr
        if frame_edge is not None:
            panel_bottom = frame_edge - gb
            y = (sh - panel_bottom) if x11 else (wy + wh - panel_bottom)
            height = max(panel_bottom - (wy + gt), 100)
        else:
            y = (sh - (wy + wh)) + gb
    elif taskbar == "right":
        anchor = "top left"
        x = gl
        y = top_origin + gt
    elif taskbar == "left":
        anchor = "top right"
        x = gr
        y = top_origin + gt
    elif taskbar == "none":
        anchor = "top right"
        x = gr
        y = top_origin + gt
        height = max(sh - gt - gb, 100)
    else:  # taskbar == "top"
        anchor = "top right"
        x = gr
        if frame_edge is not None:
            y = top_origin + (frame_edge - wy) + gt
            height = max(sh - frame_edge - gt - gb, 100)
        else:
            y = top_origin + gt
    return {"x": x, "y": y, "width": width, "height": height, "anchor": anchor}


def monitor_screen(m):
    return m["width"], m["height"]


def align_panel_side(panel, gaps, side):
    """Force the panel onto the left or right screen edge.

    The panel keeps its full height and taskbar inset; only the anchor and the
    horizontal offset change. `side` is "left" or "right" (right = default).
    """
    if side != "left":
        return panel
    anchor = panel["anchor"]
    if anchor == "bottom right":
        anchor = "bottom left"
    elif anchor == "top right":
        anchor = "top left"
    panel["anchor"] = anchor
    panel["x"] = gaps["left"]
    return panel


def parse_align_arg():
    align = "right"
    for i, a in enumerate(sys.argv):
        if a == "--align" and i + 1 < len(sys.argv):
            align = sys.argv[i + 1].lower()
        elif a.startswith("--align="):
            align = a.split("=", 1)[1].lower()
    return align if align in ("left", "right") else "right"


def global_bounds(monitors):
    tw = max(m["x"] + m["width"] for m in monitors) if monitors else 0
    th = max(m["y"] + m["height"] for m in monitors) if monitors else 0
    return tw, th


def compute_per_monitor(monitors, gaps, compositor, panel_alignment="right"):
    result = []
    workarea = get_net_workarea()
    global_screen = global_bounds(monitors)
    global_workarea = workarea if workarea else (0, 0, global_screen[0], global_screen[1])
    taskbar = detect_taskbar(global_screen, global_workarea)

    # The taskbar's visual frame (with floating-panel margins) is what the panel
    # must keep the top/bottom gap away from, so the gap matches the config.
    frame = kde_panel_frame(global_screen) if taskbar in ("top", "bottom") else None

    for m in monitors:
        screen = monitor_screen(m)

        # Intersect the (global, taskbar-free) workarea with this monitor's
        # rectangle, in monitor-local coordinates. That way the panel is inset
        # from the taskbar on every monitor the taskbar overlaps while its
        # height never exceeds the monitor's own height -- with mixed-resolution
        # setups the global workarea height (from the tallest screen) must not
        # leak onto a shorter monitor. When the taskbar only overlaps part of
        # the desktop (e.g. it sits on the primary only), the intersection for
        # the other monitors collapses to their full height with no taskbar.
        mx, my = m["x"], m["y"]
        wx0 = max(global_workarea[0] - mx, 0)
        wy0 = max(global_workarea[1] - my, 0)
        wx1 = min(global_workarea[0] + global_workarea[2], mx + screen[0]) - mx
        wy1 = min(global_workarea[1] + global_workarea[3], my + screen[1]) - my
        if wx1 > wx0 and wy1 > wy0:
            local_workarea = (wx0, wy0, wx1 - wx0, wy1 - wy0)
            local_taskbar = detect_taskbar(screen, local_workarea)
        else:
            local_workarea = (0, 0, screen[0], screen[1])
            local_taskbar = "none"

        # Translate the taskbar frame into this monitor's local coordinates;
        # it is only relevant on the monitor(s) it geometrically overlaps.
        local_frame = None
        if frame:
            fx, fy, fw, fh = frame
            if (
                fx < mx + screen[0]
                and fx + fw > mx
                and fy < my + screen[1]
                and fy + fh > my
            ):
                local_frame = (fx - mx, fy - my, fw, fh)

        panel = compute_panel(
            screen, local_workarea, local_taskbar, gaps, compositor, kde_frame=local_frame
        )
        panel = align_panel_side(panel, gaps, panel_alignment)
        result.append(
            {
                "index": m["index"],
                "name": m["name"],
                "width": screen[0],
                "height": screen[1],
                "panel": panel,
            }
        )

    heights = sorted({r["panel"]["height"] for r in result}, reverse=True)
    return {"compositor": compositor, "monitors": result, "heights": heights}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    config_dir = os.path.abspath(args[-1] if args else os.getcwd())
    gaps = load_gaps(config_dir)

    if "--per-monitor" in sys.argv:
        compositor = detect_compositor()
        monitors = json.load(sys.stdin).get("monitors", [])
        panel_alignment = parse_align_arg()
        print(json.dumps(compute_per_monitor(monitors, gaps, compositor, panel_alignment)))
        return

    screen = get_xrandr_resolution()
    workarea = get_net_workarea()
    real = screen is not None and workarea is not None
    if screen is None:
        screen = (1920, 1080)
    if workarea is None:
        workarea = (0, 0, screen[0], screen[1])

    compositor = detect_compositor()
    taskbar = detect_taskbar(screen, workarea)
    frame = kde_panel_frame(screen) if taskbar in ("top", "bottom") else None
    panel = compute_panel(screen, workarea, taskbar, gaps, compositor, kde_frame=frame)
    panel = align_panel_side(panel, gaps, parse_align_arg())

    # PANEL_HEIGHT env override still wins (used by panel.py to size the charts).
    env_override = os.environ.get("PANEL_HEIGHT") or os.environ.get("EWW_PANEL_HEIGHT")
    if env_override:
        panel["height"] = int(env_override)

    result = {
        "screen": {"width": screen[0], "height": screen[1]},
        "workarea": {
            "x": workarea[0],
            "y": workarea[1],
            "width": workarea[2],
            "height": workarea[3],
        },
        "taskbar": taskbar,
        "panel": panel,
        "panel_gap": gaps,
        "compositor": compositor,
        "real_workarea": real,
    }
    print(json.dumps(result))
    print(
        "screen=%dx%d workarea=%d,%d %dx%d taskbar=%s gap=t%d,r%d,b%d,l%d panel=%s %dx%d+%d+%d"
        % (
            screen[0],
            screen[1],
            workarea[0],
            workarea[1],
            workarea[2],
            workarea[3],
            taskbar,
            gaps["top"],
            gaps["right"],
            gaps["bottom"],
            gaps["left"],
            panel["anchor"],
            panel["width"],
            panel["height"],
            panel["x"],
            panel["y"],
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
