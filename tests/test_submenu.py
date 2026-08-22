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


# --- geometry (flip + clamp) ------------------------------------------------------

def test_geometry_right_open_default():
    x, y, w, h = submenu.geometry_for("units", 2, 800, 100, 1920, 1045)
    assert (x, y, w, h) == (1016, 317, submenu.SUB_W1, 2 * submenu.SUB_ROW_H + submenu.SUB_PAD_V)


def test_geometry_flips_left_at_right_edge():
    x, _, _, _ = submenu.geometry_for("units", 2, 1850, 100, 1920, 1045)
    assert x == 1850 - submenu.SUB_W1 + submenu.OVERLAP


def test_geometry_clamps_when_neither_side_fits():
    x, _, _, _ = submenu.geometry_for("units", 2, 10, 0, 200, 1000)
    assert x == 200 - submenu.SUB_W1  # clamped, no flip possible


def test_geometry_theme_is_two_columns_and_clamped_bottom(themes):
    n = len(submenu.options_for("appearance", {}))
    x, y, w, h = submenu.geometry_for("appearance", n, 100, 700, 1400, 768)
    rows = (n + 1) // 2
    assert w == submenu.SUB_W2
    assert h == rows * submenu.SUB_ROW_H + submenu.SUB_PAD_V
    assert y == max(0, min(700 + submenu.MENU_PAD + submenu.ROWS["appearance"] * submenu.CTX_ROW_H,
                           768 - h))
    assert x == 100 + submenu.CTX_MENU_W - submenu.OVERLAP


def test_geometry_unknown_row_raises():
    with pytest.raises(KeyError):
        submenu.geometry_for("bogus", 2, 0, 0, 1000, 1000)


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
    sess.write_text(json.dumps({"mode": "ctx", "x": 500, "y": 300, "screen": 1}))
    monkeypatch.setattr(submenu, "SESSION_FILE", str(sess))
    return sess


def test_open_item_pushes_vars_and_opens_window(session_ctx, themes, state,
                                                tmp_path, monkeypatch):
    merged = tmp_path / "config.yaml"
    merged.write_text("appearance: dark\n", encoding="utf-8")

    import config_io
    monkeypatch.setattr(submenu, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config_io, "BASE_CONFIG_FILE", "config.yaml")
    monkeypatch.setattr(config_io, "LOCAL_CONFIG_FILE",
                        str(tmp_path / "config.local.yaml"))
    monkeypatch.setattr(submenu, "frame_size", lambda screen: (1920, 1045))

    calls = []

    def fake_eww(*args):
        calls.append(list(args))

    monkeypatch.setattr(submenu, "eww", fake_eww)

    submenu.open_item("appearance")

    gen_after = submenu.read_gen()

    update = next(c for c in calls if c[0] == "update")
    payload = dict(arg.split("=", 1) for arg in update[1:])
    col_a = json.loads(payload["sub_col_a"])
    col_b = json.loads(payload["sub_col_b"])
    assert [o["value"] for o in col_a] == ["dark", "dark-blue"]
    assert [o["value"] for o in col_b] == ["light"]
    assert payload["sub_active"] == "dark"
    assert payload["sub_cols"] == "2"

    open_call = next(c for c in calls if c[0] == "open")
    flat = " ".join(open_call)
    assert "--id submenu" in flat or ("--id" in open_call and "submenu" in open_call)
    assert "key=appearance" in flat
    # anchored right of the ctx menu at the Theme row (row 4)
    expected_x = 500 + submenu.CTX_MENU_W - submenu.OVERLAP
    expected_y = submenu.MENU_PAD + submenu.ROWS["appearance"] * submenu.CTX_ROW_H + 300
    assert f"sx={expected_x}" in flat
    assert f"sy={expected_y}" in flat
    assert gen_after >= 1


def test_open_item_without_session_uses_fallback(themes, state, tmp_path, monkeypatch):
    sess = tmp_path / "missing.json"
    monkeypatch.setattr(submenu, "SESSION_FILE", str(sess))
    monkeypatch.setattr(submenu, "frame_size", lambda screen: (1920, 1045))
    calls = []
    monkeypatch.setattr(submenu, "eww", lambda *a: calls.append(a))
    submenu.open_item("units")
    open_call = next(c for c in calls if c[0] == "open")
    flat = " ".join(open_call)
    assert "key=units" in flat
