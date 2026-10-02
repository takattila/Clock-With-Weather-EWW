#!/usr/bin/env python3
"""Translate a monitor enumeration index into the selector eww/GDK accepts.

eww resolves `:monitor` / `--screen` against the monitor names GDK reports, and
on Wayland those are the EDID **model** names, NOT the DRM connector names:

    connector HDMI-A-1  ->  GDK model "Smart TV"
    connector DP-2      ->  GDK model "IRT-UW3480"

Handing eww the connector name fails outright -- it does not silently fall back:

    Failed to get monitor HDMI-A-1
    The available monitors are:
        [0] Smart TV
        [1] IRT-UW3480

Which pushed every window open (and every right-click overlay) onto the index
fallback -- exactly the order-dependent path this project avoids on purpose,
see start.sh's open_on_monitor and the monitor_selector() of ctx.py/about.py.
Note this is not specific to the virtual DP-2 output: on this machine
HDMI-A-1's EDID name is "Smart TV" either, so the name never resolved.

So ask GDK directly (python3-gi, the same GDK eww itself uses) and match its
monitors against the enumeration by GEOMETRY. Neither side's index order can
then affect the result.

Two outputs reporting the same model name ("twins") cannot be told apart by
name -- eww would resolve it to the first match -- so those fall back to their
index, which is the pre-existing behaviour and still lands on the right screen.

Usage:
  monitors.py | gdk_monitor.py              # "index<TAB>connector<TAB>selector"
  gdk_monitor.py < monitors.json

The input must be the `monitors.py` JSON (or anything else with a per-monitor
origin): the selector is resolved by geometry, so x/y are required. Note that
`workarea.py --per-monitor`'s layout does NOT carry them -- its monitor entries
only have width/height, the origin lives under "panel" -- so pass monitors.py.
"""

import json
import sys

Gdk = None


def _gdk():
    """The Gdk.Display eww resolves monitor names against, or None."""
    global Gdk
    if Gdk is not None:
        return Gdk
    try:
        import gi

        # eww 0.5 is a GTK3 app, so GTK3's GDK is the authority on both the
        # model names and the logical geometry it compares them against.
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk as _Gdk

        Gdk = _Gdk
    except Exception:
        return None
    return Gdk


def gdk_monitors():
    """[(model, x, y, w, h)] in GDK's own index order; [] when unavailable."""
    gdk = _gdk()
    if gdk is None:
        return []
    try:
        display = gdk.Display.get_default()
        if display is None:
            return []
        out = []
        for i in range(display.get_n_monitors()):
            mon = display.get_monitor(i)
            if mon is None:
                continue
            g = mon.get_geometry()
            out.append((mon.get_model(), g.x, g.y, g.width, g.height))
        return out
    except Exception:
        return []


def selectors(monitors):
    """{enumeration index: eww selector} for the `monitors.py` entries.

    The index itself is the fallback, so a missing python3-gi, an X11 session
    or a layout GDK has not caught up with yet degrades to exactly what the
    callers did before instead of failing.
    """
    gdk = gdk_monitors()
    twins = {}
    for model, _x, _y, _w, _h in gdk:
        twins[model] = twins.get(model, 0) + 1

    out = {}
    for m in monitors or []:
        try:
            idx = int(m["index"])
            want = (int(m["x"]), int(m["y"]), int(m["width"]), int(m["height"]))
        except Exception:
            continue
        found = None
        for model, gx, gy, gw, gh in gdk:
            if (gx, gy, gw, gh) != want:
                continue
            # Only take the model when it addresses this one output.
            if model and twins.get(model, 0) == 1:
                found = str(model)
            break
        out[idx] = found if found else str(idx)
    return out


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        raw = open(src).read() if src else sys.stdin.read()
    except OSError as exc:
        sys.stderr.write("ERROR: gdk_monitor.py: %s\n" % exc)
        return 1
    raw = raw.strip()
    if not raw:
        return 0
    try:
        data = json.loads(raw)
    except ValueError:
        sys.stderr.write("ERROR: gdk_monitor.py: input is not monitor JSON\n")
        return 1
    sel = selectors(data.get("monitors"))
    for m in data.get("monitors") or []:
        try:
            idx = int(m["index"])
        except Exception:
            continue
        print("%s\t%s\t%s" % (idx, m.get("name", ""), sel.get(idx, str(idx))))
    return 0


if __name__ == "__main__":
    sys.exit(main())