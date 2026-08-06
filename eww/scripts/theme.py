#!/usr/bin/env python3
"""
Generate eww theme files (eww.theme.scss + eww.theme.json) from config.json
and the corresponding Conky appearance theme (../themes/appearance/<name>/appearance.lua).

Usage: ./theme.py [config_dir]
"""

import json
import os
import re
import sys


def load_config(config_dir):
    with open(os.path.join(config_dir, "config.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def parse_lua_value(content, key):
    match = re.search(
        r"^\s*" + re.escape(key) + r"\s*=\s*\"([^\"]+)\"",
        content,
        re.MULTILINE,
    )
    if match:
        return match.group(1)
    match = re.search(
        r"^\s*" + re.escape(key) + r"\s*=\s*([0-9.]+)",
        content,
        re.MULTILINE,
    )
    if match:
        return float(match.group(1))
    return None


def parse_appearance(appearance_dir):
    with open(os.path.join(appearance_dir, "appearance.lua"), "r", encoding="utf-8") as f:
        content = f.read()

    return {
        "theme": parse_lua_value(content, "theme") or "light",
        "icon_set": parse_lua_value(content, "set") or "dovora",
        "font_face": parse_lua_value(content, "face") or "Noto Sans",
        "color_light": parse_lua_value(content, "light") or "#ffffff",
        "color_dark": parse_lua_value(content, "dark") or "#9e9e9e",
        "bg_color": parse_lua_value(content, "color") or "#000000",
        "bg_alpha": parse_lua_value(content, "transparency") or 0.0,
    }


def main():
    config_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())

    config = load_config(config_dir)
    appearance = config.get("appearance", "light")

    themes_dir = os.path.normpath(
        os.path.join(config_dir, "..", "themes", "appearance", appearance)
    )
    if not os.path.isdir(themes_dir):
        print(
            "ERROR: appearance theme directory not found: %s" % themes_dir,
            file=sys.stderr,
        )
        sys.exit(1)

    data = parse_appearance(themes_dir)

    with open(os.path.join(config_dir, "eww.theme.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    with open(os.path.join(config_dir, "eww.theme.scss"), "w", encoding="utf-8") as f:
        f.write('$theme: "%s";\n' % data["theme"])
        f.write('$icon-set: "%s";\n' % data["icon_set"])
        f.write('$font-face: "%s";\n' % data["font_face"])
        f.write("$color-light: %s;\n" % data["color_light"])
        f.write("$color-dark: %s;\n" % data["color_dark"])
        f.write("$bg-color: %s;\n" % data["bg_color"])
        f.write("$bg-alpha: %s;\n" % data["bg_alpha"])

    print("-> appearance --------- : %s" % appearance)
    print("-> theme --------------- : %s" % data["theme"])
    print("-> icon set ------------ : %s" % data["icon_set"])
    print("-> font face ----------- : %s" % data["font_face"])
    print("-> font color light ---- : %s" % data["color_light"])
    print("-> font color dark ----- : %s" % data["color_dark"])
    print("-> background color ----- : %s" % data["bg_color"])
    print("-> background opacity --- : %s" % data["bg_alpha"])


if __name__ == "__main__":
    main()
