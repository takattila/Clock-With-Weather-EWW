#!/usr/bin/env python3
"""Close the popup windows (context menu + hover submenus + dismiss layers).

The `dismiss_overlay_<N>` windows are transparent, full-monitor layers — ONE
PER CONNECTED MONITOR, opened by ctx.py with ids recorded in the session file
— that sit under the context menu / its hover submenus / the GTK About window.
Clicking anywhere on any screen hits such a layer and closes every popup.

The window list comes from generated/input_session.json (written by ctx.py);
the plain `dismiss_overlay` name is always included as a legacy/fallback so
older sessions are cleaned up too.

Closing is VERIFIED: right after a quick-settings selection the eww daemon
can be busy regenerating the theme and silently drop an IPC close (measured:
one of two same-name overlay instances survived its close). On X11 we check
with xdotool whether any popup window is still mapped and retry — up to
~2.5 s — until the desktop is really clean; anything left over is unmapped.

The GTK About window watches the session file and quits once it is gone.

Usage:
  ./close_popup.py
"""

import json
import os
import re
import subprocess
import sys

# scripts/widgets/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

import session

XENV_KEYS = ("DISPLAY", "XAUTHORITY")


def read_session_data():
    try:
        with open(SESSION_FILE) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def windows_to_close(session_data=None):
    """Ordered, de-duplicated list of popup windows to close."""
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


def _xenv():
    return {k: v for k, v in os.environ.items() if k in XENV_KEYS}


def stray_popup_ids():
    """X11 window ids of still-mapped popup windows ([] on Wayland/error)."""
    if not os.environ.get("DISPLAY"):
        return []
    env = _xenv()
    try:
        out = subprocess.run(
            ["xdotool", "search", "--name",
             r"^Eww - (ctx_menu|dismiss_overlay)"],
            capture_output=True, text=True, timeout=3, env=env,
        ).stdout
        return [w for w in out.split() if w]
    except Exception:
        return []


def destroy_leftovers(ids):
    """Unmap popup X windows that survived every close attempt."""
    env = _xenv()
    for win in ids:
        try:
            subprocess.run(
                ["xdotool", "windowunmap", win],
                check=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=3, env=env,
            )
        except Exception:
            pass


def close_popups_verified(session_data=None):
    """Close every popup and VERIFY at the X level that none is left.

    A single `eww close` can be dropped when the daemon is busy (measured:
    of two same-name overlay instances, one survived its close right after a
    theme selection). Retries are driven by the actual X state, not hoped
    away; whatever survives the retries is force-unmapped.
    """
    names = windows_to_close(session_data)

    def clean():
        return not stray_popup_ids()

    if clean():
        # Nothing mapped: still send the closes (covers non-X edge cases and
        # makes sure freshly-mapped strays from this very moment are gone).
        close_all(names)
        return

    for _ in range(8):
        close_all(names)
        if clean():
            break
        import time
        time.sleep(0.25)

    leftover = stray_popup_ids()
    if leftover:
        # Unmap whatever refused to die: an invisible popup layer left on top
        # blocks every right-click on the widgets beneath it.
        env = _xenv()
        for win in leftover:
            try:
                subprocess.run(
                    ["xdotool", "windowunmap", win],
                    check=False, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=3, env=env,
                )
            except Exception:
                pass


def main():
    session_data = read_session_data()
    close_popups_verified(session_data)
    # Deactivate the keyboard daemon session (ESC / click-outside closed the
    # popups), so the daemon goes back to idle.
    session.clear_session()


if __name__ == "__main__":
    main()
