"""Pure helpers of the raindrop settings form (scripts/move/rain_panel.py).

The GTK window cannot be constructed headless, so these tests cover the logic
that does not need a display: value validation, the merged-config read and the
Reset helper (which rewrites config.local.yaml, so the tests point it at a
tmp_path and never touch the real one).
"""

import json
from pathlib import Path
import sys

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "move"))
    import rain_panel  # noqa: E402
except SystemExit:
    pytest.skip("GTK3 not available in this environment", allow_module_level=True)


# --- validation --------------------------------------------------------------

@pytest.mark.parametrize(
    "key,value,expected_ok",
    [
        ("rain_enabled", "true", True),
        ("rain_enabled", "false", True),
        ("rain_enabled", "TRUE", True),
        ("rain_enabled", "yes", False),
        ("rain_enabled", "", False),
        ("rain_auto", "true", True),
        ("rain_auto", "maybe", False),
        ("rain_count", "0", True),
        ("rain_count", "24", True),
        ("rain_count", "120", True),
        ("rain_count", "121", False),
        ("rain_count", "-1", False),
        ("rain_count", "12.5", False),
        ("rain_count", "many", False),
        ("rain_count", "", False),
        ("rain_speed", "1", True),
        ("rain_speed", "10", True),
        ("rain_speed", "0", False),
        ("rain_speed", "11", False),
        ("rain_opacity", "0", True),
        ("rain_opacity", "0.35", True),
        ("rain_opacity", "1", True),
        ("rain_opacity", "1.1", False),
        ("rain_opacity", "-0.1", False),
        ("rain_opacity", "clear", False),
        ("rain_opacity", "", False),
        ("rain_colour", "blue", False),   # never written silently
    ],
)
def test_validate(key, value, expected_ok):
    ok, _msg = rain_panel.validate(key, value)
    assert ok is expected_ok


def test_validate_error_messages():
    assert rain_panel.validate("rain_enabled", "yes")[1] == \
        "rain_enabled must be true or false"
    assert rain_panel.validate("rain_count", "999")[1] == "Count must be 0-120"
    assert rain_panel.validate("rain_count", "x")[1] == "Count must be a whole number"
    assert rain_panel.validate("rain_speed", "99")[1] == "Speed must be 1-10"
    assert rain_panel.validate("rain_opacity", "2")[1] == "Opacity must be 0.0-1.0"
    assert rain_panel.validate("rain_opacity", "x")[1] == "Opacity must be a number"
    assert rain_panel.validate("bogus", "1")[1] == "Unsupported setting: bogus"


def test_validate_accepts_non_string_input():
    # load_settings() hands back whatever YAML held; a bare int/bool must work.
    assert rain_panel.validate("rain_count", 24)[0] is True
    assert rain_panel.validate("rain_opacity", 0.5)[0] is True
    assert rain_panel.validate("rain_enabled", True)[0] is True
    assert rain_panel.validate("rain_enabled", None)[0] is False


def test_valid_ranges_match_config_set():
    # The panel must refuse exactly what config_set.py would refuse, otherwise
    # Save fails after the panel already claimed the value was fine.
    for key, good, bad in [
        ("rain_count", "60", "121"),
        ("rain_speed", "5", "0"),
        ("rain_opacity", "0.5", "1.5"),
    ]:
        assert rain_panel.validate(key, good)[0] is True
        assert rain_panel.validate(key, bad)[0] is False
        assert rain_panel.COUNT_MIN == 0 and rain_panel.COUNT_MAX == 120
        assert rain_panel.SPEED_MIN == 1 and rain_panel.SPEED_MAX == 10


# --- load_settings -----------------------------------------------------------

def _config_dir(tmp_path, base="", local=None, monkeypatch=None):
    (tmp_path / "config.yaml").write_text(
        "weather:\n  city: Tatabánya\n" + base, encoding="utf-8")
    if local is not None:
        (tmp_path / "config.local.yaml").write_text(local, encoding="utf-8")
    if monkeypatch is not None:
        monkeypatch.setattr(rain_panel, "CONFIG_DIR", str(tmp_path))
    return str(tmp_path)


def test_load_settings_defaults(tmp_path, monkeypatch):
    _config_dir(tmp_path, monkeypatch=monkeypatch)
    assert rain_panel.load_settings() == {
        "rain_enabled": "true", "rain_auto": "true",
        "rain_count": "24", "rain_speed": "5", "rain_opacity": "0.35",
    }


def test_load_settings_reads_the_rain_block(tmp_path, monkeypatch):
    _config_dir(tmp_path, "  rain:\n    enabled: false\n    count: 40\n",
               monkeypatch=monkeypatch)
    settings = rain_panel.load_settings()
    assert settings["rain_enabled"] == "false"
    assert settings["rain_count"] == "40"


