#!/usr/bin/env python3
"""
Read the central YAML config (config.yaml) and the selected weather theme
(themes/weather/<name>/weather.yaml), print the merged configuration.

The eww widget cannot parse YAML directly, so the defpoll commands call this
bridge instead of reading a JSON config file.

The OpenWeatherMap API key is NOT stored in config.yaml (so it never ends up
in the repository). It is resolved in this order:
  1. the OPENWEATHER_API_KEY environment variable (same as the Conky side),
  2. a local, git-ignored file eww/.api_key (first line, chmod 600),
  3. an empty string (weather falls back to an API error message).

Usage:
  ./config.py             merged JSON (for the `config` defpoll)
  ./config.py --key NAME  a single value
                          (api_key | appearance | weather | hour_format |
                           city | language_code | lang | units)

Keys that are resolved from the selected weather theme: city, language_code,
lang, units.
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
    weather_name = cfg.get("weather", "default")
    system = cfg.get("system") or {}

    weather_path = os.path.join(CONFIG_DIR, "themes", "weather", weather_name, "weather.yaml")
    with open(weather_path, "r", encoding="utf-8") as f:
        weather = (yaml.safe_load(f) or {}).get("weather", {})

    return {
        "api_key": resolve_api_key(),
        "appearance": appearance,
        "weather": weather_name,
        "hour_format": str(system.get("hour_format", "24")),
        "city": weather.get("city", ""),
        "language_code": weather.get("language_code", ""),
        "lang": weather.get("lang", ""),
        "units": weather.get("units", ""),
    }


def main():
    merged = load_config()

    if len(sys.argv) > 1 and sys.argv[1] == "--key":
        if len(sys.argv) < 3:
            sys.exit("Usage: ./config.py [--key NAME]")
        key = sys.argv[2]
        if key not in merged:
            sys.exit("Unknown key: %s" % key)
        print(merged[key])
        return

    print(json.dumps(merged))


if __name__ == "__main__":
    main()
