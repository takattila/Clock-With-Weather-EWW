import textwrap

import pytest

import theme


@pytest.fixture
def appearance_dict():
    return {
        "theme": "light",
        "icon": {"set": "dovora", "transparency": {"light": 0.5}},
        "font": {"face": "Noto Sans", "color": {"light": "#ffffff"}, "transparency": {"light": 0.8}},
        "background": {"color": "#000000", "transparency": 0.2},
    }


def test_parse_appearance(appearance_dict):
    data = theme.parse_appearance(appearance_dict)
    assert data["theme"] == "light"
    assert data["icon_set"] == "dovora"
    assert data["icon_alpha"] == 0.5
    assert data["icon_color"] is None
    assert data["font_face"] == "Noto Sans"
    assert data["color_light"] == "#ffffff"
    assert data["color_dark"] == "#9e9e9e"
    assert data["color_light_alpha"] == 0.8
    assert data["bg_color"] == "#000000"
    assert data["bg_alpha"] == 0.2


def test_parse_appearance_dark_theme():
    data = theme.parse_appearance(
        {
            "theme": "dark",
            "icon": {"transparency": {"light": 1.0, "dark": 0.6}, "color": {"dark": "#abcdef"}},
        }
    )
    assert data["icon_alpha"] == 0.6
    assert data["icon_color"] == "#abcdef"


def test_load_appearance_inline():
    appearance = {"theme": "light", "icon": {"set": "dovora"}}
    assert theme.load_appearance(".", appearance) == appearance


def test_load_appearance_theme_file(config_dir):
    theme_dir = config_dir / "assets" / "themes" / "appearance" / "light"
    theme_dir.mkdir(parents=True)
    (theme_dir / "appearance.yaml").write_text(
        "appearance:\n  theme: light\n  icon:\n    set: dovora\n", encoding="utf-8"
    )
    data = theme.load_appearance(str(config_dir), "light")
    assert data["theme"] == "light"
    assert data["icon"]["set"] == "dovora"


def test_load_appearance_missing_theme(config_dir):
    with pytest.raises(SystemExit):
        theme.load_appearance(str(config_dir), "does-not-exist")


def test_parse_appearance_style_defaults(appearance_dict):
    """Without the v3.0 style keys everything falls back to the classic values."""
    data = theme.parse_appearance(appearance_dict)
    assert data["chart_cpu"] == "#ffffff"
    assert data["chart_memory"] == "#ffffff"
    assert data["chart_down"] == "#ffffff"
    assert data["chart_up"] == "#ffffff"
    assert data["chart_glow"] is False
    assert data["panel_bg_color"] == "#000000"
    assert data["panel_bg_alpha"] == 0.2
    assert data["panel_bg_image"] == "none"
    assert data["text_shadow"] == "none"


def test_parse_appearance_style_keys():
    data = theme.parse_appearance(
        {
            "theme": "dark",
            "font": {
                "color": {"light": "#00e5ff", "dark": "#ff2d95"},
                "shadow": {"color": "#00e5ff", "blur": 8},
            },
            "background": {"color": "#000010", "transparency": 0.25},
            "chart": {
                "colors": {
                    "cpu": "#ff9500",
                    "memory": "#00e5ff",
                    "net_down": "#ff2d95",
                    "net_up": "#39ff14",
                },
                "glow": True,
            },
            "panel": {
                "background": {
                    "color": "#000020",
                    "transparency": 0.5,
                    "gradient": "linear-gradient(to bottom, #1b3a5c, #0d1f33)",
                }
            },
        }
    )
    assert data["chart_cpu"] == "#ff9500"
    assert data["chart_memory"] == "#00e5ff"
    assert data["chart_down"] == "#ff2d95"
    assert data["chart_up"] == "#39ff14"
    assert data["chart_glow"] is True
    assert data["panel_bg_color"] == "#000020"
    assert data["panel_bg_alpha"] == 0.5
    assert data["panel_bg_image"] == "linear-gradient(to bottom, #1b3a5c, #0d1f33)"
    assert data["text_shadow"] == (
        "0 0 8px rgba(0,229,255,0.85), 0 0 16px rgba(0,229,255,0.45)"
    )


