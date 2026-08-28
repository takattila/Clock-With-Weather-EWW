"""Pure helpers of the weather-settings GTK form (scripts/move/weather_panel.py).

The GTK window itself cannot be constructed headless; these tests cover the
logic that does not touch the display: field validation and the .api_key file
helpers (which take an explicit path, so the real git-ignored key is never
touched).
"""

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "move"))
    import weather_panel  # noqa: E402
except SystemExit:
    pytest.skip("GTK3 not available in this environment", allow_module_level=True)


@pytest.mark.parametrize(
    "key,value,expected_ok",
    [
        ("city", "Tatabánya", True),
        ("city", "  ", False),
        ("language_code", "hu", True),
        ("language_code", "", False),
        ("lang", "hu", True),
        ("lang", " ", False),
        ("units", "metric", True),
        ("units", "imperial", True),
        ("units", "kelvin", False),
        ("api_url", "https://api.openweathermap.org/data/2.5/weather", True),
        ("api_url", "http://localhost:8080", True),
        ("api_url", "ftp://host", False),
        ("api_key", "", True),  # empty -> leave the current key untouched
        ("api_key", "abcdef0123456789", True),
        ("bogus", "x", False),
    ],
)
def test_validate(key, value, expected_ok):
    ok, err = weather_panel.validate(key, value)
    assert ok is expected_ok
    assert (err is None) is expected_ok


def test_validate_error_messages():
    assert weather_panel.validate("city", "  ")[1] == "city must not be empty"
    assert weather_panel.validate("lang", "  ")[1] == "lang must not be empty"
    assert (weather_panel.validate("api_url", "x")[1]
            .startswith("api_url must start with http:// or https://"))
    assert (weather_panel.validate("units", "kelvin")[1]
            == "units must be metric or imperial")


def test_api_key_round_trip(tmp_path):
    p = tmp_path / ".api_key"
    assert weather_panel.current_api_key(str(p)) == ""
    assert weather_panel.write_api_key("  abc123  ", str(p))
    assert weather_panel.current_api_key(str(p)) == "abc123"
    assert (p.stat().st_mode & 0o777) == 0o600


def test_api_key_overwrite(tmp_path):
    p = tmp_path / ".api_key"
    assert weather_panel.write_api_key("key-one", str(p))
    assert weather_panel.write_api_key("key-two", str(p))
    assert weather_panel.current_api_key(str(p)) == "key-two"


def test_api_key_empty_content_reads_empty(tmp_path):
    p = tmp_path / ".api_key"
    p.write_bytes(b"")
    assert weather_panel.current_api_key(str(p)) == ""


# ---------------------------------------------------------------------------
# Save / Enter wiring (regression: validate() returns tuple order (ok, msg);
# the UI handlers must unpack it that way or every Save would abort)
# ---------------------------------------------------------------------------

class FakeEntry:
    def __init__(self, text):
        self.text = text
        self.selected = False

    def get_text(self):
        return self.text

    def set_text(self, t):
        self.text = t

    def select_region(self, *_):
        self.selected = True


def make_panel():
    panel = weather_panel.WeatherPanel.__new__(weather_panel.WeatherPanel)
    panel.editing = None
    panel.status_label = None
    panel.draft = {}
    panel.committed = {
        "city": "Tatabánya", "language_code": "hu", "lang": "hu",
        "units": "metric", "api_url": "https://api.example/weather",
        "api_key": "",
    }
    return panel


def fake_gtk(monkeypatch, panel):
    """Neutralize the display-touching side of _end_editing (keyboard_ungrab)."""
    import types

    monkeypatch.setattr(panel, "set_typing", lambda *a, **k: None)
    monkeypatch.setattr(
        weather_panel, "Gdk",
        types.SimpleNamespace(keyboard_ungrab=lambda *a, **k: None),
    )


def test_on_entry_activate_stores_stripped_value():
    panel = make_panel()
    entry = FakeEntry("  Budapest  ")
    panel.on_entry_activate(entry, "city")
    assert entry.text == "Budapest"
    assert panel.draft["city"] == "Budapest"


def test_on_entry_activate_rejects_empty():
    panel = make_panel()
    entry = FakeEntry("  ")
    panel.on_entry_activate(entry, "city")
    assert entry.selected is True
    assert "city" not in panel.draft


def test_on_entry_activate_empty_api_key_leaves_draft_alone():
    panel = make_panel()
    panel.on_entry_activate(FakeEntry("  "), "api_key")
    assert "api_key" not in panel.draft


def test_on_save_writes_only_changed_fields(monkeypatch):
    panel = make_panel()
    fake_gtk(monkeypatch, panel)
    panel.entries = {
        "city": FakeEntry("Budapest"), "language_code": FakeEntry("hu"),
        "lang": FakeEntry("hu"), "api_url": FakeEntry("https://api.example/weather"),
        "api_key": FakeEntry(" "),
    }
    written = []
    refreshed = []
    panel.config_set = lambda key, value: written.append((key, value)) or True
    panel.refresh_weather = lambda *a, **k: refreshed.append(a)
    monkeypatch.setattr(weather_panel, "close_popup", lambda: None)
    monkeypatch.setattr(weather_panel.Gtk, "main_quit", lambda: None)

    assert panel.on_save() is True
    assert written == [("city", "Budapest")]
    assert refreshed[0][0] == "Budapest"
    assert panel.committed["city"] == "Budapest"


