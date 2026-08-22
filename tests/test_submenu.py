import json
import os
import subprocess

import pytest

import submenu


@pytest.fixture
def state(tmp_path, monkeypatch):
    """Isolated generated/ state files."""
    gen_file = tmp_path / "submenu_gen"
    monkeypatch.setattr(submenu, "GEN_FILE", str(gen_file))
    return gen_file


@pytest.fixture
def themes(tmp_path, monkeypatch):
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
    # custom inline map -> no theme can be highlighted
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


# --- geometry (relative to the parent menu's REAL rect; flip + clamp) ---------

# A synthetic parent-menu rect whose rows are exactly CTX-row-height tall:
# menu_h - 2 * MENU_PAD == 10 * 42.
MENU_W, MENU_H = 220, 2 * submenu.MENU_PAD + 10 * 42


def test_geometry_right_open_default():
    x, y, w, h = submenu.geometry_for(
        "units", 2, 800, 100, MENU_W, MENU_H, 1920, 1045
    )
    assert (x, y, w, h) == (
        800 + MENU_W - submenu.OVERLAP,
        100 + submenu.MENU_PAD + 5 * 42,
        submenu.SUB_W1,
        2 * submenu.SUB_ROW_H + submenu.SUB_PAD_V,
    )


def test_geometry_row_height_calibrated_from_parent_height():
    # A taller-than-usual parent menu widens its rows proportionally.
    menu_h = 2 * submenu.MENU_PAD + 10 * 47
    _, y, _, _ = submenu.geometry_for(
        "units", 2, 800, 100, MENU_W, menu_h, 1920, 1200
    )
    assert y == 100 + submenu.MENU_PAD + 5 * 47


def test_geometry_flips_left_at_right_edge():
    x, _, _, _ = submenu.geometry_for(
        "units", 2, 1850, 100, MENU_W, MENU_H, 1920, 1045
    )
    assert x == 1850 - submenu.SUB_W1 + submenu.OVERLAP


def test_geometry_clamps_when_neither_side_fits():
    x, _, _, _ = submenu.geometry_for(
        "units", 2, 10, 0, MENU_W, MENU_H, 200, 1000
    )
    assert x == 200 - submenu.SUB_W1  # clamped, no flip possible


def test_geometry_theme_is_two_columns_and_clamped_bottom(themes):
    n = len(submenu.options_for("appearance", {}))
    x, y, w, h = submenu.geometry_for(
        "appearance", n, 100, 700, MENU_W, MENU_H, 1400, 768
    )
    rows = (n + 1) // 2
    assert w == submenu.SUB_W2
    assert h == rows * submenu.SUB_ROW_H + submenu.SUB_PAD_V
    raw_y = 700 + submenu.MENU_PAD + submenu.ROWS["appearance"] * 42
    assert y == max(0, min(raw_y, 768 - h))
    assert x == 100 + MENU_W - submenu.OVERLAP


def test_geometry_unknown_row_raises():
    with pytest.raises(KeyError):
        submenu.geometry_for("bogus", 2, 0, 0, MENU_W, MENU_H, 1000, 1000)


# --- generation counter / scheduled close ------------------------------------------

def test_bump_gen_increments(state):
    assert submenu.read_gen() == 0
    assert submenu.bump_gen() == 1
    assert submenu.read_gen() == 1


def test_delayed_close_closes_when_gen_unchanged(state, monkeypatch):
    monkeypatch.setattr(submenu, "CLOSE_DELAY", 0.01)
    calls = []
    monkeypatch.setattr(submenu, "eww", lambda *a: calls.append(a))
    submenu.delayed_close(submenu.read_gen())
    assert calls == [("close", "submenu")]


def test_delayed_close_skips_when_gen_moved_on(state, monkeypatch):
    monkeypatch.setattr(submenu, "CLOSE_DELAY", 0.01)
    calls = []
    monkeypatch.setattr(submenu, "eww", lambda *a: calls.append(a))
    stale_gen = submenu.read_gen()
    submenu.bump_gen()  # a newer hover/cancel happened meanwhile
    submenu.delayed_close(stale_gen)
    assert calls == []