def test_text_shadow_value():
    assert theme._text_shadow_value({}) == "none"
    assert theme._text_shadow_value({"color": "#ff0000"}) == "none"
    assert theme._text_shadow_value({"blur": 8}) == "none"
    assert theme._text_shadow_value({"color": "#00e5ff", "blur": 4}) == (
        "0 0 4px rgba(0,229,255,0.85), 0 0 8px rgba(0,229,255,0.45)"
    )
    # An unparsable blur falls back to 6 px.
    assert theme._text_shadow_value({"color": "#ffffff", "blur": "x"}) == (
        "0 0 6px rgba(255,255,255,0.85), 0 0 12px rgba(255,255,255,0.45)"
    )


def test_contrast_ink():
    # Dark backgrounds keep the (light) fallback ink.
    assert theme._contrast_ink("#000000", "#ffffff") == "#ffffff"
    assert theme._contrast_ink("#0a1420", "#6db3f2") == "#6db3f2"
    # Light backgrounds flip to a dark ink.
    assert theme._contrast_ink("#f5f7fa", "#f8fafc") == "#2e3436"
    assert theme._contrast_ink("#fff0f5", "#fdf6f9") == "#2e3436"


def test_parse_appearance_ink_dark_background(appearance_dict):
    # bg #000000 -> dark -> the classic light ink (unchanged behavior).
    data = theme.parse_appearance(appearance_dict)
    assert data["menu_ink"] == "#ffffff"
    assert data["panel_ink"] == "#ffffff"


def test_parse_appearance_ink_light_background():
    # Light PAINTED background + light text: the background flips dark
    # (hue-preserving) and the ink flips light with it.
    data = theme.parse_appearance(
        {
            "theme": "light",
            "font": {"color": {"light": "#fdf6f9", "dark": "#e8c7d8"}},
            "background": {"color": "#fff0f5", "transparency": 0.4},
            "panel": {"background": {"color": "#fff0f5", "transparency": 0.45}},
        }
    )
    assert theme._luminance(theme._parse_color(data["bg_color"])) < 60
    assert theme._luminance(theme._parse_color(data["panel_bg_color"])) < 60
    assert data["menu_ink"] == "#fdf6f9"
    assert data["panel_ink"] == "#fdf6f9"


def test_parse_appearance_ink_panel_differs_from_widget():
    # Dark widget background (light menu ink) + light panel background
    # (flipped dark -> light panel ink) are independent.
    data = theme.parse_appearance(
        {
            "theme": "dark",
            "font": {"color": {"light": "#ffffff"}},
            "background": {"color": "#0a1420", "transparency": 0.0},
            "panel": {"background": {"color": "#f5f7fa", "transparency": 0.5}},
        }
    )
    assert data["menu_ink"] == "#ffffff"
    assert data["panel_ink"] == "#ffffff"


def test_bg_for_text_flips_light_background_for_light_text():
    # pastel-bg: near-white text on a near-white background -> dark flip
    flipped = theme._bg_for_text("#f5f7fa", "#f8fafc")
    assert theme._luminance(theme._parse_color(flipped)) < 60
    # hue preserved: the bluish background stays bluish (blue >= red)
    r, g, b = theme._parse_color(flipped)
    assert b >= r


def test_bg_for_text_flips_dark_background_for_dark_text():
    flipped = theme._bg_for_text("#101418", "#2e3436")
    assert theme._luminance(theme._parse_color(flipped)) > 200


def test_bg_for_text_keeps_contrasting_backgrounds():
    # dark background + light text: unchanged
    assert theme._bg_for_text("#1a120b", "#ffffff") == "#1a120b"
    # light background + dark text: unchanged
    assert theme._bg_for_text("#ffffff", "#2e3436") == "#ffffff"


