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
