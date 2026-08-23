#!/usr/bin/env python3
"""Machine-local YAML writer: edits only git-ignored config.local.yaml.

config.local.yaml holds machine-specific overrides on top of the committed
config.yaml; every reader sees them deep-merged (scripts/core/config_io.py,
local keys win down to the leaves). This script writes ONLY into the local
file, so moving / resizing / re-configuring the widgets never produces
changes in git.

It is used by the Move / Resize context menu actions (scripts/move/), by the
context-menu quick toggles (scripts/widgets/menu_toggle.py) and by the setup
wizard (scripts/bin/setup.sh); the config watcher (watch.py) then detects the
change and reloads / relays out the widget.

Usage:
  ./config_set.py --widget clock --monitor 0 --key position_x --value 120
  ./config_set.py --widget clock --monitor 0 --key scale --value 0.8
  ./config_set.py --widget panel --monitor 1 --key scale --value 0.7
  ./config_set.py --widget panel --monitor 1 --key position_x --value 30
  ./config_set.py --widget panel --key gap_right --value 0

--widget is `clock` (weather window) or `panel`; it is REQUIRED only for the
widget-scoped keys below. The position_x / position_y / scale / scale_x /
scale_y keys are written into per_monitor[N] ONLY and REQUIRE --monitor
(there are no global position/scale keys). scale_x / scale_y are the
independent width/height scales written by the Move/Resize Save (each axis
falls back to the shared `scale` when missing). For the panel they are
per-monitor OFFSETS added to the global panel.gap baseline
(scripts/workarea.py); the gap keys (gap_top / gap_right / gap_bottom /
gap_left) remain global and are written into panel.gap.

GLOBAL keys need neither --widget nor --monitor (passing --monitor is an
error):
  ./config_set.py --key hour_format --value 12      -> system.hour_format
  ./config_set.py --key appearance --value dark     -> appearance
  ./config_set.py --key units --value imperial      -> weather.units
  ./config_set.py --key panel_enabled --value false -> panel.enabled
  ./config_set.py --key panel_alignment --value left-> panel.window.alignment

Keys not touched by this run are preserved: the whole previous local tree is
loaded, updated and dumped back. Values are coerced (positions and gaps to
int, scale to float, panel_enabled to bool, the rest kept as strings),
matching what the readers expect.
"""

import argparse
import os
import sys

import yaml

# scripts/core/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL_CONFIG_FILE = os.path.join(CONFIG_DIR, "config.local.yaml")
APPEARANCE_THEMES_DIR = os.path.join(CONFIG_DIR, "assets", "themes", "appearance")

GAP_SIDES = ("top", "right", "bottom", "left")


def load_local():
    """Return the parsed config.local.yaml ({} when the file does not exist)."""
    try:
        with open(LOCAL_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as exc:
        sys.exit("ERROR: cannot parse %s (%s)" % (LOCAL_CONFIG_FILE, exc))
    if not isinstance(data, dict):
        sys.exit("ERROR: %s must contain a mapping" % LOCAL_CONFIG_FILE)
    return data


def set_path(data, path, value):
    """Create the intermediate mappings along `path` and set the leaf value."""
    node = data
    for part in path[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[path[-1]] = value


def coerce_value(key, raw):
    """Positions and gap sizes become int, scale float, panel bool, rest str."""
    if key in ("scale", "scale_x", "scale_y"):
        try:
            return float(raw)
        except (TypeError, ValueError):
            sys.exit("ERROR: %s must be a number, got: %s" % (key, raw))
    if key == "enabled":
        flag = str(raw).strip().lower()
        if flag in ("true", "false"):
            return flag == "true"
        sys.exit("ERROR: panel_enabled must be true or false, got: %s" % (raw,))
    if key in ("hour_format", "appearance", "units", "alignment"):
        return str(raw).strip()
    try:
        return int(str(raw).strip().rstrip(","))
    except (TypeError, ValueError):
        sys.exit("ERROR: %s must be an integer, got: %s" % (key, raw))


def reject_monitor(args):
    if args.monitor is not None:
        sys.exit("ERROR: %s is global; --monitor must not be used" % args.key)


def resolve_target(args):
    """Validate the change and locate its destination.

    Returns (path, label): `path` is the exact YAML tree location the value
    must be written to (including the per-monitor index for the widget keys),
    `label` is the human-readable dotted name used in the confirmation
    message. Exits with a readable error on any mismatch.
    """
    # --- global keys (quick toggles; no --widget / --monitor) ---------------
    if args.key == "hour_format":
        reject_monitor(args)
        if str(args.value) not in ("12", "24"):
            sys.exit("ERROR: hour_format must be 12 or 24, got: %s" % (args.value,))
        return ["system", "hour_format"], "system.hour_format"
    if args.key == "appearance":
        reject_monitor(args)
        theme_dir = os.path.join(APPEARANCE_THEMES_DIR, str(args.value).strip())
        if not os.path.isdir(theme_dir):
            sys.exit(
                "ERROR: unknown appearance theme: %s (no such directory under %s)"
                % (args.value, APPEARANCE_THEMES_DIR)
            )
        return ["appearance"], "appearance"
    if args.key == "units":
        reject_monitor(args)
        if str(args.value) not in ("metric", "imperial"):
            sys.exit("ERROR: units must be metric or imperial, got: %s" % (args.value,))
        return ["weather", "units"], "weather.units"
    if args.key == "panel_enabled":
        reject_monitor(args)
        return ["panel", "enabled"], "panel.enabled"
    if args.key == "panel_alignment":
        reject_monitor(args)
        if str(args.value) not in ("right", "left"):
            sys.exit("ERROR: panel_alignment must be right or left, got: %s" % (args.value,))
        return ["panel", "window", "alignment"], "panel.window.alignment"

    # --- widget-scoped keys --------------------------------------------------
    if args.widget is None:
        sys.exit("ERROR: --widget is required for key: %s" % args.key)

    if args.key.startswith("gap_") and args.key[4:] in GAP_SIDES:
        if args.widget != "panel":
            sys.exit("ERROR: gap keys apply to the panel only")
        if args.monitor is not None:
            sys.exit("ERROR: panel gaps are global (no --monitor)")
        return ["panel", "gap", args.key[4:]], "panel.gap.%s" % args.key[4:]

    if args.key in ("position_x", "position_y", "scale", "scale_x", "scale_y"):
        if args.monitor is None:
            sys.exit("ERROR: %s is stored per monitor; --monitor is required" % args.key)
        section = (
            "weather.window" if args.widget == "clock" else "panel.window"
        )
        path = [section.split(".")[0], section.split(".")[1], "per_monitor", args.monitor, args.key]
        return path, "%s.per_monitor[%d].%s" % (section, args.monitor, args.key)

    sys.exit("ERROR: unsupported key: %s" % args.key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", default=None, choices=["clock", "panel"])
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--monitor", type=int, default=None)
    args = ap.parse_args()

    path, label = resolve_target(args)
    leaf = path[-1]

    data = load_local()
    set_path(data, path, coerce_value(leaf, args.value))
    with open(LOCAL_CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    print("wrote %s=%s -> %s" % (
        label, args.value, os.path.basename(LOCAL_CONFIG_FILE),
    ))


if __name__ == "__main__":
    main()
