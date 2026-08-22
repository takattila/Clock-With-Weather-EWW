#!/usr/bin/env python3
"""Close the popup windows (context menu + hover submenus + dismiss layers).

The `dismiss_overlay_<N>` windows are transparent, full-monitor layers — ONE
PER CONNECTED MONITOR, opened by ctx.py with ids recorded in the session file
— that sit under the context menu / its hover submenus / the GTK About window.
Clicking anywhere on any screen hits such a layer and closes every popup.

The window list comes from generated/input_session.json (written by ctx.py);
the plain `dismiss_overlay` name is always included as a legacy/fallback so
older sessions are cleaned up too. Each close is attempted twice: right after
a theme selection the eww daemon can be busy regenerating the theme and drop
an IPC call.

The GTK About window watches the same session file and quits once it is gone.

Usage:
  ./close_popup.py
"""

import json
import os
import subprocess
import sys
import time

# scripts/widgets/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

import session


def read_session_data():
    try:
        with open(SESSION_FILE) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def windows_to_close(session_data=None):
    """Ordered, de-duplicated list of popup windows to close."""
    names = ["ctx_menu", "submenu"]
    if isinstance(session_data, dict):
        for idx in session_data.get("overlays") or []:
            try:
                names.append("dismiss_overlay_%d" % int(idx))
            except (TypeError, ValueError):
                continue
    names.append("dismiss_overlay")  # legacy single-monitor id / fallback

    seen, ordered = set(), []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def close_all(names):
    for window in names:
        try:
            subprocess.run(
                ["eww", "--config", EWW_CONFIG_DIR, "close", window],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def main():
    session_data = read_session_data()
    names = windows_to_close(session_data)
    close_all(names)
    # One retry: right after a quick-settings selection the daemon may still be
    # busy regenerating/reloading and can drop an IPC close.
    time.sleep(0.15)
    close_all(names)
    # Deactivate the keyboard daemon session (ESC / click-outside closed the
    # popups), so the daemon goes back to idle.
    session.clear_session()


if __name__ == "__main__":
    main()
