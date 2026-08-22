#!/usr/bin/env python3
"""Context-menu quick toggles: flip one setting in config.local.yaml.

Every right-click menu toggle button (AM/PM switch, Theme, Units, Panel
shown/hidden, Side right/left) lands here. The script reads the MERGED view
(config.yaml deep-merged with config.local.yaml, scripts/core/config_io.py),
computes the NEXT value for the requested key and delegates the actual write
to scripts/core/config_set.py -- so the single-writer rule stays intact and
the git-ignored local override layer does all the work. The running watcher
(watch.py) then regenerates / reloads / relays out automatically; only the
units toggle needs an extra step (see below).

Value transitions:
  hour_format      "24" <-> "12"
  appearance       next directory under assets/themes/appearance/
                   alphabetically (wrap-around); unknown or custom-map
                   current values start the cycle at the first theme
  units            metric <-> imperial; afterwards the weather payload is
                   refreshed IMMEDIATELY by re-running scripts/core/weather.py
                   with the same arguments as the defpoll (but the NEW units)
                   and pushing it into the eww variable -- otherwise the
                   change would only show up at the next 10-minute poll
  panel_enabled    true <-> false   (watcher relayout applies it)
  panel_alignment  right <-> left   (watcher relayout applies it)

Usage:
  ./menu_toggle.py --key hour_format
  ./menu_toggle.py --key appearance
  ./menu_toggle.py --key units
"""

import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# scripts/widgets/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
APPEARANCE_THEMES_DIR = os.path.join(CONFIG_DIR, "assets", "themes", "appearance")
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

from config_io import load_merged

KEYS = ("hour_format", "appearance", "units", "panel_enabled", "panel_alignment")


def run(cmd, capture=False):
    """Run a command; capture stdout when asked, never raise on failure."""
    try:
        if capture:
            res = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, text=True, timeout=25,
            )
            return (res.stdout or "").strip()
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, timeout=25,
        )
        return ""
    except Exception:
        return ""


def config_key(name):
    """Read a single resolved value through the config bridge."""
    return run(
        ["python3", os.path.join(CONFIG_DIR, "scripts", "core", "config.py"), "--key", name],
        capture=True,
    )


def write(key, value):
    """Persist the new value via the single local-config writer."""
    return run(
        [
            "python3", os.path.join(CONFIG_DIR, "scripts", "core", "config_set.py"),
            "--key", key, "--value", str(value),
        ],
        capture=True,
    )


def available_themes():
    """Sorted appearance-theme directory names ('light' as safe fallback)."""
    try:
        names = [
            n for n in sorted(os.listdir(APPEARANCE_THEMES_DIR))
            if os.path.isdir(os.path.join(APPEARANCE_THEMES_DIR, n))
        ]
    except OSError:
        names = []
    return names or ["light"]


def next_appearance(current):
    """The next theme alphabetically; unknown/custom-map starts the cycle."""
    themes = available_themes()
    if isinstance(current, dict) or str(current) not in themes:
        return themes[0]
    idx = themes.index(str(current))
    return themes[(idx + 1) % len(themes)]


def next_value(key, cfg):
    """Compute the flipped/cycled value of `key` from the merged config."""
    system = cfg.get("system") or {}
    weather = cfg.get("weather") or {}
    panel = cfg.get("panel") or {}

    if key == "hour_format":
        return "12" if str(system.get("hour_format", "24")) == "24" else "24"
    if key == "appearance":
        return next_appearance(cfg.get("appearance", "light"))
    if key == "units":
        return "metric" if str(weather.get("units") or "metric") == "imperial" else "imperial"
    if key == "panel_enabled":
        enabled = str(panel.get("enabled", True)).strip().lower() != "false"
        return "false" if enabled else "true"
    if key == "panel_alignment":
        alignment = str((panel.get("window") or {}).get("alignment", "right")).strip().lower()
        return "left" if alignment == "right" else "right"
    sys.exit("ERROR: unsupported toggle key: %s" % key)


def refresh_weather(units):
    """Re-fetch the weather with the NEW units and push it into eww now.

    The defpoll would apply the unit change at its next 10-minute tick; this
    makes the °C/°F switch instant. Best-effort: any failure only warns.
    """
    try:
        payload = run(
            [
                "python3", os.path.join(CONFIG_DIR, "scripts", "core", "weather.py"),
                config_key("api_key"), config_key("city"), config_key("lang"),
                units, config_key("api_url"),
            ],
            capture=True,
        )
        if not payload:
            raise RuntimeError("empty weather response")
        lines = payload.strip().splitlines()
        run([
            "eww", "--config", EWW_CONFIG_DIR,
            "update", "weather_info=%s" % lines[-1],
        ])
    except Exception as exc:
        print("WARN: instant weather refresh failed (%s); the widget picks the "
              "new units up at the next poll" % exc, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, choices=KEYS)
    args = ap.parse_args()

    cfg = load_merged(CONFIG_DIR)
    value = next_value(args.key, cfg)

    out = write(args.key, value)
    if out:
        print(out)

    if args.key == "units":
        refresh_weather(value)


if __name__ == "__main__":
    main()
