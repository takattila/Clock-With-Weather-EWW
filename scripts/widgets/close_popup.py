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
    """Ordered, de-duplicated list of popup windows to close.

    The hover-submenu pane lives INSIDE the ctx_menu window (rendered from
    the `sub_show` / `sub_yuck` variables), so closing `ctx_menu` hides it;
    the variables are reset separately in main().
    """
    names = ["ctx_menu"]
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


def destroy_stray_windows():
    """X11: unmap leftover override-redirect popup windows.

    Re-opening the same eww window id quickly can leave the previous X window
    behind (measured leak on eww 0.6.0); such invisible strays keep eating
    pointer input. Unmapping them by name makes the desktop clickable again
    even when the daemon-side bookkeeping already lost track of them.
    """
    env = {k: v for k, v in os.environ.items()
           if k in ("DISPLAY", "XAUTHORITY")}
    try:
        out = subprocess.run(
            ["xdotool", "search", "--name", r"^Eww - (submenu|ctx_menu)$"],
            capture_output=True, text=True, timeout=3, env=env,
        ).stdout
    except Exception:
        return
    for win in out.split():
        try:
            subprocess.run(
                ["xdotool", "windowunmap", win],
                check=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=3,
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
    destroy_stray_windows()
    # Hide/reset the picker pane of the (already closed) ctx_menu window.
    subprocess.run(
        ["eww", "--config", EWW_CONFIG_DIR, "update",
         "sub_show=false", "sub_yuck="],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=5,
    )
    # Deactivate the keyboard daemon session (ESC / click-outside closed the
    # popups), so the daemon goes back to idle.
    session.clear_session()


if __name__ == "__main__":
    main()
