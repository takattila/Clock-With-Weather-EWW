#!/usr/bin/env python3
"""
Read the central YAML config (config.yaml) and the selected weather theme
(themes/weather/<name>/weather.yaml), print the merged configuration.

The eww widget cannot parse YAML directly, so the defpoll commands call this
bridge instead of reading a JSON config file.

The OpenWeatherMap API key is NOT stored in config.yaml (so it never ends up
in the repository). It is resolved in this order:
  1. the OPENWEATHER_API_KEY environment variable,
  2. a local, git-ignored file .api_key (first line, chmod 600),
  3. an empty string (weather falls back to an API error message).

The `weather` section of config.yaml accepts two forms:
  1. a theme name: weather: { name: <name>, window: {...} } loads
     themes/weather/<name>/weather.yaml (the classic behavior),
  2. an inline map: weather: { city, language_code, lang, units, api_url }
     used directly (a `name` key takes precedence over inline fields).

Usage:
  ./config.py             merged JSON (for the `config` defpoll)
  ./config.py --key NAME  a single value
                          (api_key | appearance | weather | hour_format |
                           city | language_code | lang | units | api_url |
                           alignment | position_x | position_y | scale |
                           panel_enabled | panel_alignment | panel_scale)
  ./config.py --key NAME --monitor N
                          resolve position_x/position_y/scale/panel_scale for
                          monitor N (per_monitor overrides win over globals)

Keys that are resolved from the selected weather theme: city, language_code,
lang, units, api_url.

The per-monitor override map lives in config.yaml as
weather.window.per_monitor / panel.window.per_monitor (see the comments
there). The monitor index matches `eww open --screen N`.
"""

import json
import os
import sys

import yaml

CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
API_KEY_ENV = "OPENWEATHER_API_KEY"


def resolve_api_key():
    """Return the API key from the env var, the git-ignored .api_key file, or ''."""
    env_key = os.environ.get(API_KEY_ENV, "").strip()
    if env_key:
        return env_key
    try:
        with open(os.path.join(CONFIG_DIR, ".api_key"), "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    return ""


def load_config():
    with open(os.path.join(CONFIG_DIR, "config.yaml"), "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    appearance = cfg.get("appearance", "light")
    weather_cfg = cfg.get("weather") or {}
    system = cfg.get("system") or {}
    weather_window = weather_cfg.get("window") or {}
    panel = cfg.get("panel") or {}
    panel_window = panel.get("window") or {}

    weather_name = weather_cfg.get("name", "")
    if weather_name:
        # Theme mode: load themes/weather/<name>/weather.yaml
        weather_path = os.path.join(CONFIG_DIR, "themes", "weather", weather_name, "weather.yaml")
        with open(weather_path, "r", encoding="utf-8") as f:
            weather = (yaml.safe_load(f) or {}).get("weather", {})
    else:
        # Inline mode: use the weather map directly (minus the window key)
        weather_name = "custom"
        weather = {k: v for k, v in weather_cfg.items() if k != "window"}

    weather_scale = float(weather_window.get("scale", 1.0) or 1.0)
    panel_scale = float(panel_window.get("scale", 1.0) or 1.0)
    weather_pm = weather_window.get("per_monitor") or {}
    panel_pm = panel_window.get("per_monitor") or {}

    merged = {
        "api_key": resolve_api_key(),
        "appearance": appearance,
        "weather": weather_name,
        "hour_format": str(system.get("hour_format", "24")),
        "city": weather.get("city", ""),
        "language_code": weather.get("language_code", ""),
        "lang": weather.get("lang", ""),
        "units": weather.get("units", ""),
        "api_url": weather.get("api_url", "https://api.openweathermap.org/data/2.5/weather"),
        "alignment": weather_window.get("alignment", "middle_middle"),
        "position_x": int(weather_window.get("position_x", 0)),
        "position_y": int(weather_window.get("position_y", 0)),
        "scale": weather_scale,
        "weather_per_monitor": weather_pm,
        "panel_enabled": str(panel.get("enabled", True)).lower(),
        "panel_alignment": str(panel_window.get("alignment", "right")).lower(),
        "panel_scale": panel_scale,
        "panel_per_monitor": panel_pm,
    }

    monitor = None
    if "--monitor" in sys.argv:
        idx = sys.argv.index("--monitor")
        if idx + 1 < len(sys.argv):
            monitor = int(sys.argv[idx + 1])
    if monitor is not None:
        wpm = weather_pm.get(monitor)
        if isinstance(wpm, dict):
            merged["position_x"] = int(wpm.get("position_x", merged["position_x"]))
            merged["position_y"] = int(wpm.get("position_y", merged["position_y"]))
            merged["scale"] = float(wpm.get("scale", merged["scale"]))
        ppm = panel_pm.get(monitor)
        if isinstance(ppm, dict):
            merged["panel_scale"] = float(ppm.get("scale", merged["panel_scale"]))

    return merged


def main():
    merged = load_config()

    if len(sys.argv) > 1 and sys.argv[1] == "--key":
        if len(sys.argv) < 3:
            sys.exit("Usage: ./config.py [--key NAME]")
        key = sys.argv[2]
        if key not in merged:
            sys.exit("Unknown key: %s" % key)
        value = merged[key]
        if key == "appearance" and isinstance(value, dict):
            print("custom")
            return
        print(value)
        return

    print(json.dumps(merged))


if __name__ == "__main__":
    main()
