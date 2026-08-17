#!/usr/bin/env python3
"""Regenerate generated/move_rect.svg for a given width/height.

The SVG's viewBox is set to the widget's pixel size so that
Pixbuf::from_file_at_size(w, h) (which FITS, not stretches, preserving the
aspect ratio) renders the rectangle at exactly w x h. A fixed 100x100 square
SVG would always render as a square (librsvg keeps the aspect ratio).
"""

import argparse
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(SCRIPT_DIR, "..", "generated", "move_rect.svg")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    args = ap.parse_args()

    w = max(2, int(args.width))
    h = max(2, int(args.height))
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">\n'
        '  <rect x="2" y="2" width="%d" height="%d" fill="rgba(255,255,255,0.08)" '
        'stroke="rgba(255,255,255,0.95)" stroke-width="2" stroke-dasharray="10 6" rx="4" ry="4"/>\n'
        '</svg>\n'
    ) % (w, h, w, h, w - 4, h - 4)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        f.write(svg)
    print(OUT_PATH)


if __name__ == "__main__":
    main()