def test_load_settings_prefers_the_local_override(tmp_path, monkeypatch):
    _config_dir(tmp_path, "  rain:\n    count: 40\n",
                local="weather:\n  rain:\n    count: 12\n",
                monkeypatch=monkeypatch)
    assert rain_panel.load_settings()["rain_count"] == "12"


def test_load_settings_normalizes_string_booleans(tmp_path, monkeypatch):
    _config_dir(tmp_path, "  rain:\n    enabled: 'false'\n    auto: 'true'\n",
               monkeypatch=monkeypatch)
    settings = rain_panel.load_settings()
    assert settings["rain_enabled"] == "false"
    assert settings["rain_auto"] == "true"


def test_load_settings_survives_a_scalar_rain_block(tmp_path, monkeypatch):
    _config_dir(tmp_path, "  rain: true\n", monkeypatch=monkeypatch)
    assert rain_panel.load_settings()["rain_count"] == "24"


def test_load_settings_survives_a_broken_config(tmp_path, monkeypatch):
    _config_dir(tmp_path, monkeypatch=monkeypatch)
    (tmp_path / "config.yaml").write_text("weather: [oops\n", encoding="utf-8")
    assert rain_panel.load_settings()["rain_enabled"] == "true"


# --- Reset -------------------------------------------------------------------

def test_reset_removes_only_the_rain_subtree(tmp_path, monkeypatch):
    _config_dir(
        tmp_path,
        local="weather:\n  city: Tatabánya\n  rain:\n    count: 30\n"
              "panel:\n  enabled: true\n",
        monkeypatch=monkeypatch,
    )
    assert rain_panel.reset_rain_overrides() is True
    data = yaml.safe_load((tmp_path / "config.local.yaml").read_text())
    assert "rain" not in data["weather"]
    assert data["weather"]["city"] == "Tatabánya"
    assert data["panel"]["enabled"] is True


def test_reset_drops_an_empty_weather_block(tmp_path, monkeypatch):
    _config_dir(tmp_path, local="weather:\n  rain:\n    count: 30\n",
                monkeypatch=monkeypatch)
    assert rain_panel.reset_rain_overrides() is True
    data = yaml.safe_load((tmp_path / "config.local.yaml").read_text())
    assert data == {}


def test_reset_without_a_local_file_is_a_no_op(tmp_path, monkeypatch):
    _config_dir(tmp_path, monkeypatch=monkeypatch)
    assert rain_panel.reset_rain_overrides() is True
    assert not (tmp_path / "config.local.yaml").exists()


def test_reset_reports_failure_on_unparsable_local_file(tmp_path, monkeypatch):
    _config_dir(tmp_path, local="[1, 2\n", monkeypatch=monkeypatch)
    assert rain_panel.reset_rain_overrides() is False


# --- CSS ---------------------------------------------------------------------

def test_build_css_is_complete_and_terminated():
    css = rain_panel.build_css("#1a1a1a", "#ffffff", 0.95, 10, "Inter")
    assert css.strip().endswith("}")
    assert "Inter" in css
    assert "rgba(26, 26, 26, 0.97)" in css
    assert "rgba(255, 255, 255, 0.95)" in css
    for selector in ("button.save", "button.toggle-btn.on", ".status",
                     ".status.hint", ".hint", ".title", "scale", "spinbutton"):
        assert selector in css


def test_build_css_status_hint_is_not_the_error_red():
    css = rain_panel.build_css("#000000", "#ffffff", 1.0, 8, "Inter")
    status_hint = [ln for ln in css.splitlines() if ".status.hint" in ln]
    assert status_hint, ".status.hint rule is missing"
    assert "255, 100, 100" not in status_hint[0]


# --- Save / dirty logic ------------------------------------------------------


class _FakeCtx:
    def __init__(self, on=False):
        self.classes = {"on"} if on else set()

    def add_class(self, name):
        self.classes.add(name)

    def remove_class(self, name):
        self.classes.discard(name)

    def list_classes(self):
        return list(self.classes)


class _FakeButton:
    def __init__(self, on=False):
        self._ctx = _FakeCtx(on)

    def get_style_context(self):
        return self._ctx


class _FakeScale:
    def __init__(self, value, digits):
        self._value = value
        self._digits = digits

    def get_value(self):
        return self._value

    def get_digits(self):
        return self._digits

    def set_value(self, value):
        self._value = value


class _FakeSpin:
    def __init__(self, value):
        self._value = value

    def get_value(self):
        return self._value

    def set_value(self, value):
        self._value = value


