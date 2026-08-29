"""Pure helpers of the theme editor (scripts/move/theme_panel.py).

The GTK window itself cannot be constructed headless; these tests cover the
logic that does not touch the display: hex/pixel parsing, the appearance
draft round-trips, minimalization, validation and the two writers (the inline
config.local.yaml override for Save, the new theme file for Save As - both
take an explicit directory, so the real repo config/themes are never touched).
"""

from pathlib import Path
import sys

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "move"))
    import theme_panel  # noqa: E402
except SystemExit:
    pytest.skip("GTK3 not available in this environment", allow_module_level=True)


# ---------------------------------------------------------------------------
# hex / pixel parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("#ffffff", "#ffffff"),
        ("FFFFFF", "#ffffff"),
        ("#fff", "#ffffff"),
("#e8a87c", "#e8a87c"),
            ("  #12aBcd ", "#12abcd"),
        ("", None),
        ("  ", None),
        ("xyz", None),
        ("#12345", None),
        ("#gggggg", None),
    ],
)
def test_normalize_hex(raw, expected):
    assert theme_panel.normalize_hex(raw) == expected


def test_hex_or_falls_back():
    assert theme_panel.hex_or("#E8A87C", "#000000") == "#e8a87c"
    assert theme_panel.hex_or("", "#000000") == "#000000"
    assert theme_panel.hex_or(None, "#ff0000") == "#ff0000"
    assert theme_panel.hex_or("garbage", "#00ff00") == "#00ff00"


def test_rgb_hex_clamps():
    assert theme_panel.rgb_hex(255, 0, 128) == "#ff0080"
    assert theme_panel.rgb_hex(256, -5, 300) == "#ff00ff"


def test_pixel_color_at_8bit_rgb():
    # width=2, n_channels=3, rowstride=6 (no padding): two full rows.
    rowstride = 6
    nch = 3
    buf = bytearray([255, 0, 0,  9, 0, 0,
                     0, 255, 0,  0, 0, 255])
    assert theme_panel.pixel_color_at(buf, rowstride, nch, 0, 0, 2, 2) == (255, 0, 0)
    assert theme_panel.pixel_color_at(buf, rowstride, nch, 1, 0, 2, 2) == (9, 0, 0)
    assert theme_panel.pixel_color_at(buf, rowstride, nch, 2, 0, 2, 2) is None  # x >= width
    assert theme_panel.pixel_color_at(buf, rowstride, nch, 0, 1, 2, 2) == (0, 255, 0)
    assert theme_panel.pixel_color_at(buf, rowstride, nch, 1, 1, 2, 2) == (0, 0, 255)
    assert theme_panel.pixel_color_at(buf, rowstride, nch, 0, 2, 2, 2) is None  # y >= height


def test_pixel_color_at_boundaries():
    rowstride = 3
    buf = bytearray(b"\x01\x02\x03")
    assert theme_panel.pixel_color_at(buf, rowstride, 3, 0, 0, 1, 1) == (1, 2, 3)
    assert theme_panel.pixel_color_at(buf, rowstride, 3, 1, 1, 1, 1) is None


# ---------------------------------------------------------------------------
# to_draft / round-trips
# ---------------------------------------------------------------------------

def test_to_draft_fills_defaults_from_empty_map():
    d = theme_panel.to_draft({}, 20)
    assert d["theme"] == "light"
    assert d["icon_set"] == "dovora"
    assert d["font_face"] == "Noto Sans"
    assert d["font_color_light"] == "#ffffff"
    assert d["font_color_dark"] == "#9e9e9e"
    assert d["background_color"] == "#000000"
    assert d["background_transparency"] == 0.0
    assert d["chart_cpu"] == d["chart_memory"] == d["chart_down"] == d["chart_up"] == "#ffffff"
    assert d["panel_color"] == ""
    assert d["corner_radius"] == 20


