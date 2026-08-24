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
    assert submenu.split_columns(options, 1) == [options]


def test_split_three_columns_balanced():
    options = [{"value": "t%d" % i} for i in range(8)]
    chunks = submenu.split_columns(options, 3)
    assert [len(c) for c in chunks] == [3, 3, 2]
    assert [o["value"] for c in chunks for o in c] == [o["value"] for o in options]


# --- pane top offset / height -------------------------------------------------------

def test_pane_top_offsets_follow_row_order():
    for key, row in submenu.ROWS.items():
        assert submenu.pane_top_for(key) == int(submenu.MENU_PAD + row * submenu.ROW_H)


def test_pane_height_rows_and_padding():
    # 3 options in 2 columns -> 2 rows; 5 in 2 columns -> 3 rows
    assert submenu.pane_height([1, 2, 3], 2) == 2 * submenu.SUB_ROW_H + submenu.SUB_PAD_V
    assert submenu.pane_height([1, 2, 3, 4, 5], 2) == 3 * submenu.SUB_ROW_H + submenu.SUB_PAD_V
    assert submenu.pane_height([1, 2], 1) == 2 * submenu.SUB_ROW_H + submenu.SUB_PAD_V


def test_max_pane_height_follows_theme_count(themes, monkeypatch):
    monkeypatch.setattr(submenu, "available_themes",
                        lambda: [f"t{i}" for i in range(42)])
    assert submenu.max_pane_height(2) == submenu.pane_height([None] * 42, 2)
    monkeypatch.setattr(submenu, "available_themes", lambda: ["light"])
    assert submenu.max_pane_height() == submenu.pane_height([None], 2)


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
    # no session file -> fallback geometry (menu at the top of a 1080p
    # screen, default window height): the short pane stays row-aligned in
    # two columns, and the window itself is NEVER mutated from here
    # (menu_h / pos_y are window-arg variables, `eww update` cannot touch
    # them on a running window).
    assert payload["sub_top"] == str(submenu.pane_top_for("appearance"))
    assert payload["sub_cols"] == "2"
    assert payload["sub_w"] == str(submenu.SUB_W[2])
    assert payload["sub_show"] == "true"
    assert not any(a.startswith(("menu_h=", "pos_y=")) for a in update[1:])


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


# --- bottom-edge clamping (long theme lists) ------------------------------------------

def _many_themes(monkeypatch, count):
    monkeypatch.setattr(submenu, "available_themes",
                        lambda: [f"t{i:02d}" for i in range(count)])


def _open(monkeypatch, tmp_path, session=None):
    """Run open_item('appearance') with wired fakes.

    `session` mirrors the input-session dict ctx.py writes at menu open
    (x / y / screen / menu_h / monitor_h). Returns (payload, raw args).
    """
    import config_io
    monkeypatch.setattr(submenu, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config_io, "BASE_CONFIG_FILE", "config.yaml")
    monkeypatch.setattr(config_io, "LOCAL_CONFIG_FILE",
                        str(tmp_path / "config.local.yaml"))
    (tmp_path / "config.yaml").write_text("", encoding="utf-8")
    if session is not None:
        gen = tmp_path / "generated"
        gen.mkdir(exist_ok=True)
        (gen / "input_session.json").write_text(
            json.dumps(dict(session, mode="ctx")), encoding="utf-8")

    calls = []
    monkeypatch.setattr(submenu, "eww", lambda *a: calls.append(list(a)))
    submenu.open_item("appearance")
    update = next(c for c in calls if c[0] == "update")
    return dict(a.split("=", 1) for a in update[1:]), update


def test_open_item_keeps_row_alignment_when_window_is_tall(themes, tmp_path, monkeypatch):
    # ctx.py sized the window down to the monitor bottom (menu_h=865, menu
    # at y=100 on a 1080p monitor): all 42 themes fit below the Theme row
    # in two columns at the row-aligned offset.
    _many_themes(monkeypatch, 42)
    payload, update = _open(monkeypatch, tmp_path, session={
        "x": 100, "y": 100, "screen": 0, "menu_h": 865, "monitor_h": 1080,
    })

    pane2 = submenu.pane_height([None] * 42, 2)
    assert payload["sub_top"] == str(submenu.THEME_ROW_TOP)
    assert payload["sub_cols"] == "2"
    assert payload["sub_w"] == str(submenu.SUB_W[2])
    assert not any(a.startswith(("menu_h=", "pos_y=")) for a in update[1:])
    assert pane2 + submenu.THEME_ROW_TOP + submenu.MENU_PAD <= 865


