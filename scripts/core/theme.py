#!/usr/bin/env python3
"""
Generate eww theme files (eww.theme.scss + eww.theme.json) from config.yaml
(plus the git-ignored config.local.yaml overrides, see config_io.py) and the
appearance definition.

The `appearance` field of config.yaml accepts two forms:
  1. a string -> a theme directory under assets/themes/appearance/<name>/appearance.yaml
  2. a map    -> a custom inline appearance definition (same structure as
                 assets/themes/appearance/<name>/appearance.yaml)

Usage: ./theme.py [config_dir]
"""

import json
import os
import shutil
import sys

import yaml

try:
    from PIL import Image
except ImportError:
    Image = None

from config_io import load_merged


def load_config(config_dir):
    return load_merged(config_dir)


def load_appearance(config_dir, appearance):
    """Return the appearance map from config.yaml.

    Accepts a theme name (string -> assets/themes/appearance/<name>/appearance.yaml)
    or a custom inline map (used directly).
    """
    if isinstance(appearance, dict):
        return appearance
    themes_dir = os.path.normpath(
        os.path.join(config_dir, "assets", "themes", "appearance", appearance)
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
    icon_color = icon.get("color", {}) or {}
    background = a.get("background", {}) or {}

    theme = a.get("theme", "light")

    return {
        "theme": theme,
        "icon_set": icon.get("set", "dovora"),
        "icon_alpha": icon_transparency.get(theme, 1.0),
        "icon_color": icon_color.get(theme),
        "font_face": font.get("face", "Noto Sans"),
        "color_light": font_color.get("light", "#ffffff"),
        "color_dark": font_color.get("dark", "#9e9e9e"),
        "color_light_alpha": font_transparency.get("light", 1.0),
        "color_dark_alpha": font_transparency.get("dark", 1.0),
        "bg_color": background.get("color", "#000000"),
        "bg_alpha": background.get("transparency", 0.0),
    }


def tint_icon(img, color):
    """Tint a monochrome icon: replace its RGB with `color`, keep the alpha."""
    img = img.convert("RGBA")
    alpha = img.split()[3]
    r, g, b = _parse_color(color)
    out = Image.new("RGBA", img.size, (r, g, b, 255))
    out.putalpha(alpha)
    return out


def _parse_color(value):
    value = str(value).lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def generate_icons(config_dir, data):
    """Recreate generated/icons/ from the source theme icon folders.

    When `icon.color` is set for the active theme the PNGs are tinted with
    Pillow (RGB replaced, alpha kept); otherwise they are copied unchanged, so
    themes without a color look exactly as before. Returns a human-readable
    summary string or None when everything was skipped.
    """
    icon_color = data.get("icon_color")
    theme = data["theme"]
    icon_set = data["icon_set"]
    gen_base = os.path.join(config_dir, "generated", "icons", theme)
    src_base = os.path.join(config_dir, "assets", "icons-src", theme)
    notes = []

    def generate(src_dir, dst_dir):
        if not os.path.isdir(src_dir):
            return
        shutil.rmtree(dst_dir, ignore_errors=True)
        os.makedirs(dst_dir, exist_ok=True)
        for name in sorted(os.listdir(src_dir)):
            if not name.endswith(".png"):
                continue
            src = os.path.join(src_dir, name)
            dst = os.path.join(dst_dir, name)
            try:
                if icon_color is None:
                    shutil.copy2(src, dst)
                elif Image is None:
                    notes.append(
                        "WARN: Pillow missing, copying %s untinted" % name
                    )
                    shutil.copy2(src, dst)
                else:
                    tint_icon(Image.open(src), icon_color).save(dst)
            except Exception as exc:
                notes.append("WARN: skipping %s (%s)" % (src, exc))

    generate(
        os.path.join(src_base, "weather", icon_set),
        os.path.join(gen_base, "weather", icon_set),
    )
    generate(
        os.path.join(src_base, "elements"),
        os.path.join(gen_base, "elements"),
    )
    return "\n".join(notes) or None


def main():
    config_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())

    config = load_config(config_dir)
    appearance = config.get("appearance", "light")

    data = parse_appearance(load_appearance(config_dir, appearance))

    system = config.get("system", {}) or {}
    data["bg_radius"] = int(system.get("corner_radius", 20))

    icon_notes = generate_icons(config_dir, data)

    # The generated theme files live next to eww.yuck in the eww config dir.
    eww_dir = os.path.join(config_dir, "eww")
    os.makedirs(eww_dir, exist_ok=True)

    with open(os.path.join(eww_dir, "eww.theme.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    with open(os.path.join(eww_dir, "eww.theme.scss"), "w", encoding="utf-8") as f:
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
    def print_key(label, value):
        print("-> %-18s : %s" % (label, value))

    print_key("appearance", appearance_label)
    print_key("theme", data["theme"])
    print_key("icon set", data["icon_set"])
    print_key("icon color", data["icon_color"] or "original (no tint)")
    print_key("icon transparency", data["icon_alpha"])
    print_key("font face", data["font_face"])
    print_key("font color light", data["color_light"])
    print_key("font color dark", data["color_dark"])
    print_key("font transparency", "light %s / dark %s" % (data["color_light_alpha"], data["color_dark_alpha"]))
    print_key("background color", data["bg_color"])
    print_key("background opacity", data["bg_alpha"])
    print_key("bg corner radius", "%spx" % data["bg_radius"])

    if icon_notes:
        print(icon_notes)


if __name__ == "__main__":
    main()