ROSE_GOLD = {
    "theme": "dark",
    "icon": {"set": "monochrome",
             "transparency": {"light": 1.0, "dark": 0.85},
             "color": {"dark": "#e8c4b8"}},
    "font": {"face": "Noto Sans",
             "color": {"light": "#f3d9ce", "dark": "#d9a08c"},
             "transparency": {"light": 1.0, "dark": 1.0},
             "shadow": {"color": "#e8a87c", "blur": 5}},
    "background": {"transparency": 0.0, "color": "#1f1418"},
    "chart": {"colors": {"cpu": "#e8a87c", "memory": "#f0c9b4",
                         "net_down": "#c9899a", "net_up": "#a99bb5"},
              "glow": False},
}


def test_to_draft_reads_a_real_theme_structure():
    d = theme_panel.to_draft(ROSE_GOLD, 15)
    assert d["theme"] == "dark"
    assert d["icon_set"] == "monochrome"
    assert d["icon_transparency_dark"] == 0.85
    assert d["icon_color_dark"] == "#e8c4b8"
    assert d["font_shadow_color"] == "#e8a87c"
    assert d["font_shadow_blur"] == 5
    assert d["background_color"] == "#1f1418"
    assert d["chart_memory"] == "#f0c9b4"
    assert d["chart_glow"] is False


def test_draft_roundtrip_normalize_then_to_draft():
    d0 = theme_panel.to_draft(ROSE_GOLD, 15)
    a = theme_panel.normalize_appearance(d0)
    d1 = theme_panel.to_draft(a, 15)
    assert d0 == d1 or all(
        abs(float(d0[k]) - float(d1[k])) < 1e-9 if isinstance(d0[k], float)
        else d0[k] == d1[k]
        for k in d0
    )


def test_normalize_appearance_omits_empty_optional_sections():
    d = theme_panel.to_draft({}, 15)
    a = theme_panel.normalize_appearance(d)
    assert "color" not in a["icon"]      # no icon tint
    assert "shadow" not in a["font"]     # no glow
    assert "panel" not in a              # panel follows the widget background
    assert a["chart"]["glow"] is False
    assert a["background"] == {"transparency": 0.0, "color": "#000000"}


def test_normalize_appearance_keeps_icon_color_and_shadow_when_set():
    d = theme_panel.to_draft(ROSE_GOLD, 15)
    a = theme_panel.normalize_appearance(d)
    assert a["icon"]["color"] == {"dark": "#e8c4b8"}
    assert a["font"]["shadow"] == {"color": "#e8a87c", "blur": 5}
    assert "panel" not in a


def test_normalize_appearance_panel_when_custom_background():
    d = theme_panel.to_draft({
        "background": {"color": "#0d1f33", "transparency": 0.3},
        "panel": {"background": {"color": "#123456", "transparency": 0.5,
                                 "gradient": "linear-gradient(to bottom, #1b3a5c, #0d1f33)"}},
    }, 15)
    a = theme_panel.normalize_appearance(d)
    assert a["panel"]["background"]["color"] == "#123456"
    assert a["panel"]["background"]["transparency"] == 0.5
    assert "linear-gradient" in a["panel"]["background"]["gradient"]


def test_minimalize_drops_trivial_chart():
    d = theme_panel.to_draft({}, 15)
    a = theme_panel.minimalize_appearance(d)
    assert "chart" not in a


def test_minimalize_keeps_chart_when_glow_or_diverging_color():
    plain = theme_panel.to_draft({}, 15)
    d_glow = dict(plain, chart_glow=True)
    assert "chart" in theme_panel.minimalize_appearance(d_glow)
    d_color = dict(plain, chart_cpu="#ff0000")
    assert "chart" in theme_panel.minimalize_appearance(d_color)


def test_minimalize_keeps_panel_only_when_written():
    plain = theme_panel.to_draft({}, 15)
    assert "panel" not in theme_panel.minimalize_appearance(plain)
    d_panel = dict(plain, panel_color="#112233", panel_transparency=0.5)
    assert "panel" in theme_panel.minimalize_appearance(d_panel)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def test_validate_theme_and_basics():
    assert theme_panel.validate("theme", "dark")[0] is True
    assert theme_panel.validate("theme", "blue")[0] is False
    assert theme_panel.validate("icon_set", "dovora")[0] is True
    assert theme_panel.validate("icon_set", "  ")[0] is False
    assert theme_panel.validate("font_face", "Noto Sans")[0] is True
    assert theme_panel.validate("font_face", "")[0] is False


