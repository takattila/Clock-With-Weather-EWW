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

import colorsys
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


def _text_shadow_value(shadow):
    """Build the GTK CSS text-shadow value from font.shadow (color + blur).

    Two layered shadows (tight + wide) give a neon glow. Returns "none"
    when color or blur is missing.
    """
    color = shadow.get("color")
    blur = shadow.get("blur")
    if not color or blur is None:
        return "none"
    r, g, b = _parse_color(color)
    try:
        blur = max(1, int(blur))
    except (TypeError, ValueError):
        blur = 6
    return "0 0 %dpx rgba(%d,%d,%d,0.85), 0 0 %dpx rgba(%d,%d,%d,0.45)" % (
        blur,
        r,
        g,
        b,
        blur * 2,
        r,
        g,
        b,
    )


def _luminance(rgb):
    """Perceptual luminance 0-255 of an (r, g, b) tuple."""
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _contrast_ink(bg_color, fallback):
    """Text ("ink") color with enough contrast against `bg_color`.

    The context menu, the submenu and the panel paint their background from
    the theme background colors — on light backgrounds the (usually white)
    font.color.light would become unreadable, so the ink flips to a dark
    gray. Dark backgrounds keep the classic light ink (fallback).
    """
    luminance = _luminance(_parse_color(bg_color))
    return fallback if luminance < 140 else "#2e3436"


def _bg_for_text(bg_color, text_color):
    """Background that keeps `text_color` readable.

    Light text on a light background (or dark on dark) would vanish, so the
    background flips to a contrasting, hue-preserving tone (dark slate for
    a bluish light background, dark plum for a pinkish one, ...). Backgrounds
    with enough luminance distance are returned unchanged.
    """
    bg = _parse_color(bg_color)
    lum_bg = _luminance(bg)
    lum_tx = _luminance(_parse_color(text_color))
    if abs(lum_bg - lum_tx) >= 90:
        return bg_color
    hue, light, sat = colorsys.rgb_to_hls(
        bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0
    )
    light = 0.10 if lum_tx >= 140 else 0.92
    r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def parse_appearance(a):
    font = a.get("font", {}) or {}
    font_color = font.get("color", {}) or {}
    font_transparency = font.get("transparency", {}) or {}
    font_shadow = font.get("shadow", {}) or {}
    icon = a.get("icon", {}) or {}
    icon_transparency = icon.get("transparency", {}) or {}
    icon_color = icon.get("color", {}) or {}
    background = a.get("background", {}) or {}
    chart = a.get("chart", {}) or {}
    chart_colors = chart.get("colors", {}) or {}
    panel = a.get("panel", {}) or {}
    panel_background = panel.get("background", {}) or {}

    theme = a.get("theme", "light")

    color_light = font_color.get("light", "#ffffff")
    bg_color = background.get("color", "#000000")
    bg_alpha = background.get("transparency", 0.0)
    # Panel background: falls back to the widget background, so themes
    # without a panel section keep the shared background.
    panel_bg_color = panel_background.get("color", bg_color)
    panel_bg_alpha = panel_background.get("transparency", bg_alpha)

    # Light widget elements on a light painted background (or dark on dark)
    # would vanish: flip painted backgrounds to a contrasting, hue-preserving
    # tone. Only where they are actually painted (alpha > 0) — fully
    # transparent backgrounds keep their declared color for the context menu.
    if bg_alpha > 0:
        bg_color = _bg_for_text(bg_color, color_light)
    if panel_bg_alpha > 0:
        panel_bg_color = _bg_for_text(panel_bg_color, color_light)

    return {
        "theme": theme,
        "icon_set": icon.get("set", "dovora"),
        "icon_alpha": icon_transparency.get(theme, 1.0),
        "icon_color": icon_color.get(theme),
        "font_face": font.get("face", "Noto Sans"),
        "color_light": color_light,
        "color_dark": font_color.get("dark", "#9e9e9e"),
        "color_light_alpha": font_transparency.get("light", 1.0),
        "color_dark_alpha": font_transparency.get("dark", 1.0),
        "bg_color": bg_color,
        "bg_alpha": bg_alpha,
        # Per-chart colors (panel.py reads them from eww.theme.json; the
        # SCSS copies color the matching panel titles). Default: the main
        # light font color, i.e. the pre-v3.0 single-color behavior.
        "chart_cpu": chart_colors.get("cpu", color_light),
        "chart_memory": chart_colors.get("memory", color_light),
        "chart_down": chart_colors.get("net_down", color_light),
        "chart_up": chart_colors.get("net_up", color_light),
        "chart_glow": bool(chart.get("glow", False)),
        "panel_bg_color": panel_bg_color,
        "panel_bg_alpha": panel_bg_alpha,
        "panel_bg_image": panel_background.get("gradient") or "none",
        "text_shadow": _text_shadow_value(font_shadow),
        # Ink colors with contrast against their (effective) backgrounds:
        # the context menu / submenu paint bg_color, the panel paints
        # panel_bg_color.
        "menu_ink": _contrast_ink(bg_color, color_light),
        "panel_ink": _contrast_ink(panel_bg_color, color_light),
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


def write_theme_files(config_dir, data):
    """Write eww.theme.json + eww.theme.scss next to eww.yuck for `data`.

    Shared by theme.py's own main() and the live-preview worker
    (scripts/move/theme_preview.py) so both generate the identical theme files
    from the same resolved appearance dict. Expects `data` already fully
    populated (parse_appearance + bg_radius set).
    """
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
        f.write("$chart-cpu: %s;\n" % data["chart_cpu"])
        f.write("$chart-memory: %s;\n" % data["chart_memory"])
        f.write("$chart-down: %s;\n" % data["chart_down"])
        f.write("$chart-up: %s;\n" % data["chart_up"])
        f.write("$chart-glow: %s;\n" % ("true" if data["chart_glow"] else "false"))
        f.write("$panel-bg-color: %s;\n" % data["panel_bg_color"])
        f.write("$panel-bg-alpha: %s;\n" % data["panel_bg_alpha"])
        f.write("$panel-bg-image: %s;\n" % data["panel_bg_image"])
        f.write("$text-shadow: %s;\n" % data["text_shadow"])
        f.write("$menu-ink: %s;\n" % data["menu_ink"])
        f.write("$panel-ink: %s;\n" % data["panel_ink"])


def main():
    config_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())

    config = load_config(config_dir)
    appearance = config.get("appearance", "light")

    data = parse_appearance(load_appearance(config_dir, appearance))

    system = config.get("system", {}) or {}
    data["bg_radius"] = int(system.get("corner_radius", 20))

    icon_notes = generate_icons(config_dir, data)

    write_theme_files(config_dir, data)

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
    print_key(
        "chart colors",
        "cpu %s / mem %s / down %s / up %s"
        % (
            data["chart_cpu"],
            data["chart_memory"],
            data["chart_down"],
            data["chart_up"],
        ),
    )
    print_key("chart glow", "yes" if data["chart_glow"] else "no")
    print_key(
        "panel background",
        "%s @ %s%s"
        % (
            data["panel_bg_color"],
            data["panel_bg_alpha"],
            "" if data["panel_bg_image"] == "none" else " + gradient",
        ),
    )
    print_key("text shadow", data["text_shadow"])
    print_key("menu ink", data["menu_ink"])
    print_key("panel ink", data["panel_ink"])

    if icon_notes:
        print(icon_notes)


if __name__ == "__main__":
    main()