def _values(enabled="true", auto="true", count=24, speed=5, opacity=0.35):
    """What the CONTROLS hold right now (numbers, like the Gtk widgets)."""
    return {
        "rain_enabled": enabled, "rain_auto": auto,
        "rain_count": count, "rain_speed": speed, "rain_opacity": opacity,
    }


def _written(enabled="true", auto="true", count="24", speed="5", opacity="0.35"):
    """What the CONFIG holds (strings, as config_set.py writes them)."""
    return {
        "rain_enabled": enabled, "rain_auto": auto,
        "rain_count": count, "rain_speed": speed, "rain_opacity": opacity,
    }


def _panel_stub(values, committed, status_label=None):
    """A RainPanel carrying only what the control bookkeeping reads."""
    panel = rain_panel.RainPanel.__new__(rain_panel.RainPanel)
    panel.committed = dict(committed)
    panel.spins = {"rain_count": _FakeSpin(values["rain_count"])}
    panel.scales = {
        "rain_speed": _FakeScale(values["rain_speed"], 0),
        "rain_opacity": _FakeScale(values["rain_opacity"], 2),
    }
    panel.toggle_btns = {}
    for key in ("rain_enabled", "rain_auto"):
        active = str(values[key]).lower()
        for value in ("true", "false"):
            panel.toggle_btns[(key, value)] = _FakeButton(on=(value == active))
    panel.status_label = status_label
    panel.syncing = False
    return panel


def test_dirty_keys_is_empty_on_a_fresh_open():
    panel = _panel_stub(_values(), _written())
    assert panel.dirty_keys() == []


def test_dirty_keys_reports_a_changed_slider():
    panel = _panel_stub(_values(opacity=0.6), _written())
    assert panel.dirty_keys() == ["rain_opacity"]


def test_dirty_keys_reports_several_changes():
    panel = _panel_stub(_values(count=60, speed=8, auto="false"), _written())
    assert sorted(panel.dirty_keys()) == ["rain_auto", "rain_count", "rain_speed"]


def test_dirty_keys_reports_a_toggle():
    panel = _panel_stub(_values(enabled="false"), _written())
    assert panel.dirty_keys() == ["rain_enabled"]


def test_dirty_keys_normalises_scale_formatting():
    # Gtk.Scale with 2 digits renders "5.00" / "0.40"; config_set.py takes the
    # trimmed text, so an untouched panel must not look dirty.
    panel = _panel_stub(_values(speed=5, opacity=0.4), _written(opacity="0.4"))
    assert panel.dirty_keys() == []


def test_dirty_keys_survives_an_int_in_the_config():
    # A hand-edited config.local.yaml can hold real YAML ints/bools.
    panel = _panel_stub(_values(), {"rain_enabled": True, "rain_auto": True,
                                    "rain_count": 24, "rain_speed": 5,
                                    "rain_opacity": 0.35})
    assert panel.dirty_keys() == []


def test_dirty_keys_survives_a_string_bool_in_the_config():
    panel = _panel_stub(_values(), {"rain_enabled": "true", "rain_auto": "true",
                                    "rain_count": "24", "rain_speed": "5",
                                    "rain_opacity": "0.35"})
    assert panel.dirty_keys() == []


def test_dirty_keys_detects_a_change_against_an_int_config():
    panel = _panel_stub(_values(count=60), {"rain_enabled": True,
                                            "rain_auto": True,
                                            "rain_count": 24, "rain_speed": 5,
                                            "rain_opacity": 0.35})
    assert panel.dirty_keys() == ["rain_count"]


def test_current_reads_the_active_toggle_button():
    panel = _panel_stub(_values(auto="false"), _written())
    assert panel._current("rain_auto") == "false"
    assert panel._current("rain_enabled") == "true"


def test_on_value_does_not_write_the_config(monkeypatch):
    # Save is the ONLY writer: a slider drag must not re-trigger the eww config
    # watcher (theme regen + `eww reload`) on every tick.
    calls = []
    monkeypatch.setattr(rain_panel.subprocess, "run",
                        lambda *a, **k: calls.append(a))
    panel = _panel_stub(_values(opacity=0.9), _written())
    panel.on_value("rain_opacity", panel.scales["rain_opacity"])
    assert calls == []
    assert panel.dirty_keys() == ["rain_opacity"]


def test_on_toggle_does_not_write_the_config(monkeypatch):
    calls = []
    monkeypatch.setattr(rain_panel.subprocess, "run",
                        lambda *a, **k: calls.append(a))
    panel = _panel_stub(_values(), _written())
    panel.on_toggle("rain_auto", "false")
    assert calls == []
    assert "rain_auto" in panel.dirty_keys()


