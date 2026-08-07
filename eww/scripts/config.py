#!/usr/bin/env python3
"""
Read the central YAML config (config.yaml) and the selected weather theme
(themes/weather/<name>/weather.yaml), print the merged configuration.

The eww widget cannot parse YAML directly, so the defpoll commands call this
bridge instead of reading a JSON config file.

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
        "api_key": cfg.get("api_key", ""),
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
