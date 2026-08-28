import importlib.util
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MENU_TOGGLE = REPO_ROOT / "scripts" / "widgets" / "menu_toggle.py"

spec = importlib.util.spec_from_file_location("menu_toggle_under_test", MENU_TOGGLE)
menu_toggle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu_toggle)


@pytest.fixture
def writes(monkeypatch):
    """Capture config_set.py invocations instead of touching the real file."""
    calls = []
    monkeypatch.setattr(
        menu_toggle, "write",
        lambda key, value: calls.append((key, str(value))) or "ok",
    )
    return calls


@pytest.fixture
def themes(tmp_path, monkeypatch):
    """A fake assets/themes/appearance tree."""
    base = tmp_path / "appearance"
    base.mkdir()
    for name in ("dark", "dark-blue", "light"):
        (base / name).mkdir()
    monkeypatch.setattr(menu_toggle, "APPEARANCE_THEMES_DIR", str(base))
    return base


# --- flip logic --------------------------------------------------------------

def test_hour_format_flips_both_ways():
    assert menu_toggle.next_value("hour_format", {"system": {"hour_format": "24"}}) == "12"
    assert menu_toggle.next_value("hour_format", {"system": {"hour_format": "12"}}) == "24"


def test_hour_format_defaults_to_24_when_missing():
    assert menu_toggle.next_value("hour_format", {}) == "12"


def test_units_flips_and_defaults_to_metric():
    assert menu_toggle.next_value("units", {}) == "imperial"
    assert menu_toggle.next_value("units", {"weather": {"units": "metric"}}) == "imperial"
    assert menu_toggle.next_value("units", {"weather": {"units": "imperial"}}) == "metric"


def test_panel_enabled_handles_bool_and_string():
    assert menu_toggle.next_value("panel_enabled", {"panel": {"enabled": True}}) == "false"
    assert menu_toggle.next_value("panel_enabled", {"panel": {"enabled": False}}) == "true"
    assert menu_toggle.next_value("panel_enabled", {"panel": {}}) == "false"


def test_panel_alignment_flips():
    assert menu_toggle.next_value("panel_alignment", {}) == "left"
    assert menu_toggle.next_value(
        "panel_alignment", {"panel": {"window": {"alignment": "left"}}}
    ) == "right"


def test_unknown_key_exits():
    with pytest.raises(SystemExit):
        menu_toggle.next_value("bogus", {})


# --- theme cycling -----------------------------------------------------------

def test_theme_cycle_is_alphabetical_with_wraparound(themes):
    assert menu_toggle.next_appearance("dark") == "dark-blue"
    assert menu_toggle.next_appearance("dark-blue") == "light"
    assert menu_toggle.next_appearance("light") == "dark"  # wrap-around


def test_theme_cycle_starts_fresh_on_unknown_name(themes):
    assert menu_toggle.next_appearance("deleted-theme") == "dark"


def test_theme_cycle_starts_fresh_on_custom_map(themes):
    # A custom inline appearance map makes cfg["appearance"] an OBJECT.
    assert menu_toggle.next_appearance({"theme": "light"}) == "dark"


def test_theme_list_fallback_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        menu_toggle, "APPEARANCE_THEMES_DIR", str(tmp_path / "missing")
    )
    assert menu_toggle.available_themes() == ["light"]


# --- main() wiring -----------------------------------------------------------

def run_main(monkeypatch, key):
    monkeypatch.setattr("sys.argv", ["menu_toggle.py", "--key", key])


def test_main_writes_flipped_hour_format(writes, monkeypatch):
    run_main(monkeypatch, "hour_format")
    menu_toggle.main()
    assert writes == [("hour_format", "12")]


def test_main_writes_next_theme(writes, themes, monkeypatch):
    run_main(monkeypatch, "appearance")
    menu_toggle.main()
    assert writes == [("appearance", "dark")]


def test_main_units_refreshes_weather(writes, monkeypatch):
    calls = {"weather": None, "eww": []}
    # Hermetic: the flip must not depend on the real config.local.yaml (whose
    # metric/imperial the user may have changed live while testing).
    monkeypatch.setattr(
        menu_toggle, "load_merged",
        lambda _path: {"weather": {"units": "metric"}},
    )

    def fake_config_key(name):
        return {
            "api_key": "KEY", "city": "Budapest",
            "lang": "hu", "api_url": "https://x/weather",
        }[name]

    def fake_run(cmd, capture=False):
        joined = " ".join(str(part) for part in cmd)
        if "weather.py" in joined:
            calls["weather"] = cmd
            return '{"main": {}}'
        if "eww" in joined and "update" in joined:
            calls["eww"].append(cmd)
        return ""

    monkeypatch.setattr(menu_toggle, "config_key", fake_config_key)
    monkeypatch.setattr(menu_toggle, "run", fake_run)
    run_main(monkeypatch, "units")
    menu_toggle.main()
    assert writes == [("units", "imperial")]
    # weather.py re-run with the NEW units (arg index: python3, script,
    # api_key, city, lang, UNITS, api_url), result pushed into eww
    assert calls["weather"][5] == "imperial"
    assert any("weather_info=" in " ".join(c) for c in calls["eww"])


def test_main_panel_enabled_writes_bool_string(writes, monkeypatch):
    run_main(monkeypatch, "panel_enabled")
    menu_toggle.main()
    assert writes == [("panel_enabled", "false")]


# --- direct set (--value, used by the hover submenus) -------------------------------

def run_main_with_value(monkeypatch, key, value):
    monkeypatch.setattr(
        "sys.argv", ["menu_toggle.py", "--key", key, "--value", value]
    )


def test_main_value_sets_exact_value(writes, monkeypatch):
    run_main_with_value(monkeypatch, "hour_format", "12")
    menu_toggle.main()
    assert writes == [("hour_format", "12")]


def test_main_value_skips_flip_logic(themes, writes, monkeypatch):
    # even though the current theme is 'dark' (flip would pick dark-blue),
    # an explicit --value writes exactly what was asked
    run_main_with_value(monkeypatch, "appearance", "light-blue-bg")
    menu_toggle.main()
    assert writes == [("appearance", "light-blue-bg")]


def test_main_value_units_refreshes_weather(writes, monkeypatch):
    calls = {"weather": None}

    def fake_config_key(name):
        return {"api_key": "KEY", "city": "Budapest", "lang": "hu",
                "api_url": "https://x/weather"}[name]

    def fake_run(cmd, capture=False):
        joined = " ".join(str(part) for part in cmd)
        if "weather.py" in joined:
            calls["weather"] = cmd
            return "{}"
        return ""

    monkeypatch.setattr(menu_toggle, "config_key", fake_config_key)
    monkeypatch.setattr(menu_toggle, "run", fake_run)
    run_main_with_value(monkeypatch, "units", "metric")
    menu_toggle.main()
    assert writes == [("units", "metric")]
    assert calls["weather"][5] == "metric"


def test_write_invokes_config_set(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, capture=False):
        seen["cmd"] = cmd
        return "wrote ok"

    monkeypatch.setattr(menu_toggle, "run", fake_run)
    out = menu_toggle.write("hour_format", 24)
    assert out == "wrote ok"
    assert any("config_set.py" in str(part) for part in seen["cmd"])
    assert "--key" in seen["cmd"] and "hour_format" in seen["cmd"]