def test_validate_hex_fields():
    for key in ("font_color_light", "background_color", "chart_cpu",
                "panel_color", "icon_color_light", "font_shadow_color"):
        assert theme_panel.validate(key, "#12abCD") == (True, None)
        if key in ("icon_color_light", "font_shadow_color", "panel_color"):
            assert theme_panel.validate(key, "") == (True, None)  # optional
        else:
            assert theme_panel.validate(key, "")[0] is False
        assert theme_panel.validate(key, "nope")[0] is False
    assert theme_panel.validate("font_color_light", "#12345")[0] is False


def test_validate_transparency_and_numbers():
    for key in ("icon_transparency_light", "font_transparency_dark",
                "background_transparency", "panel_transparency"):
        assert theme_panel.validate(key, "0.5") == (True, None)
        assert theme_panel.validate(key, "-0.1")[0] is False
        assert theme_panel.validate(key, "1.5")[0] is False
        assert theme_panel.validate(key, "abc")[0] is False
    assert theme_panel.validate("corner_radius", "15") == (True, None)
    assert theme_panel.validate("corner_radius", "x")[0] is False
    assert theme_panel.validate("font_shadow_blur", "8") == (True, None)
    assert theme_panel.validate("font_shadow_blur", "300")[0] is False


def test_validate_gradient():
    assert theme_panel.validate("panel_gradient", "linear-gradient(to bottom, #1b3a5c, #0d1f33)") == (True, None)
    assert theme_panel.validate("panel_gradient", "a\nb")[0] is False
    assert theme_panel.validate("panel_gradient", "x" * 201)[0] is False
    assert theme_panel.validate("bogus_key", "1")[0] is False


def test_validate_draft_full_ok():
    d = theme_panel.to_draft(ROSE_GOLD, 15)
    assert theme_panel.validate_draft(d) == (True, None)


def test_validate_draft_catches_bad_hex():
    d = theme_panel.to_draft(ROSE_GOLD, 15)
    d["chart_cpu"] = "rgb(1,2,3)"
    ok, msg = theme_panel.validate_draft(d)
    assert ok is False and "chart_cpu" in msg


# ---------------------------------------------------------------------------
# icon-set discovery
# ---------------------------------------------------------------------------

def test_available_icon_sets_scans_both_light_and_dark(tmp_path):
    for side in ("light", "dark"):
        base = tmp_path / "assets" / "icons-src" / side / "weather"
        base.mkdir(parents=True)
        (base / "dovora").mkdir()
        (base / "modern").mkdir() if side == "light" else None
    assert theme_panel.available_icon_sets(str(tmp_path)) == ["dovora", "modern"]


