import sys

import pytest
import yaml

import config_set


@pytest.fixture
def local_file(tmp_path, monkeypatch):
    p = tmp_path / "config.local.yaml"
    monkeypatch.setattr(config_set, "LOCAL_CONFIG_FILE", str(p))
    return p


@pytest.fixture
def base_file(tmp_path):
    """The committed defaults; the writer must NEVER touch this file."""
    p = tmp_path / "config.yaml"
    p.write_text(
        "appearance: light\n"
        "weather:\n"
        "  window:\n"
        "    per_monitor:\n"
        "      0:\n"
        "        position_x: 0\n"
        "        position_y: 0\n"
        "        scale: 1.0\n"
        "panel:\n"
        "  gap:\n"
        "    top: 5      # taskbar gap\n"
        "    right: 0\n",
        encoding="utf-8",
    )
    return p


def run(args, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["config_set.py"] + args)


def read(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_gap_top_edit(local_file, monkeypatch):
    run(["--widget", "panel", "--key", "gap_top", "--value", "8"], monkeypatch)
    config_set.main()
    data = read(local_file)
    assert data["panel"]["gap"]["top"] == 8


def test_gap_accumulates_sides(local_file, monkeypatch):
    run(["--widget", "panel", "--key", "gap_top", "--value", "8"], monkeypatch)
    config_set.main()
    run(["--widget", "panel", "--key", "gap_left", "--value", "3"], monkeypatch)
    config_set.main()
    gap = read(local_file)["panel"]["gap"]
    assert gap == {"top": 8, "left": 3}


def test_clock_scale_per_monitor(local_file, monkeypatch):
    run(
        ["--widget", "clock", "--monitor", "0", "--key", "scale", "--value", "0.8"],
        monkeypatch,
    )
    config_set.main()
    pm = read(local_file)["weather"]["window"]["per_monitor"]
    assert pm[0]["scale"] == 0.8
    assert isinstance(pm[0]["scale"], float)


def test_axis_scales_per_monitor(local_file, monkeypatch):
    # Independent width/height scales written by the Move/Resize Save.
    run(["--widget", "clock", "--monitor", "0", "--key", "scale_x", "--value", "1.2"],
        monkeypatch)
    config_set.main()
    run(["--widget", "clock", "--monitor", "0", "--key", "scale_y", "--value", "0.8"],
        monkeypatch)
    config_set.main()
    run(["--widget", "panel", "--monitor", "1", "--key", "scale_x", "--value", "0.9"],
        monkeypatch)
    config_set.main()
    run(["--widget", "panel", "--monitor", "1", "--key", "scale_y", "--value", "1.4"],
        monkeypatch)
    config_set.main()
    clock_pm = read(local_file)["weather"]["window"]["per_monitor"][0]
    panel_pm = read(local_file)["panel"]["window"]["per_monitor"][1]
    assert clock_pm["scale_x"] == 1.2
    assert clock_pm["scale_y"] == 0.8
    assert isinstance(clock_pm["scale_x"], float)
    assert panel_pm["scale_x"] == 0.9
    assert panel_pm["scale_y"] == 1.4


def test_invalid_axis_scale(local_file, monkeypatch):
    run(["--widget", "clock", "--monitor", "0", "--key", "scale_y", "--value", "wide"],
        monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "must be a number" in str(exc.value)


def test_panel_position_per_monitor(local_file, monkeypatch):
    run(
        ["--widget", "panel", "--monitor", "1", "--key", "position_x", "--value", "30"],
        monkeypatch,
    )
    config_set.main()
    run(
        ["--widget", "panel", "--monitor", "1", "--key", "position_y", "--value", "15"],
        monkeypatch,
    )
    config_set.main()
    pm = read(local_file)["panel"]["window"]["per_monitor"]
    assert pm[1] == {"position_x": 30, "position_y": 15}


def test_position_value_coerced_to_int(local_file, monkeypatch):
    run(
        ["--widget", "clock", "--monitor", "2", "--key", "position_x", "--value", "-40"],
        monkeypatch,
    )
    config_set.main()
    value = read(local_file)["weather"]["window"]["per_monitor"][2]["position_x"]
    assert value == -40
    assert isinstance(value, int)


def test_base_config_stays_untouched(base_file, local_file, monkeypatch):
    before = base_file.read_text(encoding="utf-8")
    for args in (
        ["--widget", "clock", "--monitor", "0", "--key", "scale", "--value", "0.5"],
        ["--widget", "panel", "--key", "gap_top", "--value", "9"],
    ):
        run(args, monkeypatch)
        config_set.main()
    assert base_file.read_text(encoding="utf-8") == before
    assert read(local_file)["weather"]["window"]["per_monitor"][0]["scale"] == 0.5


def test_existing_local_keys_preserved(local_file, monkeypatch):
    local_file.write_text("appearance: dark\nsystem:\n  hour_format: \"12\"\n", encoding="utf-8")
    run(
        ["--widget", "clock", "--monitor", "0", "--key", "scale", "--value", "0.75"],
        monkeypatch,
    )
    config_set.main()
    data = read(local_file)
    assert data["appearance"] == "dark"
    assert data["system"]["hour_format"] == "12"
    assert data["weather"]["window"]["per_monitor"][0]["scale"] == 0.75


def test_yaml_round_trip_valid(local_file, monkeypatch):
    run(
        ["--widget", "clock", "--monitor", "1", "--key", "scale", "--value", "0.75"],
        monkeypatch,
    )
    config_set.main()
    data = yaml.safe_load(local_file.read_text(encoding="utf-8"))
    assert data["weather"]["window"]["per_monitor"][1]["scale"] == 0.75


def test_broken_local_file_exits(local_file, monkeypatch):
    local_file.write_text("appearance: [unclosed\n", encoding="utf-8")
    run(["--widget", "panel", "--key", "gap_top", "--value", "8"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "cannot parse" in str(exc.value)


def test_non_mapping_local_file_exits(local_file, monkeypatch):
    local_file.write_text("- just\n- a list\n", encoding="utf-8")
    run(["--widget", "panel", "--key", "gap_top", "--value", "8"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "must contain a mapping" in str(exc.value)


def test_monitor_required_for_position(local_file, monkeypatch):
    run(["--widget", "panel", "--key", "position_x", "--value", "10"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "monitor is required" in str(exc.value)


def test_gap_requires_panel(local_file, monkeypatch):
    run(["--widget", "clock", "--key", "gap_top", "--value", "8"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "gap keys apply to the panel only" in str(exc.value)


def test_gap_rejects_monitor(local_file, monkeypatch):
    run(
        ["--widget", "panel", "--monitor", "0", "--key", "gap_top", "--value", "8"],
        monkeypatch,
    )
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "no --monitor" in str(exc.value)


def test_unknown_key(local_file, monkeypatch):
    run(["--widget", "panel", "--key", "bogus", "--value", "1"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "unsupported key" in str(exc.value)


def test_invalid_scale(local_file, monkeypatch):
    run(
        ["--widget", "clock", "--monitor", "0", "--key", "scale", "--value", "big"],
        monkeypatch,
    )
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "must be a number" in str(exc.value)


def test_print_message(local_file, monkeypatch, capsys):
    run(["--widget", "panel", "--key", "gap_top", "--value", "7"], monkeypatch)
    config_set.main()
    out = capsys.readouterr().out.strip()
    assert "wrote panel.gap.top=7" in out
    assert "config.local.yaml" in out


# ---------------------------------------------------------------------------
# Global keys (context-menu quick toggles; no --widget / no --monitor)
# ---------------------------------------------------------------------------

def test_hour_format_stored_as_string(local_file, monkeypatch):
    run(["--key", "hour_format", "--value", "12"], monkeypatch)
    config_set.main()
    value = read(local_file)["system"]["hour_format"]
    assert value == "12"
    assert isinstance(value, str)


def test_hour_format_invalid_value(local_file, monkeypatch):
    run(["--key", "hour_format", "--value", "13"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "must be 12 or 24" in str(exc.value)


def test_global_key_rejects_monitor(local_file, monkeypatch):
    run(["--key", "hour_format", "--value", "12", "--monitor", "0"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "--monitor must not be used" in str(exc.value)


def test_units_metric_imperial(local_file, monkeypatch):
    run(["--key", "units", "--value", "imperial"], monkeypatch)
    config_set.main()
    assert read(local_file)["weather"]["units"] == "imperial"


def test_units_invalid_value(local_file, monkeypatch):
    run(["--key", "units", "--value", "kelvin"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "metric or imperial" in str(exc.value)


def test_panel_enabled_bool_coercion(local_file, monkeypatch):
    run(["--key", "panel_enabled", "--value", "false"], monkeypatch)
    config_set.main()
    assert read(local_file)["panel"]["enabled"] is False
    run(["--key", "panel_enabled", "--value", "true"], monkeypatch)
    config_set.main()
    assert read(local_file)["panel"]["enabled"] is True


def test_panel_enabled_invalid_value(local_file, monkeypatch):
    run(["--key", "panel_enabled", "--value", "maybe"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "must be true or false" in str(exc.value)


def test_panel_alignment_flip(local_file, monkeypatch):
    run(["--key", "panel_alignment", "--value", "left"], monkeypatch)
    config_set.main()
    alignment = read(local_file)["panel"]["window"]["alignment"]
    assert alignment == "left"
    assert isinstance(alignment, str)


def test_panel_alignment_invalid_value(local_file, monkeypatch):
    run(["--key", "panel_alignment", "--value", "up"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "right or left" in str(exc.value)


def test_progress_mode_stored_as_string(local_file, monkeypatch):
    run(["--key", "progress_mode", "--value", "progress"], monkeypatch)
    config_set.main()
    mode = read(local_file)["system"]["progress_mode"]
    assert mode == "progress"
    assert isinstance(mode, str)


def test_progress_mode_accepts_text(local_file, monkeypatch):
    run(["--key", "progress_mode", "--value", "text"], monkeypatch)
    config_set.main()
    assert read(local_file)["system"]["progress_mode"] == "text"


def test_progress_mode_invalid_value(local_file, monkeypatch):
    run(["--key", "progress_mode", "--value", "bar-chart"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "must be text or progress" in str(exc.value)


def test_progress_mode_rejects_monitor(local_file, monkeypatch):
    run(["--key", "progress_mode", "--value", "progress", "--monitor", "0"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "--monitor must not be used" in str(exc.value)


def test_appearance_known_theme(local_file, tmp_path, monkeypatch):
    themes = tmp_path / "themes"
    themes.mkdir()
    (themes / "dark").mkdir()
    (themes / "light").mkdir()
    monkeypatch.setattr(config_set, "APPEARANCE_THEMES_DIR", str(themes))
    run(["--key", "appearance", "--value", "dark"], monkeypatch)
    config_set.main()
    assert read(local_file)["appearance"] == "dark"


def test_appearance_unknown_theme_exits(local_file, tmp_path, monkeypatch):
    themes = tmp_path / "themes"
    themes.mkdir()
    monkeypatch.setattr(config_set, "APPEARANCE_THEMES_DIR", str(themes))
    run(["--key", "appearance", "--value", "nope"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "unknown appearance theme" in str(exc.value)


def test_widget_scoped_key_requires_widget(local_file, monkeypatch):
    run(["--key", "scale", "--value", "0.8"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "--widget is required" in str(exc.value)


def test_global_keys_preserve_local_tree(local_file, monkeypatch):
    local_file.write_text(
        "appearance: light\nsystem:\n  hour_format: \"24\"\n",
        encoding="utf-8",
    )
    for args in (
        ["--key", "hour_format", "--value", "12"],
        ["--key", "panel_enabled", "--value", "false"],
    ):
        run(args, monkeypatch)
        config_set.main()
    data = read(local_file)
    assert data["appearance"] == "light"
    assert data["system"]["hour_format"] == "12"
    assert data["panel"]["enabled"] is False


# ---------------------------------------------------------------------------
# Weather settings (scripts/move/weather_panel.py): global weather.* keys
# ---------------------------------------------------------------------------

def test_weather_city_stored_as_string(local_file, monkeypatch):
    run(["--key", "city", "--value", "Tatabánya"], monkeypatch)
    config_set.main()
    value = read(local_file)["weather"]["city"]
    assert value == "Tatabánya"
    assert isinstance(value, str)


def test_weather_language_fields(local_file, monkeypatch):
    run(["--key", "language_code", "--value", "hu"], monkeypatch)
    config_set.main()
    run(["--key", "lang", "--value", "hu"], monkeypatch)
    config_set.main()
    weather = read(local_file)["weather"]
    assert weather["language_code"] == "hu"
    assert weather["lang"] == "hu"


def test_weather_api_url_stored(local_file, monkeypatch):
    url = "https://api.openweathermap.org/data/2.5/weather"
    run(["--key", "api_url", "--value", url], monkeypatch)
    config_set.main()
    saved = read(local_file)["weather"]["api_url"]
    assert saved == url
    assert isinstance(saved, str)


def test_weather_city_empty_exits(local_file, monkeypatch):
    run(["--key", "city", "--value", "   "], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "must not be empty" in str(exc.value)


def test_weather_lang_empty_exits(local_file, monkeypatch):
    run(["--key", "lang", "--value", ""], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "must not be empty" in str(exc.value)


def test_weather_api_url_bad_scheme_exits(local_file, monkeypatch):
    run(["--key", "api_url", "--value", "ftp://host"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "http:// or https://" in str(exc.value)


def test_weather_key_rejects_monitor(local_file, monkeypatch):
    run(["--key", "city", "--value", "Tatabánya", "--monitor", "0"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "--monitor must not be used" in str(exc.value)
