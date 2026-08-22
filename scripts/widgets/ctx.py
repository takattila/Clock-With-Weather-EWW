#!/usr/bin/env python3
"""Open the context menu for a widget.

Computes the menu position (scripts/move/menu_pos.py: cursor on X11, widget
corner on Wayland), closes any previously open menu and opens ctx_menu at
that spot.

Usage:
  ./ctx.py --widget clock --monitor 0
  ./ctx.py --widget panel --monitor 1
"""

import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# scripts/widgets/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

import session


def run(cmd, capture=False):
    try:
        if capture:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ""
    except Exception:
        return ""


def main():
    if os.environ.get("EWW_CTX_BG") != "1":
        # eww kills widget commands whose runtime exceeds its timeout (default
        # 200ms) even when :timeout is set on the widget. ctx.py spawns several
        # subprocesses (menu_pos + eww calls) and can take ~300ms, so re-spawn
        # ourselves detached: the eww command returns immediately and the work
        # keeps running in the background.
        env = dict(os.environ, EWW_CTX_BG="1")
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__)] + sys.argv[1:],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
        return

    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", required=True, choices=["clock", "panel"])
    ap.add_argument("--monitor", type=int, default=0)
    args = ap.parse_args()

    out = run(
        ["python3", os.path.join(CONFIG_DIR, "scripts", "move", "menu_pos.py"),
         "--widget", args.widget, "--monitor", str(args.monitor)],
        capture=True,
    )
    try:
        pos = json.loads(out)
    except Exception:
        sys.exit("ERROR: menu_pos.py failed:\n%s" % out)

    # Open the transparent dismiss layer first (so the menu stacks above it),
    # then the context menu. Clicking anywhere outside the menu hits the layer
    # and closes the popups.
    run(["eww", "--config", EWW_CONFIG_DIR, "close", "dismiss_overlay"])
    run(["eww", "--config", EWW_CONFIG_DIR, "open",
         "--id", "dismiss_overlay",
         "--screen", str(pos["screen"]),
         "--arg", "screen=%d" % pos["screen"],
         "dismiss_overlay"])
    run(["eww", "--config", EWW_CONFIG_DIR, "close", "ctx_menu"])
    run(
        [
            "eww", "--config", EWW_CONFIG_DIR, "open",
            "--id", "ctx_menu",
            "--screen", str(pos["screen"]),
            "--arg", "widget=%s" % args.widget,
            "--arg", "monitor=%d" % args.monitor,
            "--arg", "pos_x=%d" % pos["x"],
            "--arg", "pos_y=%d" % pos["y"],
            "ctx_menu",
        ]
    )
    # The invisible keyboard daemon (scripts/input_daemon.py) reads the session
    # file: while it exists, ESC closes the popups.
    session.set_session({"mode": "ctx"})


if __name__ == "__main__":
    main()