def test_available_icon_sets_missing_tree_is_empty(tmp_path):
    assert theme_panel.available_icon_sets(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# writers
# ---------------------------------------------------------------------------

def _full_draft():
    return theme_panel.to_draft(ROSE_GOLD, 18)


def test_save_inline_override_writes_full_map(tmp_path):
    import config_io
    # a pre-existing local file with unrelated keys must be preserved
    (tmp_path / "config.yaml").write_text(
        "appearance: light\nsystem:\n  corner_radius: 15\n", encoding="utf-8")
    (tmp_path / "config.local.yaml").write_text(
        "appearance: dark\nweather:\n  city: Tatabánya\n", encoding="utf-8")

    ok, err = theme_panel.save_inline_override(str(tmp_path), _full_draft(), 18)
    assert ok is True and err is None

    data = yaml.safe_load((tmp_path / "config.local.yaml").read_text(encoding="utf-8"))
    assert data["weather"]["city"] == "Tatabánya"   # other keys untouched
    assert data["system"]["corner_radius"] == 18
    assert isinstance(data["appearance"], dict)
    assert data["appearance"]["icon"]["color"]["dark"] == "#e8c4b8"
    assert data["appearance"]

    # the written inline map re-parses to the same theme values
    d = theme_panel.to_draft(data["appearance"], 18)
    assert d["background_color"] == "#1f1418"
    assert d["chart_memory"] == "#f0c9b4"


def test_save_inline_override_creates_local_file_when_missing(tmp_path):
    assert not (tmp_path / "config.local.yaml").exists()
    ok, _ = theme_panel.save_inline_override(str(tmp_path), _full_draft(), 15)
    assert ok is True
    assert (tmp_path / "config.local.yaml").exists()


def test_save_as_theme_writes_minimalized_file(tmp_path):
    theme_panel_theme = tmp_path / "assets" / "themes" / "appearance"
    ok, err = theme_panel.save_as_theme(str(tmp_path), "my-pastel", _full_draft())
    assert ok is True and err is None

    target = theme_panel_theme / "my-pastel" / "appearance.yaml"
    assert target.is_file()
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert data["appearance"]["theme"] == "dark"
    assert data["appearance"]["icon"]["color"]["dark"] == "#e8c4b8"
    # activated via config.local.yaml
    local = yaml.safe_load((tmp_path / "config.local.yaml").read_text(encoding="utf-8"))
    assert local["appearance"] == "my-pastel"


def test_save_as_theme_rejects_bad_names_and_duplicates(tmp_path):
    theme_panel_theme = tmp_path / "assets" / "themes" / "appearance"
    ok, _ = theme_panel.save_as_theme(str(tmp_path), "rose gold!", _full_draft())
    assert ok is False
    track = theme_panel_theme / "taken"
    track.mkdir(parents=True)
    ok, msg = theme_panel.save_as_theme(str(tmp_path), "taken", _full_draft())
    assert ok is False and "already exists" in msg


def test_save_as_theme_via_minimalize_roundtrip(tmp_path):
    d = theme_panel.to_draft(ROSE_GOLD, 15)
    assert theme_panel.save_as_theme(str(tmp_path), "roundtrip", d)[0] is True
    target = tmp_path / "assets" / "themes" / "appearance" / "roundtrip" / "appearance.yaml"
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    d1 = theme_panel.to_draft(data["appearance"], 15)
    assert d1["theme"] == "dark"
    assert d1["font_shadow_blur"] == 5
    assert d1["chart_cpu"] == "#e8a87c"
    assert d1["panel_color"] == ""


# ---------------------------------------------------------------------------
# child dialog positioning (Save As / color dialog follows the editor on drag)
# ---------------------------------------------------------------------------

def _child_panel(**kw):
    """A minimal ThemePanel-like object exposing only what _child_position uses."""
    obj = object.__new__(theme_panel.ThemePanel)
    defaults = dict(win_x=100, win_y=80, win_w=560, win_h=700,
                    desk_x0=0, desk_y0=0, desk_w=3288, desk_h=1080)
    defaults.update(kw)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def test_child_position_follows_editor():
    p = _child_panel(win_x=100, win_y=80, win_w=560, win_h=700)
    # dialog w=300 h=200 -> centered on the editor
    x, y = p._child_position(300, 200)
    assert x == 100 + (560 - 300) // 2  # 230
    assert y == 80 + (700 - 200) // 2  # 330
    # moving the editor moves the dialog the same relative way
    p.win_x, p.win_y = 1450, 220
    x2, y2 = p._child_position(300, 200)
    assert x2 == 1450 + (560 - 300) // 2
    assert y2 == 220 + (700 - 200) // 2


def test_child_position_clamps_to_virtual_desktop():
    p = _child_panel(win_x=100, win_y=80, win_w=560, win_h=700,
                     desk_x0=0, desk_y0=0, desk_w=3288, desk_h=1080)
    # A huge dialog at the desktop edge is clamped inside the desk box.
    x, y = p._child_position(5000, 3000)
    assert x <= p.desk_x0 + p.desk_w - 1
    assert y <= p.desk_y0 + p.desk_h - 1
    # A dialog follows when the editor moves to another monitor (positive x,
    # no longer clamped back to the origin monitor).
    p.win_x = 2500
    x2, _ = p._child_position(300, 200)
    assert x2 == 2500 + (560 - 300) // 2  # 2630
    assert x2 > 1368  # lands on the second monitor, not the origin one
