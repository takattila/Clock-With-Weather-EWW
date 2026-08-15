#!/usr/bin/env python3
"""
Generate eww theme files (eww.theme.scss + eww.theme.json) from config.yaml
and the appearance definition.

The `appearance` field of config.yaml accepts two forms:
  1. a string -> a theme directory under themes/appearance/<name>/appearance.yaml
  2. a map    -> a custom inline appearance definition (same structure as
                 themes/appearance/<name>/appearance.yaml)

Usage: ./theme.py [config_dir]
"""

import json
import os
import sys

import yaml


def load_config(config_dir):
    with open(os.path.join(config_dir, "config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_appearance(config_dir, appearance):
    """Return the appearance map from config.yaml.

    Accepts a theme name (string -> themes/appearance/<name>/appearance.yaml)
    or a custom inline map (used directly).
    """
    if isinstance(appearance, dict):
        return appearance
    themes_dir = os.path.normpath(
        os.path.join(config_dir, "themes", "appearance", appearance)
    )
    if not os.path.isdir(themes_dir):
        print(
            "ERROR: appearance theme directory not found: %s" % themes_dir,
            file=sys.stderr,
        )
        sys.exit(1)
    with open(os.path.join(themes_dir, "appearance.yaml"), "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("appearance", {})


def parse_appearance(a):
    font = a.get("font", {}) or {}
    font_color = font.get("color", {}) or {}
    font_transparency = font.get("transparency", {}) or {}
    icon = a.get("icon", {}) or {}
    icon_transparency = icon.get("transparency", {}) or {}
    background = a.get("background", {}) or {}

    theme = a.get("theme", "light")

    return {
        "theme": theme,
        "icon_set": icon.get("set", "dovora"),
        "icon_alpha": icon_transparency.get(theme, 1.0),
        "font_face": font.get("face", "Noto Sans"),
        "color_light": font_color.get("light", "#ffffff"),
        "color_dark": font_color.get("dark", "#9e9e9e"),
        "color_light_alpha": font_transparency.get("light", 1.0),
        "color_dark_alpha": font_transparency.get("dark", 1.0),
        "bg_color": background.get("color", "#000000"),
        "bg_alpha": background.get("transparency", 0.0),
    }


def main():
    config_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())

    config = load_config(config_dir)
    appearance = config.get("appearance", "light")

    data = parse_appearance(load_appearance(config_dir, appearance))

    system = config.get("system", {}) or {}
    data["bg_radius"] = int(system.get("corner_radius", 20))

    with open(os.path.join(config_dir, "eww.theme.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    with open(os.path.join(config_dir, "eww.theme.scss"), "w", encoding="utf-8") as f:
        f.write('$theme: "%s";\n' % data["theme"])
        f.write('$icon-set: "%s";\n' % data["icon_set"])
        f.write("$icon-alpha: %s;\n" % data["icon_alpha"])
        f.write('$font-face: "%s";\n' % data["font_face"])
        f.write("$color-light: %s;\n" % data["color_light"])
        f.write("$color-dark: %s;\n" % data["color_dark"])
        f.write("$color-light-alpha: %s;\n" % data["color_light_alpha"])
        f.write("$color-dark-alpha: %s;\n" % data["color_dark_alpha"])
        f.write("$bg-color: %s;\n" % data["bg_color"])
        f.write("$bg-alpha: %s;\n" % data["bg_alpha"])
        f.write("$bg-radius: %spx;\n" % data["bg_radius"])

    if isinstance(appearance, dict):
        appearance_label = "custom"
    else:
        appearance_label = appearance
    print("-> appearance --------- : %s" % appearance_label)
    print("-> theme --------------- : %s" % data["theme"])
    print("-> icon set ------------ : %s" % data["icon_set"])
    print("-> icon transparency --- : %s" % data["icon_alpha"])
    print("-> font face ----------- : %s" % data["font_face"])
    print("-> font color light ---- : %s" % data["color_light"])
    print("-> font color dark ----- : %s" % data["color_dark"])
    print("-> font transparency --- : light %s / dark %s" % (data["color_light_alpha"], data["color_dark_alpha"]))
    print("-> background color ----- : %s" % data["bg_color"])
    print("-> background opacity --- : %s" % data["bg_alpha"])
    print("-> bg corner radius ----- : %spx" % data["bg_radius"])


if __name__ == "__main__":
    main()
