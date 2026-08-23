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


def test_inline_fields_patch_named_theme(cfg, config_dir):
    # With `name` set, the theme provides the baseline and any inline fields
    # patch on top of it.
    theme_dir = config_dir / "assets" / "themes" / "weather" / "budapest"
    theme_dir.mkdir(parents=True)
    (theme_dir / "weather.yaml").write_text(
        "weather:\n  city: Budapest\n  lang: en\n", encoding="utf-8"
    )
    (config_dir / "config.yaml").write_text(
        "appearance: light\nweather:\n  name: budapest\n  lang: hu\n  units: metric\n"
        "  window:\n    alignment: middle_middle\n",
        encoding="utf-8",
    )
    merged = cfg.load_config()
    assert merged["weather"] == "budapest"
    assert merged["city"] == "Budapest"   # untouched baseline from the theme
    assert merged["lang"] == "hu"         # inline field wins
    assert merged["units"] == "metric"


def test_local_overrides_named_theme_fields(write_config, write_local_config, config_dir, monkeypatch):
    # The reported case: config.local.yaml patches individual values of a
    # themed city (base selects `name`, local provides inline fields).
    theme_dir = config_dir / "assets" / "themes" / "weather" / "default"
    theme_dir.mkdir(parents=True)
    (theme_dir / "weather.yaml").write_text(
        "weather:\n  city: Default City\n  language_code: en\n  lang: en\n"
        "  units: metric\n  api_url: https://api.openweathermap.org/data/2.5/weather\n",
        encoding="utf-8",
    )
    write_config(
        "appearance: light\nweather:\n  name: default\n"
        "  window:\n    alignment: middle_middle\n"
    )
    write_local_config(
        "weather:\n  city: Tatabánya\n  language_code: hu\n  lang: hu\n"
        "  units: metric\n  api_url: https://api.openweathermap.org/data/2.5/weather\n"
    )
    monkeypatch.setattr(config, "CONFIG_DIR", str(config_dir))
    merged = config.load_config()
    assert merged["city"] == "Tatabánya"
    assert merged["language_code"] == "hu"
    assert merged["lang"] == "hu"
    assert merged["units"] == "metric"


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


# ------------------------------------------------------------- axis scales

def test_no_monitor_axis_scales_default_to_one(cfg, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["config.py"])
    merged = cfg.load_config()
    assert merged["scale_x"] == 1.0
    assert merged["scale_y"] == 1.0
    assert merged["panel_scale_x"] == 1.0
    assert merged["panel_scale_y"] == 1.0


def test_axis_scales_inherit_shared_scale(cfg, monkeypatch):
    # No scale_x/scale_y keys anywhere: both axes fall back to the per-monitor
    # shared `scale` (backward compatibility with pre-axis configs).
    monkeypatch.setattr(sys, "argv", ["config.py", "--monitor", "1"])
    merged = cfg.load_config()
    assert merged["scale_x"] == 0.90
    assert merged["scale_y"] == 0.90
    assert merged["panel_scale_x"] == 0.70
    assert merged["panel_scale_y"] == 0.70


def test_axis_scale_independent_override(cfg, write_local_config, monkeypatch):
    # Width-only / height-only Move/Resize saves write just one axis key; the
    # other axis and the shared `scale` stay untouched.
    write_local_config(
        "weather:\n"
        "  window:\n"
        "    per_monitor:\n"
        "      0:\n"
        "        scale_x: 1.20\n"
        "panel:\n"
        "  window:\n"
        "    per_monitor:\n"
        "      0:\n"
        "        scale_y: 0.50\n"
    )
    monkeypatch.setattr(sys, "argv", ["config.py", "--monitor", "0"])
    merged = cfg.load_config()
    assert merged["scale"] == 0.80          # shared key untouched by the merge
    assert merged["scale_x"] == 1.20        # explicit axis wins
    assert merged["scale_y"] == 0.80        # ...the other inherits `scale`
    assert merged["panel_scale_x"] == 1.00
    assert merged["panel_scale_y"] == 0.50


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


# ------------------------------------------------------- local override layer


def test_local_overrides_scalars(cfg, write_local_config):
    write_local_config("appearance: dark\nsystem:\n  hour_format: \"12\"\n")
    merged = cfg.load_config()
    assert merged["appearance"] == "dark"
    assert merged["hour_format"] == "12"
    # untouched base keys survive the merge
    assert merged["city"] == "Tatabánya"
    assert merged["units"] == "metric"


def test_local_per_monitor_leaf_merge(cfg, write_local_config, monkeypatch):
    # Only scale is overridden for monitor 0: its base position survives.
    write_local_config(
        "weather:\n  window:\n    per_monitor:\n      0:\n        scale: 0.85\n"
        "panel:\n  window:\n    per_monitor:\n      1:\n        position_x: -7\n"
    )
    monkeypatch.setattr(sys, "argv", ["config.py", "--monitor", "0"])
    merged = cfg.load_config()
    assert merged["position_x"] == 10
    assert merged["position_y"] == 20
    assert merged["scale"] == 0.85
    monkeypatch.setattr(sys, "argv", ["config.py", "--monitor", "1"])
    merged = cfg.load_config()
    assert merged["panel_scale"] == 0.70
    assert merged["panel_position_x"] == -7
    assert merged["panel_position_y"] == 40


def test_missing_local_file_means_base(cfg):
    assert cfg.load_config()["appearance"] == "light"


def test_broken_local_yaml_falls_back_to_base(cfg, write_local_config, capsys):
    write_local_config("appearance: [unclosed\n")
    merged = cfg.load_config()
    assert merged["appearance"] == "light"
    err = capsys.readouterr().err
    assert "WARN" in err
    assert "config.local.yaml" in err