def test_dirty_hint_appears_and_clears():
    label = rain_panel.Gtk.Label.new("")
    label.set_visible(False)
    label.get_style_context().add_class("status")
    panel = _panel_stub(_values(), _written(), status_label=label)

    assert label.get_visible() is False
    panel.on_value("rain_speed", panel.scales["rain_speed"])
    assert panel.dirty_keys() == []
    assert label.get_visible() is False

    panel.scales["rain_speed"]._value = 9
    panel.on_value("rain_speed", panel.scales["rain_speed"])
    assert label.get_text() == "Save to apply"
    assert label.get_visible() is True
    assert "hint" in label.get_style_context().list_classes()


def test_error_replaces_the_dirty_hint():
    label = rain_panel.Gtk.Label.new("")
    label.set_visible(False)
    label.get_style_context().add_class("status")
    panel = _panel_stub(_values(opacity=0.9), _written(), status_label=label)
    panel.on_value("rain_opacity", panel.scales["rain_opacity"])
    assert "hint" in label.get_style_context().list_classes()

    panel.show_error("rain_count must be a whole number")
    assert label.get_text() == "rain_count must be a whole number"
    assert "hint" not in label.get_style_context().list_classes()



# --- construction: the controls must open ON the config values ---------------


def test_sync_from_config_fills_the_controls_from_the_config(monkeypatch):
    # Regression: the panel used to open at the adjustment MINIMUMS (0 drops,
    # speed 1, opacity 0), because nothing pushed the config into the widgets
    # and Save then wrote those minimums over the user's settings.
    monkeypatch.setattr(
        rain_panel, "load_settings",
        lambda: _written(count="40", speed="8", opacity="0.6"))
    panel = _panel_stub(_values(), _written())
    panel.sync_from_config()

    assert panel.spins["rain_count"].get_value() == 40.0
    assert panel.scales["rain_speed"].get_value() == 8.0
    assert panel.scales["rain_opacity"].get_value() == 0.6
    assert panel.committed["rain_count"] == "40"


def test_sync_from_config_leaves_the_panel_clean(monkeypatch):
    monkeypatch.setattr(rain_panel, "load_settings", lambda: _written())
    panel = _panel_stub(_values(), _written())
    panel.sync_from_config()
    assert panel.dirty_keys() == []


def test_sync_from_config_marks_the_toggle_buttons(monkeypatch):
    monkeypatch.setattr(
        rain_panel, "load_settings", lambda: _written(auto="false"))
    panel = _panel_stub(_values(), _written())
    panel.sync_from_config()
    ctx = panel.toggle_btns[("rain_auto", "false")].get_style_context()
    assert "on" in ctx.list_classes()
    assert "on" not in panel.toggle_btns[("rain_auto", "true")] \
        .get_style_context().list_classes()


def test_sync_from_config_survives_a_broken_value(monkeypatch):
    # A hand-edited config with a non-numeric count must not raise: the control
    # keeps what it had and Save refuses the value with an inline error.
    monkeypatch.setattr(
        rain_panel, "load_settings", lambda: _written(count="lots"))
    panel = _panel_stub(_values(), _written())
    panel.sync_from_config()
    assert panel.spins["rain_count"].get_value() == 24
    assert panel.committed["rain_count"] == "lots"
    assert panel.syncing is False


def test_sync_keeps_syncing_set_while_filling(monkeypatch):
    # The flag must be up while the widgets are being filled, so their
    # value-changed handlers do not treat the initial fill as a user edit.
    monkeypatch.setattr(rain_panel, "load_settings", lambda: _written())
    panel = _panel_stub(_values(), _written())
    seen = []

    class _SpyScale(_FakeScale):
        def set_value(self, value):
            seen.append(panel.syncing)
            super().set_value(value)

    class _SpySpin(_FakeSpin):
        def set_value(self, value):
            seen.append(panel.syncing)
            super().set_value(value)

    panel.spins["rain_count"] = _SpySpin(24)
    panel.scales["rain_speed"] = _SpyScale(5, 0)
    panel.scales["rain_opacity"] = _SpyScale(0.35, 2)
    panel.sync_from_config()
    assert seen == [True, True, True]
    assert panel.syncing is False


def test_panel_height_matches_what_rain_ctl_centers():
    # rain_ctl.py positions the window with these numbers and the panel pins a
    # MIN/MAX geometry hint to the same size: too small and the content
    # overflows the hint (measured 343 tall, the hint used to say 330).
    import rain_ctl

    assert (rain_panel.PANEL_W, rain_panel.PANEL_H) == \
        (rain_ctl.POSE_W, rain_ctl.POSE_H)
    assert rain_panel.PANEL_H >= 343
