import json

import pytest

import submenu


@pytest.fixture(autouse=True)
def no_measured_rows(tmp_path, monkeypatch):
    """Isolate submenu.py from a generated/menu_rows.json on disk.

    measure_menu.py only runs against a LIVE X11 ctx_menu window (tests never
    open one), but a leftover file from a desktop session would silently skew
    every row-offset test. Point MEASURED_FILE at a missing file, drop the
    cached read and re-derive THEME_ROW_TOP from the model pitches.
    """
    monkeypatch.setattr(submenu, "MEASURED_FILE", str(tmp_path / "menu_rows.json"))
    monkeypatch.setattr(submenu, "_measured_tops", None)
    monkeypatch.setattr(submenu, "_measured_loaded", False)
    monkeypatch.setattr(
        submenu, "THEME_ROW_TOP",
        submenu.row_top("clock", submenu.CONTEXT_ROWS["clock"]["appearance"]),
    )


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


# --- live-measured row offsets -------------------------------------------------

def _load_measured(tmp_path, monkeypatch, payload):
    """Point submenu at a menu_rows.json `payload` (and re-arm the cache)."""
    monkeypatch.setattr(submenu, "MEASURED_FILE", str(tmp_path / "menu_rows.json"))
    monkeypatch.setattr(submenu, "_measured_tops", None)
    monkeypatch.setattr(submenu, "_measured_loaded", False)
    (tmp_path / "menu_rows.json").write_text(json.dumps(payload))


def test_measured_tops_override_model_pitch(tmp_path, monkeypatch):
    # A desktop whose ctx-menu rows really render at a uniform 38px pitch.
    tops = [int(9 + 38 * i) for i in range(12)]
    _load_measured(tmp_path, monkeypatch, {"tops": tops, "pitch": 38, "pad": 7})
    assert submenu.measured_tops() == tuple(tops)
    assert submenu.row_top("clock", 0) == 9
    assert submenu.row_top("clock", 4) == 161          # AM/PM row
    assert submenu.row_top("clock", 11) == 427
    assert submenu.pane_top_for("appearance", "clock") == tops[5]


def test_measured_tops_rejected_when_malformed(tmp_path, monkeypatch):
    # Wrong row count, missing pad or non-numeric entries -> model fallback.
    _load_measured(tmp_path, monkeypatch, {"tops": [0, 1], "pad": 7})
    assert submenu.measured_tops() is None
    assert submenu.row_top("clock", 4) == submenu.MENU_PAD + sum(
        submenu.row_heights("clock")[:4]
    )
    _load_measured(tmp_path, monkeypatch, {"tops": list(range(12)), "pad": 3})
    assert submenu.measured_tops() is None
    _load_measured(tmp_path, monkeypatch, {"tops": list("x" * 12), "pad": 7})
    assert submenu.measured_tops() is None
    _load_measured(tmp_path, monkeypatch, {"appearance": 4})
    assert submenu.measured_tops() is None


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
    # Offsets are computed from the REAL per-row heights (buttons and
    # separators differ!), which is what lines the pane up with the parent.
    assert submenu.pane_top_for("hour_format") == submenu.row_top(
        "clock", submenu.CONTEXT_ROWS["clock"]["hour_format"])
    for widget, rows in submenu.CONTEXT_ROWS.items():
        for key, row in rows.items():
            assert submenu.pane_top_for(key, widget) == \
                submenu.row_top(widget, row)


def test_row_sequences_match_collapsed_column():
    # The sequences mirror widget_ctx_menu as it renders COLLAPSED (the
    # hidden :visible wrappers take no space - see the yuck). Clock:
    # Move Resize Reset | sep | AM/PM Theme sep Units Weather | sep |
    # Hard reset About. Panel drops the clock-only rows and adds its own.
    assert submenu.ROW_SEQUENCES["clock"] == ["B", "B", "B", "S",
                                              "B", "B", "S", "B", "B",
                                              "S", "B", "B"]
    assert submenu.ROW_SEQUENCES["panel"] == ["B", "B", "B", "S",
                                              "B", "S", "B", "B", "B",
                                              "S", "B", "B"]
    for widget, seq in submenu.ROW_SEQUENCES.items():
        assert len(seq) == submenu.VISIBLE_ROW_COUNTS[widget] == 12
        assert set(seq) <= {"B", "S"}          # every slot is a known row type
        assert seq[3] == "S"                   # the Always group separator sits
        assert seq[-3] == "S"                  # after row 3 and the last gap
        assert seq[-1] == "B"                  # About is the last row
    # each selectable row's index points at a BUTTON slot (never a sep)
    for widget, rows in submenu.CONTEXT_ROWS.items():
        for key, row in rows.items():
            assert submenu.ROW_SEQUENCES[widget][row] == "B"


