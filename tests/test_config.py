import sys

import pytest

import config


@pytest.fixture
def cfg(write_config, monkeypatch, config_dir):
    write_config()
    monkeypatch.setattr(config, "CONFIG_DIR", str(config_dir))
    return config


def test_defaults(cfg):
    merged = cfg.load_config()
    assert merged["appearance"] == "light"
    assert merged["hour_format"] == "24"
    assert merged["weather"] == "custom"
    assert merged["city"] == "Tatabánya"
    assert merged["language_code"] == "hu"
    assert merged["units"] == "metric"
    assert merged["alignment"] == "middle_middle"
    assert merged["panel_enabled"] == "true"
    assert merged["panel_alignment"] == "right"
    assert merged["scale"] == 1.0
    assert merged["panel_scale"] == 1.0
    assert merged["panel_position_x"] == 0
    assert merged["panel_position_y"] == 0


def test_weather_theme_name_mode(cfg, config_dir, monkeypatch):
    theme_dir = config_dir / "assets" / "themes" / "weather" / "budapest"
    theme_dir.mkdir(parents=True)
    (theme_dir / "weather.yaml").write_text(
        "weather:\n  city: Budapest\n  language_code: hu\n  lang: hu\n"
        "  units: metric\n  api_url: https://api.openweathermap.org/data/2.5/weather\n",
        encoding="utf-8",
    )
    (config_dir / "config.yaml").write_text(
        "appearance: light\nweather:\n  name: budapest\n  window:\n"
        "    alignment: middle_middle\n",
        encoding="utf-8",
    )
    merged = cfg.load_config()
    assert merged["weather"] == "budapest"
    assert merged["city"] == "Budapest"


def test_inline_weather_name_wins(write_config, config_dir, monkeypatch):
    theme_dir = config_dir / "assets" / "themes" / "weather" / "budapest"
    theme_dir.mkdir(parents=True)
    (theme_dir / "weather.yaml").write_text(
        "weather:\n  city: Budapest\n", encoding="utf-8"
    )
    write_config(
        "appearance: light\nweather:\n  name: budapest\n  city: Inline\n"
        "  window:\n    alignment: middle_middle\n"
    )
    monkeypatch.setattr(config, "CONFIG_DIR", str(config_dir))
    merged = config.load_config()
    assert merged["weather"] == "budapest"
    assert merged["city"] == "Budapest"


def test_per_monitor_resolution(cfg, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["config.py", "--monitor", "1"])
    merged = cfg.load_config()
    assert merged["position_x"] == 0
    assert merged["position_y"] == 0
    assert merged["scale"] == 0.90
    assert merged["panel_scale"] == 0.70
    assert merged["panel_position_x"] == 30
    assert merged["panel_position_y"] == 40


def test_per_monitor_fallback(cfg, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["config.py", "--monitor", "9"])
    merged = cfg.load_config()
    assert merged["position_x"] == 0
    assert merged["position_y"] == 0
    assert merged["scale"] == 1.0
    assert merged["panel_scale"] == 1.0
    assert merged["panel_position_x"] == 0
    assert merged["panel_position_y"] == 0


def test_no_monitor_returns_defaults(cfg, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["config.py"])
    merged = cfg.load_config()
    assert merged["position_x"] == 0
    assert merged["position_y"] == 0
    assert merged["scale"] == 1.0
    assert merged["panel_position_x"] == 0
    assert merged["panel_position_y"] == 0
    assert merged["panel_scale"] == 1.0


def test_resolve_api_key_env_wins(cfg, monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "env-key")
    assert cfg.resolve_api_key() == "env-key"


def test_resolve_api_key_file(cfg, config_dir, monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    (config_dir / ".api_key").write_text("file-key\n", encoding="utf-8")
    assert cfg.resolve_api_key() == "file-key"


def test_resolve_api_key_empty(cfg, monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    assert cfg.resolve_api_key() == ""


def test_main_key_prints(cfg, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["config.py", "--key", "city"])
    cfg.main()
    out = capsys.readouterr().out.strip()
    assert out == "Tatabánya"


def test_main_key_appearance_dict_prints_custom(cfg, monkeypatch, capsys, config_dir):
    (config_dir / "config.yaml").write_text(
        "appearance:\n  theme: light\n  icon:\n    set: dovora\n"
        "weather:\n  city: X\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["config.py", "--key", "appearance"])
    cfg.main()
    out = capsys.readouterr().out.strip()
    assert out == "custom"


def test_main_unknown_key(cfg, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["config.py", "--key", "nope"])
    with pytest.raises(SystemExit):
        cfg.main()


def test_main_full_json(cfg, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["config.py"])
    cfg.main()
    import json

    data = json.loads(capsys.readouterr().out)
    assert data["city"] == "Tatabánya"
    assert data["api_key"] == ""