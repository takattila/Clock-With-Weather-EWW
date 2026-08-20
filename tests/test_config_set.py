import sys

import pytest

import config_set

CONFIG = """\
# ============================================================================
# header comment
# ============================================================================

appearance: light

weather:
  city: Tatabánya
  window:
    # clock per-monitor settings
    per_monitor:
      0:
        position_x: 0
        position_y: 0
        scale: 1.0
      1:
        position_x: 0
        position_y: 0
        scale: 0.90

panel:
  enabled: true
  window:
    per_monitor:
      0:
        position_x: 0
        position_y: 0
        scale: 1.00
  gap:
    top: 5      # taskbar gap
    right: 0
    bottom: 5
    left: 0
"""


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    p.write_text(CONFIG, encoding="utf-8")
    monkeypatch.setattr(config_set, "CONFIG_FILE", str(p))
    return p


def run(args, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["config_set.py"] + args)


def test_gap_top_edit(cfg_file, monkeypatch):
    run(["--widget", "panel", "--key", "gap_top", "--value", "8"], monkeypatch)
    config_set.main()
    text = cfg_file.read_text(encoding="utf-8")
    assert "top: 8 # taskbar gap" in text
    assert "right: 0" in text


def test_gap_edit_preserves_comments(cfg_file, monkeypatch):
    before = cfg_file.read_text(encoding="utf-8")
    run(["--widget", "panel", "--key", "gap_bottom", "--value", "10"], monkeypatch)
    config_set.main()
    after = cfg_file.read_text(encoding="utf-8")
    for line in before.splitlines():
        if "#" in line:
            assert line in after


def test_gap_left_edit(cfg_file, monkeypatch):
    run(["--widget", "panel", "--key", "gap_left", "--value", "3"], monkeypatch)
    config_set.main()
    assert "left: 3" in cfg_file.read_text(encoding="utf-8")


def test_clock_scale_per_monitor(cfg_file, monkeypatch):
    run(["--widget", "clock", "--monitor", "0", "--key", "scale", "--value", "0.8"], monkeypatch)
    config_set.main()
    text = cfg_file.read_text(encoding="utf-8")
    assert "scale: 0.80" in text
    assert "position_x: 0" in text


def test_panel_position_x_per_monitor(cfg_file, monkeypatch):
    run(["--widget", "panel", "--monitor", "1", "--key", "position_x", "--value", "30"], monkeypatch)
    config_set.main()
    text = cfg_file.read_text(encoding="utf-8")
    assert "position_x: 30" in text


def test_panel_position_y_per_monitor(cfg_file, monkeypatch):
    run(["--widget", "panel", "--monitor", "0", "--key", "position_y", "--value", "15"], monkeypatch)
    config_set.main()
    assert "position_y: 15" in cfg_file.read_text(encoding="utf-8")


def test_yaml_round_trip_valid(cfg_file, monkeypatch):
    import yaml

    run(["--widget", "clock", "--monitor", "1", "--key", "scale", "--value", "0.75"], monkeypatch)
    config_set.main()
    data = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert data["weather"]["window"]["per_monitor"][1]["scale"] == 0.75


def test_monitor_required_for_position(cfg_file, monkeypatch):
    run(["--widget", "panel", "--key", "position_x", "--value", "10"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "monitor is required" in str(exc.value)


def test_gap_requires_panel(cfg_file, monkeypatch):
    run(["--widget", "clock", "--key", "gap_top", "--value", "8"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "gap keys apply to the panel only" in str(exc.value)


def test_gap_rejects_monitor(cfg_file, monkeypatch):
    run(["--widget", "panel", "--monitor", "0", "--key", "gap_top", "--value", "8"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "no --monitor" in str(exc.value)


def test_unknown_key(cfg_file, monkeypatch):
    run(["--widget", "panel", "--key", "bogus", "--value", "1"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        config_set.main()
    assert "unsupported key" in str(exc.value)


def test_print_message(cfg_file, monkeypatch, capsys):
    run(["--widget", "panel", "--key", "gap_top", "--value", "7"], monkeypatch)
    config_set.main()
    out = capsys.readouterr().out.strip()
    assert "wrote panel.gap.top=7" in out