def test_separators_are_shorter_than_buttons():
    # The whole reason offsets cannot be a uniform pitch: a .ctx-sep row is
    # much smaller than a .ctx-btn row, so the pane math must be cumulative.
    assert submenu.ROW_SEP < submenu.ROW_BTN
    # Theme sits below the first separator: uniform ROW_BTN pitch would be
    # wrong, the cumulative offset must skip the short sep after Resize.
    assert submenu.pane_top_for("appearance", "clock") < \
        submenu.MENU_PAD + submenu.CONTEXT_ROWS["clock"]["appearance"] * \
        submenu.ROW_BTN


def test_context_rows_match_collapsed_column():
    # These indices back the widget_ctx_menu column as it renders COLLAPSED
    # (the hidden :visible wrappers take no space - see the yuck). Clock
    # shows AM/PM(4)+Theme(5)+sep(6)+Units(7); the panel menu DROPS the
    # clock-only rows, so Theme is one row higher (4) and Panel/Side are 6/7.
    assert submenu.CONTEXT_ROWS["clock"]["appearance"] == 5
    assert submenu.CONTEXT_ROWS["panel"]["appearance"] == 4
    assert submenu.CONTEXT_ROWS["clock"]["hour_format"] == 4
    assert submenu.CONTEXT_ROWS["clock"]["units"] == 7
    assert submenu.CONTEXT_ROWS["panel"]["panel_enabled"] == 6
    assert submenu.CONTEXT_ROWS["panel"]["panel_alignment"] == 7
    # each menu only carries its own rows; the union is the full picker set
    assert set(submenu.CONTEXT_ROWS["clock"]) == {"hour_format", "appearance", "units"}
    assert set(submenu.CONTEXT_ROWS["panel"]) == {"appearance", "panel_enabled",
                                                  "panel_alignment"}
    assert set(submenu.KEYS) == {"hour_format", "appearance", "units",
                                 "panel_enabled", "panel_alignment"}
    # both menus report the same count (12 visible rows) -> the column height
    # is the same for both, even though the Theme row differs by one.
    assert submenu.VISIBLE_ROW_COUNTS["clock"] == submenu.VISIBLE_ROW_COUNTS["panel"] == 12


def test_theme_row_offset_depends_on_widget_column():
    # THEME_ROW_TOP anchors the clock column (Theme sits at visible row 5,
    # after Move/Resize/Reset + the short sep). The panel column drops the
    # AM/PM row, so its Theme pane opens one row higher - this is the
    # "Panel/Side somewhere else" bug guard: the pane must track the
    # COLLAPSED column position, not the markup index.
    assert submenu.THEME_ROW_TOP == submenu.pane_top_for("appearance", "clock")
    panel_top = submenu.pane_top_for("appearance", "panel")
    assert panel_top == submenu.row_top(
        "panel", submenu.CONTEXT_ROWS["panel"]["appearance"])
    assert panel_top < submenu.THEME_ROW_TOP
    # the panel's extra rows stack BELOW its Theme row in order
    assert submenu.pane_top_for("panel_enabled", "panel") > \
        submenu.pane_top_for("appearance", "panel")
    assert submenu.pane_top_for("panel_alignment", "panel") > \
        submenu.pane_top_for("panel_enabled", "panel")


# --- menu content height / window layout (never-clip + bottom anchoring) ---

def test_menu_content_height_matches_real_row_sum():
    assert submenu.menu_content_height("clock") == \
        int(sum(submenu.row_heights("clock")) + 2 * submenu.MENU_PAD)
    assert submenu.menu_content_height("panel") == \
        int(sum(submenu.row_heights("panel")) + 2 * submenu.MENU_PAD)
    # both columns stack the same 12 rows -> the same column height
    assert submenu.menu_content_height("clock") == \
        submenu.menu_content_height("panel")
    assert submenu.menu_content_height() == submenu.menu_content_height("clock")
    # unknown widget falls back to the clock menu
    assert submenu.menu_content_height("bogus") == submenu.menu_content_height("clock")