def test_schedule_close_spawns_detached_helper(state, monkeypatch):
    spawned = []

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            spawned.append((cmd, kwargs))

        def wait(self):
            return 0

    monkeypatch.setattr(submenu.subprocess, "Popen", FakePopen)
    submenu.schedule_close()
    cmd, kwargs = spawned[0]
    assert "--_delayed-close" in cmd
    assert cmd[-1] == str(submenu.read_gen())
    assert kwargs.get("start_new_session") is True


# --- open_item wiring ---------------------------------------------------------------

@pytest.fixture
def session_ctx(tmp_path, monkeypatch):
    sess = tmp_path / "input_session.json"
    sess.write_text(json.dumps({"mode": "ctx", "x": 400, "y": 328, "screen": 1}))
    monkeypatch.setattr(submenu, "SESSION_FILE", str(sess))
    return sess


def test_open_item_positions_relative_to_parent_window(
    session_ctx, themes, state, tmp_path, monkeypatch
):
    merged = tmp_path / "config.yaml"
    merged.write_text("appearance: dark\n", encoding="utf-8")

    import config_io
    monkeypatch.setattr(submenu, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config_io, "BASE_CONFIG_FILE", "config.yaml")
    monkeypatch.setattr(config_io, "LOCAL_CONFIG_FILE",
                        str(tmp_path / "config.local.yaml"))
    # The parent ctx_menu window really sits at abs (400, 328) on the
    # monitor with index 1 (origin at 0/0).
    monkeypatch.setattr(submenu, "ctx_menu_rect",
                        lambda: {"w": MENU_W, "h": MENU_H, "ax": 400, "ay": 328})
    monkeypatch.setattr(submenu, "monitor_at",
                        lambda ax, ay: {"index": 1, "x": 0, "y": 0,
                                        "width": 1368, "height": 768})
    monkeypatch.setattr(submenu, "frame_size", lambda screen: (1368, 738))

    calls = []

    def fake_eww(*args):
        calls.append(list(args))

    monkeypatch.setattr(submenu, "eww", fake_eww)

    submenu.open_item("appearance")

    gen_after = submenu.read_gen()

    update = next(c for c in calls if c[0] == "update")
    payload = update[1]
    assert payload.startswith("sub_yuck=")
    yuck = payload[len("sub_yuck="):]
    # both themes present, dark highlighted, handlers baked in
    assert ':class "sub-btn active"' in yuck
    assert '"dark-blue"' in yuck and '"light"' in yuck
    assert "--cancel-close" in yuck and "--schedule-close" in yuck
    assert "--key appearance --value dark" in yuck

    open_call = next(c for c in calls if c[0] == "open")
    flat = " ".join(open_call)
    assert "submenu" in open_call[-1]
    # eww gets the monitor via a separate `--screen <N>` argument pair
    assert "1" == open_call[open_call.index("--screen") + 1]
    # anchored right of the parent menu's real right edge, at the Theme row
    expected_x = 400 + MENU_W - submenu.OVERLAP
    expected_y = 328 + submenu.MENU_PAD + submenu.ROWS["appearance"] * 42
    assert f"sx={expected_x}" in flat
    assert f"sy={expected_y}" in flat
    assert gen_after >= 1


def test_open_item_without_session_aborts(state, themes, tmp_path, monkeypatch):
    sess = tmp_path / "missing.json"
    monkeypatch.setattr(submenu, "SESSION_FILE", str(sess))
    calls = []
    monkeypatch.setattr(submenu, "eww", lambda *a: calls.append(a))
    monkeypatch.setattr(submenu, "ctx_menu_rect", lambda: None)
    submenu.open_item("units")  # must not raise
    assert calls == []          # no update / no open without a live menu


def test_open_item_without_parent_window_aborts(session_ctx, state,
                                                tmp_path, monkeypatch):
    # session exists but the ctx_menu X window is gone -> no orphan submenu
    calls = []
    monkeypatch.setattr(submenu, "eww", lambda *a: calls.append(a))
    monkeypatch.setattr(submenu, "ctx_menu_rect", lambda: None)
    submenu.open_item("units")
    assert calls == []
