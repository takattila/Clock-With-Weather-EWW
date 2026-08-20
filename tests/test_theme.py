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
    theme_dir = config_dir / "themes" / "appearance" / "light"
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
    src = config_dir / "images" / "theme" / "light" / "weather" / "dovora"
    el = config_dir / "images" / "theme" / "light" / "elements"
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
    src = config_dir / "images" / "theme" / "dark" / "weather" / "dovora"
    _make_png(src / "01d.png", (10, 20, 30))

    data = {"theme": "dark", "icon_set": "dovora", "icon_color": None}
    theme.generate_icons(str(config_dir), data)

    from PIL import Image

    out = Image.open(
        config_dir / "generated" / "icons" / "dark" / "weather" / "dovora" / "01d.png"
    ).convert("RGB")
    assert out.getpixel((0, 0)) == (10, 20, 30)