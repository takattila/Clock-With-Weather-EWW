#!/usr/bin/env python3
"""Hide the hover submenu pane when the pointer enters a row WITHOUT a picker.

The picker pane (scripts/widgets/submenu.py) keeps sub_show=true until
something hides it, so the pane would stay open ("stuck") after the pointer
moves off a selectable row onto a plain action row. Every non-submenu row of
widget_ctx_menu (Move / Resize / Reset / Weather / Panel gap / Hard reset /
About) therefore carries this onhover handler, which only hides THE PANE --
the context menu itself stays open.

Usage:
  ./submenu_hide.py
"""

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# scripts/widgets/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target


def main():
    try:
        subprocess.run(
            ["eww", "--config", EWW_CONFIG_DIR, "update", "sub_show=false"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()