def test_menu_layout_top_of_screen_keeps_y_and_sizes_window():
    content_h = submenu.menu_content_height("clock")
    needed_h = submenu.THEME_ROW_TOP + submenu.max_pane_height(2) + submenu.MENU_PAD
    y, window_h = submenu.menu_layout(100, 1080, content_h, needed_h)
    assert y == 100                                  # plenty of room below
    # window grows up to needed_h (theme picker worst case) but never below
    # the column content
    assert window_h == needed_h
    assert window_h >= content_h
    assert y + window_h <= 1080 - submenu.EDGE_MARGIN


def test_menu_layout_near_bottom_anchors_to_screen_bottom():
    content_h = submenu.menu_content_height("clock")
    # 900 of 1080 -> the column would cross the bottom edge by far
    y, window_h = submenu.menu_layout(900, 1080, content_h, 865)
    available = 1080 - submenu.EDGE_MARGIN
    assert y == available - content_h                # anchored flush to the bottom
    assert y + content_h == available
    assert window_h == content_h                     # never below the content
    assert window_h <= content_h + 1


def test_menu_layout_exact_boundary_keeps_y():
    content_h = submenu.menu_content_height("clock")
    available = 1080 - submenu.EDGE_MARGIN
    # y is exactly where the content ends flush with the bottom -> unchanged
    y, window_h = submenu.menu_layout(available - content_h, 1080, content_h, 865)
    assert y == available - content_h
    assert y + content_h == available
    assert window_h == content_h


def test_menu_layout_tiny_monitor_clamps_y_and_keeps_content():
    content_h = submenu.menu_content_height("clock")
    # Monitors smaller than the column (320px) cannot fit the content at all:
    # y never goes negative and the window never shrinks below the content.
    y, window_h = submenu.menu_layout(0, 320, content_h, 865)
    assert y == 0
    assert window_h == content_h
    y, window_h = submenu.menu_layout(80, 320, content_h, 865)
    assert y == 0
    assert window_h == content_h


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
    assert not any(a.startswith(("menu_h=", "pos_y=")) for a in update[1:])
    assert pane2 + submenu.THEME_ROW_TOP + submenu.MENU_PAD <= 865


def test_open_item_slides_pane_up_to_the_screen_edge(themes, tmp_path, monkeypatch):
    # Menu opened low on the screen (y=441 of 1080): the window only reaches
    # to the bottom edge (631px), so two columns cannot fit at all — the
    # picker goes to three columns. With the real (separator-aware) row
    # offset the three-column pane fits exactly at the Theme row and stays
    # row-aligned (the old uniform-pitch offset sat lower and left the pane
    # only sliding up).
    _many_themes(monkeypatch, 42)
    payload, _ = _open(monkeypatch, tmp_path, session={
        "x": 100, "y": 441, "screen": 0, "menu_h": 631, "monitor_h": 1080,
    })

    pane3 = submenu.pane_height([None] * 42, 3)
    limit = min(631, 1080 - submenu.EDGE_MARGIN - 441) - submenu.MENU_PAD
    top = int(payload["sub_top"])
    assert payload["sub_cols"] == "3"
    assert top == max(submenu.MENU_PAD, min(submenu.THEME_ROW_TOP, limit - pane3))
    assert 441 + top + pane3 <= 1080 - submenu.EDGE_MARGIN  # fully on-screen
    # the corrected offset leaves enough room below the parent row, so the
    # pane stays in line with it instead of drifting.
    assert top == submenu.THEME_ROW_TOP


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
    assert x == 1500 - submenu.PANE_W
    assert 1500 - submenu.PANE_W + submenu.MENU_COL_W + submenu.PANE_W <= 1920


def test_horizontal_layout_shifts_left_when_neither_side_fits():
    # Degenerate: pane fits on neither side -> plain left shift, clamped.
    x, flipped = submenu.horizontal_layout(50, 400)
    assert flipped is False
    assert x == max(0, min(50, 400 - submenu.MENU_COL_W - submenu.PANE_W
                           - submenu.EDGE_MARGIN))
