#!/usr/bin/env python3
"""Machine-local YAML writer: edits only git-ignored config.local.yaml.

config.local.yaml holds machine-specific overrides on top of the committed
config.yaml; every reader sees them deep-merged (scripts/core/config_io.py,
local keys win down to the leaves). This script writes ONLY into the local
file, so moving / resizing the widgets never produces changes in git.

It is used by the Move / Resize context menu actions (scripts/move/) and by
the setup wizard (scripts/bin/setup.sh); the config watcher (watch.py) then
detects the change and reloads / relays out the widget.

Usage:
  ./config_set.py --widget clock --monitor 0 --key position_x --value 120
  ./config_set.py --widget clock --monitor 0 --key scale --value 0.8
  ./config_set.py --widget panel --monitor 1 --key scale --value 0.7
  ./config_set.py --widget panel --monitor 1 --key position_x --value 30
  ./config_set.py --widget panel --key gap_right --value 0

--widget is `clock` (weather window) or `panel`. The position_x / position_y /
scale keys are written into per_monitor[N] ONLY and REQUIRE --monitor (there
are no global position/scale keys). For the panel they are per-monitor
OFFSETS added to the global panel.gap baseline (scripts/workarea.py); the gap
keys (gap_top / gap_right / gap_bottom / gap_left) remain global and are
written into panel.gap.

Keys not touched by this run are preserved: the whole previous local tree is
loaded, updated and dumped back. Values are coerced (positions and gaps to
int, scale to float), matching what the readers expect.
"""

import argparse
import os
import sys

import yaml

# scripts/core/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL_CONFIG_FILE = os.path.join(CONFIG_DIR, "config.local.yaml")

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
    """Positions and gap sizes become int, scale becomes float."""
    if key == "scale":
        try:
            return float(raw)
        except (TypeError, ValueError):
            sys.exit("ERROR: %s must be a number, got: %s" % (key, raw))
    try:
        return int(str(raw).strip().rstrip(","))
    except (TypeError, ValueError):
        sys.exit("ERROR: %s must be an integer, got: %s" % (key, raw))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", required=True, choices=["clock", "panel"])
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--monitor", type=int, default=None)
    args = ap.parse_args()

    if args.key.startswith("gap_") and args.key[4:] in GAP_SIDES:
        if args.widget != "panel":
            sys.exit("ERROR: gap keys apply to the panel only")
        if args.monitor is not None:
            sys.exit("ERROR: panel gaps are global (no --monitor)")
        section_path = ["panel", "gap"]
        key_written = args.key[4:]
        path = section_path + [key_written]
    elif args.key in ("position_x", "position_y", "scale"):
        if args.monitor is None:
            sys.exit("ERROR: %s is stored per monitor; --monitor is required" % args.key)
        section_path = (
            ["weather", "window"] if args.widget == "clock" else ["panel", "window"]
        )
        key_written = args.key
        path = section_path + ["per_monitor", args.monitor, key_written]
    else:
        sys.exit("ERROR: unsupported key: %s" % args.key)

    data = load_local()
    set_path(data, path, coerce_value(key_written, args.value))
    with open(LOCAL_CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    print("wrote %s.%s%s=%s -> %s" % (
        ".".join(section_path),
        ("per_monitor[%d]." % args.monitor) if args.monitor is not None else "",
        key_written, args.value, os.path.basename(LOCAL_CONFIG_FILE),
    ))


if __name__ == "__main__":
    main()