def test_open_item_slides_pane_up_to_the_screen_edge(themes, tmp_path, monkeypatch):
    # Menu opened low on the screen (y=441 of 1080): the window only reaches
    # to the bottom edge (631px), so two columns (638px) cannot fit at all —
    # the picker goes to three columns AND slides up from its row until the
    # bottom aligns with the screen edge.
    _many_themes(monkeypatch, 42)
    payload, _ = _open(monkeypatch, tmp_path, session={
        "x": 100, "y": 441, "screen": 0, "menu_h": 631, "monitor_h": 1080,
    })

    pane3 = submenu.pane_height([None] * 42, 3)
    limit = min(631, 1080 - submenu.EDGE_MARGIN - 441) - submenu.MENU_PAD
    top = int(payload["sub_top"])
    assert payload["sub_cols"] == "3"
    assert top == max(submenu.MENU_PAD, min(submenu.THEME_ROW_TOP, limit - pane3))
    assert top < submenu.THEME_ROW_TOP                     # slid up
    assert 441 + top + pane3 <= 1080 - submenu.EDGE_MARGIN  # fully on-screen


def test_open_item_adds_a_column_when_height_is_tight(themes, tmp_path, monkeypatch):
    # Small monitor (768px), menu near its bottom: two columns cannot fit
    # even at the window top, so the picker switches to three columns
    # (trading width for height) and still ends fully on-screen.
    _many_themes(monkeypatch, 42)
    payload, _ = _open(monkeypatch, tmp_path, session={
        "x": 100, "y": 208, "screen": 0, "menu_h": 552, "monitor_h": 768,
    })

    pane3 = submenu.pane_height([None] * 42, 3)
    top = int(payload["sub_top"])
    assert payload["sub_cols"] == "3"
    assert payload["sub_w"] == str(submenu.SUB_W[3])
    assert top == max(submenu.MENU_PAD,
                      min(submenu.THEME_ROW_TOP,
                          min(552, 768 - submenu.EDGE_MARGIN - 208)
                          - submenu.MENU_PAD - pane3))
    assert 208 + top + pane3 <= 768 - submenu.EDGE_MARGIN


def test_open_item_clamps_pane_to_menu_padding(themes, tmp_path, monkeypatch):
    # Degenerate case (pane taller than everything available): the pane
    # clamps to the menu padding at the window top instead of going negative.
    _many_themes(monkeypatch, 42)
    payload, _ = _open(monkeypatch, tmp_path, session={
        "x": 0, "y": 0, "screen": 0, "menu_h": 300, "monitor_h": 320,
    })

    assert int(payload["sub_top"]) == submenu.MENU_PAD
    assert payload["sub_cols"] == "3"


# --- horizontal flip (right screen edge) ----------------------------------------------

def test_horizontal_layout_fits_right():
    # Plenty of room to the right: menu at the cursor, pane on the right.
    assert submenu.horizontal_layout(400, 1920) == (400, False)
    assert submenu.horizontal_layout(400, None) == (400, False)  # unknown monitor


def test_horizontal_layout_flips_left_near_right_edge():
    # Right-clicking the right-side panel: [menu + widest pane] would cross
    # the monitor edge, but the pane fits on the left -> window opens
    # pane_w_max further left, pane flips to the LEFT of the menu column.
    x, flipped = submenu.horizontal_layout(1500, 1920)
    assert flipped is True
    assert x == 1500 - submenu.SUB_W[3]
    assert 1500 - submenu.SUB_W[3] + submenu.MENU_COL_W + submenu.SUB_W[3] <= 1920


def test_horizontal_layout_shifts_left_when_neither_side_fits():
    # Degenerate: pane fits on neither side -> plain left shift, clamped.
    x, flipped = submenu.horizontal_layout(50, 400)
    assert flipped is False
    assert x == max(0, min(50, 400 - submenu.MENU_COL_W - submenu.SUB_W[3]
                           - submenu.EDGE_MARGIN))
