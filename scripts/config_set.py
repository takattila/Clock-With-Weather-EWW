#!/usr/bin/env python3
"""Line-aware in-place YAML writer for config.yaml.

The central config file is heavily commented. A plain YAML dump would destroy
all of it, so this script performs a *line-aware* edit: it only touches the
target key line(s) (or, for per_monitor, the small machine-managed sub-tree)
and leaves every other line byte-identical.

It is used by the Move / Resize context menu actions (scripts/move.py):
the config watcher (scripts/watch.py) then detects the change and reloads /
relays out the widget.

Usage:
  ./config_set.py --widget clock --key position_x --value 120
  ./config_set.py --widget clock --key scale --value 0.8
  ./config_set.py --widget clock --monitor 0 --key position_x --value 120
  ./config_set.py --widget panel --monitor 1 --key scale --value 0.7

--widget is `clock` (weather window) or `panel`. Without --monitor the global
key is written; with --monitor the value is written into per_monitor[N].
"""

import argparse
import os
import re
import sys

import yaml

CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")

KEY_RE = re.compile(r"^(\s*)([^:#]+?)\s*:(.*)$")


def read_lines():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return f.readlines()


def find_key(lines, target):
    """Return (line_index, key_value) for the mapping key `target` (a path list).

    Tracks the current nesting with an indent stack; comments and blank lines
    do not affect it. `target` components are compared as strings.
    """
    target = [str(t) for t in target]
    stack = []  # (indent, key)
    for i, raw in enumerate(lines):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = KEY_RE.match(line)
        if not m:
            continue
        key = m.group(2).strip()
        value = m.group(3).strip()
        indent = len(m.group(1))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = [k for _, k in stack] + [key]
        stack.append((indent, key))
        if path == target:
            return i, value
    return None


def block_region(lines, start, parent_indent):
    """Return (child_start, child_end) indexes of the block's content lines.

    `start` is the line right after the block key line. Lines with an indent
    greater than `parent_indent` (plus any nested lines) are the block's
    children; comments/blanks AFTER the last child belong to the NEXT sibling
    and are left untouched by the caller.
    """
    j = start
    last_content = start - 1
    while j < len(lines):
        l = lines[j]
        if not l.strip() or l.lstrip().startswith("#"):
            j += 1
            continue
        if len(l) - len(l.lstrip()) <= parent_indent:
            break
        last_content = j
        j += 1
    return start, last_content + 1


def block_lines(parent_indent, data):
    """Render the (monitor-index -> {key: value}) dict as a block-style body."""
    out = []
    child_indent = parent_indent + 2
    for monitor in sorted(data, key=lambda k: str(k)):
        out.append("%s%s:" % (" " * child_indent, monitor))
        for key, value in data[monitor].items():
            out.append("%s%s: %s" % (" " * (child_indent + 2), key, value))
    return ["%s\n" % l for l in out]


def replace_inline_value(lines, i, value):
    """Replace the value part of the key line at `i`, keeping any trailing
    comment on the same line."""
    line = lines[i].rstrip("\n")
    m = KEY_RE.match(line)
    if not m:
        return
    rest = m.group(3)
    comment = ""
    if "#" in rest:
        ci = rest.index("#")
        comment = rest[ci:]
    lines[i] = "%s%s: %s%s\n" % (m.group(1), m.group(2).strip(), value,
                                 (" " + comment.strip()) if comment else "")


def insert_child(lines, parent_target, key, value):
    """Insert a new `key: value` child at the end of the `parent_target` block."""
    found = find_key(lines, parent_target)
    if found is None:
        sys.exit("ERROR: parent block not found: %s" % ".".join(map(str, parent_target)))
    pi, _ = found
    pindent = len(lines[pi]) - len(lines[pi].lstrip())
    child_indent = pindent + 2
    start, end = block_region(lines, pi + 1, pindent)
    lines.insert(end, "%s%s: %s\n" % (" " * child_indent, key, value))


def set_global(lines, section_target, key, value):
    target = section_target + [key]
    found = find_key(lines, target)
    if found is not None:
        replace_inline_value(lines, found[0], value)
    else:
        insert_child(lines, section_target, key, value)


def current_per_monitor(section_target):
    """Return the parsed per_monitor dict for the section (from the real YAML)."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    node = cfg
    for part in section_target:
        node = (node or {}).get(part, {}) if isinstance(node, dict) else {}
    if not isinstance(node, dict):
        node = {}
    return node.get("per_monitor") or {}


def set_per_monitor(lines, section_target, monitor, key, value):
    target = section_target + ["per_monitor"]
    found = find_key(lines, target)
    if found is None:
        sys.exit("ERROR: per_monitor block not found: %s" % ".".join(map(str, section_target)))
    pi, inline = found
    pindent = len(lines[pi]) - len(lines[pi].lstrip())

    current = current_per_monitor(section_target)
    mon = current.get(monitor)
    if not isinstance(mon, dict):
        mon = {}
    mon[key] = value
    current[monitor] = mon

    start, end = block_region(lines, pi + 1, pindent)
    lines[pi] = "%sper_monitor:\n" % (" " * pindent)
    lines[start:end] = block_lines(pindent, current)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--widget", required=True, choices=["clock", "panel"])
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--monitor", type=int, default=None)
    args = ap.parse_args()

    section = ["weather", "window"] if args.widget == "clock" else ["panel", "window"]
    if args.key not in ("position_x", "position_y", "scale"):
        sys.exit("ERROR: unsupported key: %s" % args.key)

    lines = read_lines()
    if args.monitor is None:
        set_global(lines, section, args.key, args.value)
    else:
        set_per_monitor(lines, section, args.monitor, args.key, args.value)

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("wrote %s.%s%s=%s" % (
        ".".join(section),
        ("per_monitor[%d]." % args.monitor) if args.monitor is not None else "",
        args.key, args.value,
    ))


if __name__ == "__main__":
    main()