def test_parse_appearance_flips_only_painted_backgrounds():
    base = {
        "theme": "light",
        "font": {"color": {"light": "#f8fafc", "dark": "#cdd9e5"}},
        "background": {"color": "#f5f7fa", "transparency": 0.0},
        "panel": {"background": {"color": "#f5f7fa", "transparency": 0.5}},
    }
    # Fully transparent widget background: NOT flipped (the clock floats on
    # the wallpaper), so the menu keeps its light background + dark ink.
    d = theme.parse_appearance(base)
    assert d["bg_color"] == "#f5f7fa"
    assert d["menu_ink"] == "#2e3436"
    # Painted panel background: flipped dark -> panel ink flips light.
    assert theme._luminance(theme._parse_color(d["panel_bg_color"])) < 60
    assert d["panel_ink"] == "#f8fafc"

    # -bg variant: the painted widget background flips too.
    bg_variant = dict(base, background={"color": "#f5f7fa", "transparency": 0.45})
    d2 = theme.parse_appearance(bg_variant)
    assert theme._luminance(theme._parse_color(d2["bg_color"])) < 60
    assert d2["menu_ink"] == "#f8fafc"


def test_parse_appearance_keeps_dark_bg_themes_unchanged(appearance_dict):
    data = theme.parse_appearance(appearance_dict)
    assert data["bg_color"] == "#000000"
    assert data["panel_bg_color"] == "#000000"


def test_load_config_merges_local_overrides(config_dir):
    (config_dir / "config.yaml").write_text(
        "appearance: light\nsystem:\n  corner_radius: 20\n", encoding="utf-8"
    )
    (config_dir / "config.local.yaml").write_text(
        "appearance: dark\nsystem:\n  corner_radius: 8\n", encoding="utf-8"
    )
    cfg = theme.load_config(str(config_dir))
    assert cfg["appearance"] == "dark"
    assert cfg["system"]["corner_radius"] == 8


def test_parse_color():
    assert theme._parse_color("#ff0000") == (255, 0, 0)
    assert theme._parse_color("00ff00") == (0, 255, 0)
    assert theme._parse_color("#abcdef") == (171, 205, 239)


def test_tint_icon():
    from PIL import Image

    img = Image.new("RGB", (4, 4), (10, 20, 30))
    out = theme.tint_icon(img, "#00ff00")
    assert out.size == (4, 4)
    assert out.getpixel((0, 0))[:3] == (0, 255, 0)
    assert out.getpixel((0, 0))[3] == 255


def test_tint_icon_keeps_alpha():
    from PIL import Image

    img = Image.new("RGBA", (2, 2), (100, 100, 100, 128))
    out = theme.tint_icon(img, "#ff0000")
    assert out.getpixel((0, 0)) == (255, 0, 0, 128)


def _make_png(path, color=(200, 200, 200)):
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color).save(path)


def test_generate_icons_tint(config_dir):
    src = config_dir / "assets" / "icons-src" / "light" / "weather" / "dovora"
    el = config_dir / "assets" / "icons-src" / "light" / "elements"
    _make_png(src / "01d.png", (200, 200, 200))
    _make_png(el / "arrow-up.png", (200, 200, 200))

    data = {
        "theme": "light",
        "icon_set": "dovora",
        "icon_color": "#ff0000",
    }
    notes = theme.generate_icons(str(config_dir), data)
    assert notes is None

    from PIL import Image

    gen = config_dir / "generated" / "icons" / "light"
    tinted = Image.open(gen / "weather" / "dovora" / "01d.png").convert("RGB")
    assert tinted.getpixel((0, 0)) == (255, 0, 0)
    assert (gen / "elements" / "arrow-up.png").exists()


def test_generate_icons_copy_without_color(config_dir):
    src = config_dir / "assets" / "icons-src" / "dark" / "weather" / "dovora"
    _make_png(src / "01d.png", (10, 20, 30))

    data = {"theme": "dark", "icon_set": "dovora", "icon_color": None}
    theme.generate_icons(str(config_dir), data)

    from PIL import Image

    out = Image.open(
        config_dir / "generated" / "icons" / "dark" / "weather" / "dovora" / "01d.png"
    ).convert("RGB")
    assert out.getpixel((0, 0)) == (10, 20, 30)