#!/usr/bin/env python3
"""
Generate eww theme files (eww.theme.scss + eww.theme.json) from config.yaml
and the corresponding YAML appearance theme (themes/appearance/<name>/appearance.yaml).

Usage: ./theme.py [config_dir]
"""

import json
import os
import sys

import yaml


def load_config(config_dir):
    with open(os.path.join(config_dir, "config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_appearance(appearance_dir):
    with open(os.path.join(appearance_dir, "appearance.yaml"), "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    a = data.get("appearance", {})
    font = a.get("font", {}) or {}
    background = a.get("background", {}) or {}
    return {
        "theme": a.get("theme", "light"),
        "icon_set": (a.get("icon", {}) or {}).get("set", "dovora"),
        "font_face": font.get("face", "Noto Sans"),
        "color_light": (font.get("color", {}) or {}).get("light", "#ffffff"),
        "color_dark": (font.get("color", {}) or {}).get("dark", "#9e9e9e"),
        "bg_color": background.get("color", "#000000"),
        "bg_alpha": background.get("transparency", 0.0),
    }


def main():
    config_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())

    config = load_config(config_dir)
    appearance = config.get("appearance", "light")

    themes_dir = os.path.normpath(
        os.path.join(config_dir, "themes", "appearance", appearance)
    )
    if not os.path.isdir(themes_dir):
        print(
            "ERROR: appearance theme directory not found: %s" % themes_dir,
            file=sys.stderr,
        )
        sys.exit(1)

    data = parse_appearance(themes_dir)

    system = config.get("system", {}) or {}
    data["bg_radius"] = int(system.get("corner_radius", 20))

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
        f.write("$bg-radius: %spx;\n" % data["bg_radius"])

    print("-> appearance --------- : %s" % appearance)
    print("-> theme --------------- : %s" % data["theme"])
    print("-> icon set ------------ : %s" % data["icon_set"])
    print("-> font face ----------- : %s" % data["font_face"])
    print("-> font color light ---- : %s" % data["color_light"])
    print("-> font color dark ----- : %s" % data["color_dark"])
    print("-> background color ----- : %s" % data["bg_color"])
    print("-> background opacity --- : %s" % data["bg_alpha"])
    print("-> bg corner radius ----- : %spx" % data["bg_radius"])


if __name__ == "__main__":
    main()
