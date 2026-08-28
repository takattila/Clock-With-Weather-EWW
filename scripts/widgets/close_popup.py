#!/usr/bin/env python3
"""Close the popup windows (context menu + hover submenus + dismiss layers).

The `dismiss_overlay_<N>` windows are transparent, full-monitor layers — ONE
PER CONNECTED MONITOR, opened by ctx.py with ids recorded in the session file
— that sit on the compositor's OVERLAY level, above every normal window.
Clicking anywhere on any screen hits such a layer and closes every popup;
while they are mapped they also block input meant for anything beneath them
(browser, terminals, ...), so closing them must be RELIABLE.

The window list comes from generated/input_session.json (written by ctx.py);
the plain `dismiss_overlay` name is always included as a legacy/fallback so
older sessions are cleaned up too.

Closing is VERIFIED via `eww active-windows` (compositor-independent, works
on Wayland too): right after a quick-settings selection or an About/GitHub
open the eww daemon can be busy regenerating the theme and silently drop an
IPC close (measured: one of two same-name overlay instances survived its
close). The script retries until none of the popup names is listed anymore,
and on X11 additionally force-unmaps any leftover window.

The GTK About window watches the session file and quits once it is gone.

Usage:
  ./close_popup.py
"""

import json
import os
import re
import subprocess
import sys
import time

# scripts/widgets/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

import session  # noqa: E402

TRACKED = ("ctx_menu", "submenu", "dismiss_overlay")


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
    keys = ("DISPLAY", "XAUTHORITY")
    return {k: v for k, v in os.environ.items() if k in keys}


def open_popup_names():
    """Names of popup windows still open, from `eww active-windows`.

    Output lines look like `dismiss_overlay_1: dismiss_overlay`; this works
    identically on X11 and Wayland, unlike xdotool-based queries.
    """
    act = active_tracked()
    if act is None:
        return None
    return [name for _, name in act]


def active_tracked():
    """(instance_id, template_name) of tracked windows still open.

    Parses `eww active-windows` lines (`<id>: <template>`); returns None
    when the query itself fails (unknown state -> caller keeps retrying).
    """
    try:
        out = subprocess.run(
            ["eww", "--config", EWW_CONFIG_DIR, "active-windows"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return None
    pairs = []
    for line in out.splitlines():
        if ":" not in line:
            continue
        wid, _, name = line.partition(":")
        name = name.strip()
        if name in TRACKED:
            pairs.append((wid.strip(), name))
    return pairs


def destroy_leftovers(ids):
    """X11 last resort: unmap popup windows that survived every attempt."""
    env = {k: v for k, v in os.environ.items() if k in ("DISPLAY", "XAUTHORITY")}
    for win in ids:
        try:
            subprocess.run(
                ["xdotool", "windowunmap", win],
                check=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=3, env=env,
            )
        except Exception:
            pass


def x11_stray_ids(names):
    """X11 window ids whose WM_NAME matches any of the given eww names."""
    if not os.environ.get("DISPLAY"):
        return []
    env = _xenv()
    pattern = "^Eww - (%s)$" % "|".join(re.escape(n) for n in names)
    try:
        out = subprocess.run(
            ["xdotool", "search", "--name", pattern],
            capture_output=True, text=True, timeout=3, env=env,
        ).stdout
        return [w for w in out.split() if w]
    except Exception:
        return []


def close_popups_verified(session_data=None):
    """Close every popup and VERIFY that none is left open.

    A single `eww close` can be dropped when the daemon is busy (measured:
    of two same-name overlay instances, one survived its close right after a
    theme selection; same for the legacy About overlay). The loop re-checks
    through `eww active-windows` until every tracked name is gone. On X11 a
    final janitor pass force-unmaps anything that still refuses to die - an
    invisible overlay left on top would block all input on its monitor.
    """
    names = windows_to_close(session_data)

    for _ in range(10):
        close_all(names)
        act = active_tracked()
        if act is None:
            # Unknown state (query failed) -> keep retrying.
            time.sleep(0.25)
            continue
        if not act:
            break
        # ORPHAN RECOVERY: close by INSTANCE id too. The per-monitor overlay
        # ids normally come from the session file, but that file is already
        # gone when a Move/Resize session was ended without popup cleanup
        # (older bug) or crashed -- `active-windows` still knows them.
        close_all([wid for wid, _ in act])
        time.sleep(0.25)

    # X11 janitor: unmap strays (Wayland has no equivalent; the retries above
    # are the safety net there).
    strays = x11_stray_ids([n for n in names if n != "submenu"])
    if strays:
        env = {k: v for k, v in os.environ.items() if k in ("DISPLAY", "XAUTHORITY")}
        for win in strays:
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
    # Hide any open picker pane. sub_show / sub_yuck are plain globals and
    # nothing else resets them, so without this the LAST hovered picker (e.g.
    # the AM/PM one) would reappear in the freshly opened menu on the next
    # right-click.
    try:
        subprocess.run(
            ["eww", "--config", EWW_CONFIG_DIR, "update", "sub_show=false"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        pass
    # Deactivate the keyboard daemon session (ESC / click-outside closed the
    # popups), so the daemon goes back to idle.
    session.clear_session()


if __name__ == "__main__":
    main()
