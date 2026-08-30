#!/usr/bin/env python3
"""Live-theme-preview worker for the theme editor (scripts/move/theme_panel.py).

Spawned DETACHED by the editor so the GTK loop stays responsive. Applies the
current (as-yet-unsaved) draft to the LIVE widget — colors, fonts, radius,
glow, panel and the re-tinted icon PNGs — WITHOUT writing config.local.yaml.
Only the editor's Save button makes the change permanent.

    --apply <appearance.json> <radius>
        Regenerate eww/eww.theme.json + eww/eww.theme.scss and the tinted
        icons from the given NORMALIZED appearance map (the same dict
        save_inline_override would persist), snapshot the previous theme
        files for undo, then `eww reload`.
    --restore
        Undo a preview: regenerate the theme from the REAL merged config
        (config.yaml + config.local.yaml, i.e. the theme.py normal pipeline)
        and `eww reload`, then clear the preview marker. Idempotent no-op
        when no preview is active.

The worker never touches config.local.yaml / the theme dirs, so the inotify
watcher (watch.py) is deliberately NOT triggered and cannot fight the preview
or cause a reload loop.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CR_DIR = os.path.dirname(SCRIPT_DIR)          # scripts/
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # repo (widget) root
EWW_DIR = os.path.join(CONFIG_DIR, "eww")     # the eww --config target
GEN_DIR = os.path.join(CONFIG_DIR, "generated")
PREVIEW_FILE = os.path.join(GEN_DIR, "preview.json")
sys.path.insert(0, os.path.join(CR_DIR, "core"))

import theme  # noqa: E402


def _eww_dir():
    return EWW_DIR


def reload_eww():
    """Run `eww reload` with retries (same logic as watch._reload_eww)."""
    attempts = 5
    delay = 0.75
    for attempt in range(1, attempts + 1):
        try:
            reload = subprocess.run(
                ["eww", "--config", _eww_dir(), "reload"],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            time.sleep(delay)
            continue
        if reload.returncode == 0:
            return True
        if attempt < attempts:
            time.sleep(delay)
    return False


def _snapshot():
    """Copy the current generated theme files aside for --restore.

    Returns a temp dir holding copies, or None. Icons are left in place and
    regenerated on restore (cheap when nothing changed / overwritten on the
    next --apply).
    """
    tmp = tempfile.mkdtemp(prefix="eww-prev-")
    placed = 0
    for name in ("eww.theme.json", "eww.theme.scss"):
        src = os.path.join(_eww_dir(), name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(tmp, name))
            placed += 1
    if placed == 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    return tmp


def apply_preview(appearance, radius):
    """Recompute the theme from the normalized appearance and reload."""
    valid = isinstance(appearance, dict) and isinstance(radius, (int, float))
    if not valid:
        print("preview: invalid appearance/radius")
        return 1

    snap = _snapshot()
    os.makedirs(GEN_DIR, exist_ok=True)

    data = theme.parse_appearance(appearance)
    data["bg_radius"] = int(radius)
    theme.generate_icons(CONFIG_DIR, data)
    theme.write_theme_files(CONFIG_DIR, data)

    marker = {"active": True, "snapshot": snap,
              "ts": time.time(), "radius": int(radius)}
    with open(PREVIEW_FILE, "w", encoding="utf-8") as fh:
        json.dump(marker, fh)

    reload_eww()
    print("preview applied")
    return 0


def restore():
    """Regenerate from the REAL config and reload; clear the preview marker."""
    if os.path.isfile(PREVIEW_FILE):
        try:
            with open(PREVIEW_FILE, "r", encoding="utf-8") as fh:
                marker = json.load(fh) or {}
            snap = marker.get("snapshot")
            if snap and os.path.isdir(snap):
                shutil.rmtree(snap, ignore_errors=True)
        except Exception:
            pass
        try:
            os.remove(PREVIEW_FILE)
        except OSError:
            pass

    gen = subprocess.run(
        [sys.executable, os.path.join(CONFIG_DIR, "scripts", "core", "theme.py"),
         CONFIG_DIR],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if gen.returncode != 0:
        print("preview restore failed:\n" + gen.stderr.strip())
        return 1
    reload_eww()
    print("preview restored")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", metavar="APPEARANCE_JSON", default=None,
                    help="path to a JSON file with the normalized appearance map")
    ap.add_argument("--radius", type=float, default=None)
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    if args.restore:
        sys.exit(restore())
    if args.apply:
        try:
            with open(args.apply, "r", encoding="utf-8") as fh:
                appearance = json.load(fh) or {}
        except Exception as exc:
            print("preview: cannot read %s (%s)" % (args.apply, exc))
            sys.exit(1)
        sys.exit(apply_preview(appearance, args.radius))
    ap.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
