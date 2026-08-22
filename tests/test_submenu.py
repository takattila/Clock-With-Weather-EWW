import json

import pytest

import submenu


@pytest.fixture
def themes(tmp_path, monkeypatch):
    """A fake assets/themes/appearance tree."""
    base = tmp_path / "appearance"
    base.mkdir()
    for name in ("dark", "dark-blue", "light"):
        (base / name).mkdir()
    monkeypatch.setattr(submenu, "APPEARANCE_THEMES_DIR", str(base))
    return base


# --- option lists -------------------------------------------------------------

def test_options_fixed_items():
    cfg = {}
    assert [o["value"] for o in submenu.options_for("hour_format", cfg)] == ["24", "12"]
    assert [o["value"] for o in submenu.options_for("units", cfg)] == ["metric", "imperial"]
    assert [o["value"] for o in submenu.options_for("panel_enabled", cfg)] == ["true", "false"]
    assert [o["value"] for o in submenu.options_for("panel_alignment", cfg)] == ["right", "left"]


def test_options_appearance_sorted(themes):
    values = [o["value"] for o in submenu.options_for("appearance", {})]
    assert values == ["dark", "dark-blue", "light"]


def test_options_appearance_missing_dir_falls_back_to_light(tmp_path, monkeypatch):
    monkeypatch.setattr(
        submenu, "APPEARANCE_THEMES_DIR", str(tmp_path / "missing")
    )
    assert [o["value"] for o in submenu.options_for("appearance", {})] == ["light"]


def test_unknown_item_exits():
    with pytest.raises(SystemExit):
        submenu.options_for("bogus", {})


# --- active value highlighting --------------------------------------------------

CFG = {
    "system": {"hour_format": "12"},
    "appearance": "dark-blue",
    "weather": {"units": "imperial"},
    "panel": {"enabled": False, "window": {"alignment": "left"}},
}


def test_active_values():
    assert submenu.active_for("hour_format", CFG) == "12"
    assert submenu.active_for("appearance", CFG) == "dark-blue"
    assert submenu.active_for("units", CFG) == "imperial"
    assert submenu.active_for("panel_enabled", CFG) == "false"
    assert submenu.active_for("panel_alignment", CFG) == "left"


def test_active_defaults_and_custom_map():
    assert submenu.active_for("hour_format", {}) == "24"
    assert submenu.active_for("units", {}) == "metric"
    assert submenu.active_for("panel_enabled", {}) == "true"
    assert submenu.active_for("panel_alignment", {}) == "right"
    # custom inline appearance map -> no theme can be highlighted
    assert submenu.active_for("appearance", {"appearance": {"theme": "x"}}) == "__none__"


# --- column split ----------------------------------------------------------------

def test_split_two_columns_balanced(themes):
    options = submenu.options_for("appearance", {})
    a, b = submenu.split_columns(options, 2)
    assert len(a) == 2 and len(b) == 1
    assert a[0]["value"] == "dark" and b[-1]["value"] == "light"


def test_split_odd_count_keeps_order(themes, monkeypatch):
    monkeypatch.setattr(submenu, "available_themes",
                        lambda: [f"t{i}" for i in range(5)])
    a, b = submenu.split_columns(submenu.options_for("appearance", {}), 2)
    assert [o["value"] for o in a] == ["t0", "t1", "t2"]
    assert [o["value"] for o in b] == ["t3", "t4"]


def test_split_single_column():
    options = [{"label": "24h", "value": "24"}, {"label": "12h", "value": "12"}]
    a, b = submenu.split_columns(options, 1)
    assert a == options and b == []


# --- pane top offset ---------------------------------------------------------------

def test_pane_top_offsets_follow_row_order():
    for key, row in submenu.ROWS.items():
        assert submenu.pane_top_for(key) == int(submenu.MENU_PAD + row * submenu.ROW_H)


# --- build_yuck (literal payload) ---------------------------------------------------

def test_build_yuck_bakes_values_and_handlers():
    options = [{"label": "24h", "value": "24"},
               {"label": "12h", "value": "12"}]
    yuck = submenu.build_yuck("hour_format", options, "12", 1)
    assert yuck.count("(eventbox") == 2
    assert ':class "sub-btn active"' in yuck          # 12h highlighted
    assert "--key hour_format --value 24" in yuck
    assert "--key hour_format --value 12" in yuck
    assert "close_popup.py" in yuck                    # click dismisses popups
    assert "touch /tmp/" not in yuck                   # no debug markers


def test_build_yuck_two_columns(themes):
    options = submenu.options_for("appearance", {})
    yuck = submenu.build_yuck("appearance", options, "dark", 2)
    assert ':class "sub-btn active"' in yuck           # dark highlighted
    assert yuck.count('(box :orientation "v"') == 2    # two column boxes
    assert '"light"' in yuck


# --- open_item wiring ---------------------------------------------------------------

def test_open_item_updates_pane_vars(themes, tmp_path, monkeypatch):
    merged = tmp_path / "config.yaml"
    merged.write_text("appearance: dark\n", encoding="utf-8")

    import config_io
    monkeypatch.setattr(submenu, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config_io, "BASE_CONFIG_FILE", "config.yaml")
    monkeypatch.setattr(config_io, "LOCAL_CONFIG_FILE",
                        str(tmp_path / "config.local.yaml"))

    calls = []

    def fake_eww(*args):
        calls.append(list(args))

    monkeypatch.setattr(submenu, "eww", fake_eww)

    submenu.open_item("appearance")

    update = next(c for c in calls if c[0] == "update")
    payload = dict(a.split("=", 1) for a in update[1:])
    yuck = payload["sub_yuck"]
    # both themes present, dark highlighted, handlers baked in
    assert '"dark-blue"' in yuck and '"light"' in yuck
    assert ':class "sub-btn active"' in yuck
    assert "--key appearance --value dark-blue" in yuck
    # pane position: Theme row offset comes from ROWS (shifted by separators)
    assert payload["sub_top"] == str(submenu.pane_top_for("appearance"))
    assert payload["sub_show"] == "true"


def test_open_item_without_session_still_updates(themes, tmp_path, monkeypatch):
    # The picker pane lives inside the menu WINDOW, so a stale session does
    # not matter anymore: hovering works purely through eww variables.
    calls = []
    monkeypatch.setattr(submenu, "eww", lambda *a: calls.append(list(a)))
    monkeypatch.setattr(submenu, "CONFIG_DIR", str(tmp_path))
    import config_io
    monkeypatch.setattr(config_io, "BASE_CONFIG_FILE", "config.yaml")
    monkeypatch.setattr(config_io, "LOCAL_CONFIG_FILE",
                        str(tmp_path / "config.local.yaml"))
    (tmp_path / "config.yaml").write_text("", encoding="utf-8")

    submenu.open_item("hour_format")
    update = next(c for c in calls if c[0] == "update")
    assert any(a == "sub_show=true" for a in update[1:])
