#!/usr/bin/env python3
"""Live-measure the real ctx-menu ROW GEOMETRY and cache it for submenu.py.

submenu.py positions the hover picker pane with a model of the menu column
(.ctx-btn / .ctx-sep pitches). Those natural sizes come from the label fonts
and GTK/Pango metrics of the RUNNING compositor, which differ per system
(DPI, fontconfig, GTK theme, Qt/GNOME label height floor...). Guessing them
(e.g. a uniform ROW_H, or pinned min-heights) drifts the pane away from the
parent row. So instead: after ctx.py opens the context menu on X11, this
script captures the LIVE window surface, measures where the row labels
really are, and writes generated/menu_rows.json with the pixel top of every
collapsed column row. submenu.py then lines the pane up with those real
offsets. On failure (non-X11, capture tools missing, or the layout is not a
uniform pitch) nothing is written and submenu.py falls back to its constants.

Usage:
  ./measure_menu.py --widget clock|panel
"""

import os
import shutil
import subprocess
import sys
import tempfile

CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROWS = 12        # collapsed ctx-menu column rows (both widgets stack 12)
PAD = 7           # ctx_menu top padding (+border) == submenu.MENU_PAD
MARGIN = 2        # .ctx-btn margin (inset of the first button) == eww.scss
MAX_ROWS = 18     # sanity: never trust a capture with more B bands than rows
TOL = 4           # px tolerance for the uniform-pitch consistency check

# B-row indices in the collapsed column, per widget (== submenu.ROW_SEQUENCES).
B_ROWS = {
    "clock": [0, 1, 2, 4, 5, 7, 8, 10, 11],
    "panel": [0, 1, 2, 4, 6, 7, 8, 10, 11],
}


def run(cmd):
    try:
        return subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=20,
        )
    except Exception:
        return None


def find_ctx_menu_winid():
    try:
        import time
    except Exception:
        return None
    for attempt in range(10):
        out = run(["xwininfo", "-root", "-children"])
        if not out or out.returncode != 0:
            time.sleep(0.15)
            continue
        for line in out.stdout.splitlines():
            if 'Eww - ctx_menu' in line:
                return line.split()[0]
        time.sleep(0.15)
    return None


def capture_png(winid, png_path):
    tmp = png_path + ".xwd"
    if not shutil.which("ffmpeg"):
        return False
    xwd = run(["xwd", "-id", winid, "-silent", "-out", tmp])
    if not xwd or xwd.returncode != 0:
        return False
    ok = run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, png_path])
    try:
        os.remove(tmp)
    except OSError:
        pass
    return ok is not None and ok.returncode == 0


def measure(widget):
    try:
        from PIL import Image
    except Exception:
        return None
    winid = find_ctx_menu_winid()
    if not winid:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        png = os.path.join(tmp, "menu.png")
        if not capture_png(winid, png):
            return None
        try:
            im = Image.open(png).convert("RGB")
        except Exception:
            return None
        w, h = im.size
        if w < 150 or h < 100:
            return None

        # Column x-range: the dark .ctx-menu background rectangle
        # (rgba(bg-color 0.95) over whatever's behind is a warm near-black).
        cols = []
        for x in range(0, w, 2):
            for y in range(0, h, 2):
                r, g, b = im.getpixel((x, y))
                if r > 18 and 12 < g < 30 and 14 < b < 36 and (r - g) > 4:
                    cols.append(x)
        if len(cols) < w * 0.05:
            return None
        cx0, cx1 = min(cols), max(cols)
        if cx1 - cx0 < 120:
            return None

        # Label bands: bright text inside the column. Text labels run tall
        # (>= 5px); the dashed separators and border hints render as tiny
        # flickers (<=3px) and are skipped.
        bands = []
        inband = False
        start = 0
        for y in range(h):
            bright = 0
            for x in range(max(0, cx0 - 4), min(w, cx1 + 4)):
                r, g, b = im.getpixel((x, y))
                if r + g + b > 110:
                    bright += 1
            if bright > 2 and not inband:
                inband, start = True, y
            elif bright <= 2 and inband:
                inband = False
                if y - start >= 5:
                    bands.append((start, y - 1))
        if inband and h - start >= 5:
            bands.append((start, h - 1))
        if len(bands) != len(B_ROWS[widget]):
            return None

        starts = [b0 for (b0, _) in bands]
        diffs = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
        if not diffs:
            return None

        # Uniform pitch: every gap is ~pitch (adjacent buttons) or ~2*pitch
        # (one separator between two buttons); anything else bails out.
        p0 = min(diffs)
        ones = [d for d in diffs if abs(d - p0) <= TOL]
        if len(ones) < 4:
            return None
        pitch = round(sum(ones) / float(len(ones)))
        if not (18 <= pitch <= 90):
            return None
        twos = [d for d in diffs if abs(d - 2 * pitch) <= TOL]
        if len(ones) + len(twos) != len(diffs):
            return None

        # First row top = menu pad + button margin; leader = pixels from the
        # button top to the top of its label (padding + ascender gap).
        tops0 = PAD + MARGIN
        leader = starts[0] - tops0
        if not (4 <= leader <= 40):
            return None
        tops = [int(tops0 + i * pitch) for i in range(ROWS)]

        # Cross-check every measured label band against the model row top.
        for bi, s in enumerate(starts):
            row = B_ROWS[widget][bi]
            expected = tops[row] + leader
            if abs(expected - s) > TOL + 1:
                return None
        bottom = tops[-1] + pitch
        if bottom > h + TOL:
            return None

        return {"tops": tops, "pitch": pitch, "pad": PAD}


def main():
    args = sys.argv[1:]
    widget = "clock"
    if "--widget" in args:
        widget = args[args.index("--widget") + 1]
    widget = widget if widget in B_ROWS else "clock"
    data = measure(widget)
    out = os.path.join(CONFIG_DIR, "generated", "menu_rows.json")
    if not data:
        # No live geometry for THIS session (non-X11, nop capture tools or a
        # non-uniform layout): drop any stale file so submenu.py falls back to
        # its model instead of mis-anchoring with a previous run's numbers.
        try:
            os.remove(out)
        except OSError:
            pass
        sys.exit(0)
    try:
        import json
        with open(out, "w") as fh:
            json.dump(data, fh)
    except Exception:
        pass


if __name__ == "__main__":
    main()