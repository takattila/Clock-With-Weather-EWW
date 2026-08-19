#!/usr/bin/env python3
"""Close the popup windows (context menu).

The `dismiss_overlay` window is a transparent, full-monitor layer that is
opened *under* the context menu / the GTK About window (scripts/about_win.py).
Clicking anywhere outside them hits this overlay, which closes ctx_menu,
dismiss_overlay and clears the session file (the GTK About window watches the
same file and quits).

Usage:
  ./close_popup.py
"""

import os
import subprocess
import sys

CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts"))

import session


def main():
    for window in ("ctx_menu", "dismiss_overlay"):
        try:
            subprocess.run(
                ["eww", "--config", CONFIG_DIR, "close", window],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    # Deactivate the keyboard daemon session (ESC / click-outside closed the
    # popups), so the daemon goes back to idle. The GTK About window polls this
    # file and quits once it is gone.
    session.clear_session()


if __name__ == "__main__":
    main()