def test_on_save_rejects_empty_language(monkeypatch):
    panel = make_panel()
    fake_gtk(monkeypatch, panel)
    panel.entries = {
        "city": FakeEntry("Tatabánya"), "language_code": FakeEntry(""),
        "lang": FakeEntry("hu"), "api_url": FakeEntry("https://api.example/weather"),
        "api_key": FakeEntry(" "),
    }
    panel.config_set = lambda key, value: True
    before = dict(panel.committed)
    assert panel.on_save() is False
    assert panel.committed == before


def test_on_save_invalid_api_url_aborts(monkeypatch):
    panel = make_panel()
    fake_gtk(monkeypatch, panel)
    panel.entries = {
        "city": FakeEntry("Tatabánya"), "language_code": FakeEntry("hu"),
        "lang": FakeEntry("hu"), "api_url": FakeEntry("not a url"),
        "api_key": FakeEntry(" "),
    }
    panel.config_set = lambda key, value: True
    before = dict(panel.committed)
    assert panel.on_save() is False
    assert panel.committed == before


# ---------------------------------------------------------------------------
# Weather reset: drop the LOCAL overrides so the config.yaml/theme defaults win
# (regression: previously only Save existed; Reset must not touch the window
# subtree or the .api_key file)
# ---------------------------------------------------------------------------

def test_reset_weather_overrides_drops_leaves_only(tmp_path):
    import yaml

    local = tmp_path / "config.local.yaml"
    local.write_text(
        "appearance: dark\n"
        "weather:\n"
        "  city: Tatabánya\n"
        "  language_code: hu\n"
        "  lang: hu\n"
        "  units: imperial\n"
        "  api_url: https://example.invalid\n"
        "  window:\n"
        "    per_monitor:\n"
        "      0:\n"
        "        scale: 0.85\n",
        encoding="utf-8",
    )
    assert weather_panel.reset_weather_overrides(str(tmp_path)) is True
    data = yaml.safe_load(local.read_text(encoding="utf-8"))
    assert data["appearance"] == "dark"  # unrelated keys preserved
    weather = data["weather"]
    assert "per_monitor" in weather["window"]  # window subtree preserved
    for key in ("city", "language_code", "lang", "units", "api_url"):
        assert key not in weather


def test_reset_weather_overrides_removes_empty_weather(tmp_path):
    import yaml

    local = tmp_path / "config.local.yaml"
    local.write_text("weather:\n  city: X\n", encoding="utf-8")
    assert weather_panel.reset_weather_overrides(str(tmp_path)) is True
    data = yaml.safe_load(local.read_text(encoding="utf-8"))
    assert data == {}  # empty weather subtree dropped entirely


def test_reset_weather_overrides_missing_file_is_noop(tmp_path):
    assert weather_panel.reset_weather_overrides(str(tmp_path)) is True
    assert not (tmp_path / "config.local.yaml").exists()


def test_on_reset_reloads_defaults_and_refreshes(monkeypatch):
    panel = make_panel()
    fake_gtk(monkeypatch, panel)
    panel.entries = {
        "city": FakeEntry("x"), "language_code": FakeEntry("x"),
        "lang": FakeEntry("x"), "api_url": FakeEntry("x"),
        "api_key": FakeEntry("x"),
    }
    panel.unit_btns = {}
    monkeypatch.setattr(weather_panel, "reset_weather_overrides", lambda *a, **k: True)
    monkeypatch.setattr(weather_panel, "load_weather", lambda: {
        "city": "Budapest", "language_code": "hu", "lang": "hu",
        "units": "metric", "api_url": "https://api.example/weather",
        "api_key": "",
    })
    monkeypatch.setattr(weather_panel, "current_api_key", lambda *a, **k: "env-key")
    refreshed = []
    panel.refresh_weather = lambda *a, **k: refreshed.append(a)
    monkeypatch.setattr(weather_panel, "close_popup", lambda: None)
    monkeypatch.setattr(weather_panel.Gtk, "main_quit", lambda: None)

    assert panel.on_reset() is True
    assert panel.committed["city"] == "Budapest"
    assert panel.draft["units"] == "metric"
    assert panel.entries["city"].text == "Budapest"
    assert panel.entries["api_key"].text == ""
    assert refreshed[0][0] == "Budapest"
    assert refreshed[0][3] == "https://api.example/weather"


def test_on_reset_failure_aborts_without_refresh(monkeypatch):
    panel = make_panel()
    fake_gtk(monkeypatch, panel)
    panel.editing = None
    panel.entries = {}
    panel.unit_btns = {}
    panel.refresh_weather = lambda *a, **k: pytest.fail("must not refresh")
    monkeypatch.setattr(weather_panel, "reset_weather_overrides", lambda *a, **k: False)
    monkeypatch.setattr(weather_panel, "close_popup", lambda: None)

    before = dict(panel.committed)
    assert panel.on_reset() is False
    assert panel.committed == before