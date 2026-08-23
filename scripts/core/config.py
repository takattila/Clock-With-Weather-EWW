#!/usr/bin/env python3
"""
Read the central YAML config (config.yaml + config.local.yaml overrides) and
the selected weather theme (assets/themes/weather/<name>/weather.yaml), print
the merged configuration.

The eww widget cannot parse YAML directly, so the defpoll commands call this
bridge instead of reading a JSON config file.

The OpenWeatherMap API key is NOT stored in config.yaml (so it never ends up
in the repository). It is resolved in this order:
  1. the OPENWEATHER_API_KEY environment variable,
  2. a local, git-ignored file .api_key (first line, chmod 600),
  3. an empty string (weather falls back to an API error message).

The `weather` section of config.yaml accepts two forms:
  1. a theme name: weather: { name: <name>, window: {...} } loads
     assets/themes/weather/<name>/weather.yaml (the classic behavior),
  2. an inline map: weather: { city, language_code, lang, units, api_url }
     used directly (without a `name` key this is the "custom" city).

The forms also mix (handy for config.local.yaml overrides): with `name` set,
the theme provides the baseline values and any inline fields present patch
on top of it.

Usage:
  ./config.py             merged JSON (for the `config` defpoll)
  ./config.py --key NAME  a single value
                          (api_key | appearance | appearance_name | weather |
                           hour_format |
                           city | language_code | lang | units | api_url |
                           alignment | position_x | position_y | scale |
                           scale_x | scale_y |
                           panel_enabled | panel_alignment | panel_scale |
                           panel_scale_x | panel_scale_y |
                           panel_position_x | panel_position_y)
  ./config.py --key NAME --monitor N
                          resolve position_x/position_y/scale(_x/_y) for the
                          weather and panel_position_x/panel_position_y/
                          panel_scale(_x/_y) for the panel (per_monitor
                          overrides win over globals)

Keys that are resolved from the selected weather theme: city, language_code,
lang, units, api_url.

position_x / position_y / scale (+ scale_x/scale_y) / panel_scale (+ ..._x/y)
live ONLY in weather.window.per_monitor / panel.window.per_monitor (see the
comments in config.yaml): the right-click Move/Resize -> Save always writes
per-monitor entries. The panel also stores per-monitor position_x/position_y
offsets (exposed as panel_position_x / panel_position_y) added to the global
panel.gap baseline. Without --monitor those keys return the default (0/0/
1.0); with --monitor the per_monitor[N] entry is returned (or the default
when the monitor has no entry). The monitor index matches
`eww open --screen N`.

The AXIS scales (scale_x / scale_y, panel_scale_x / panel_scale_y) come from
the independent width/height resize: each axis falls back through
`scale_x -> scale -> parent value` (and the same chain for y), so configs
that only carry the classic shared `scale` keep working unchanged.
"""

import json
import os
import sys

import yaml

from config_io import load_merged

# scripts/core/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API_KEY_ENV = "OPENWEATHER_API_KEY"


def resolve_axis_scales(section, fallback_x, fallback_y):
    """(scale_x, scale_y) from a per_monitor entry / window section.

    Precedence PER AXIS: the explicit `scale_x` / `scale_y` key wins, then
    the shared `scale`, then the caller's fallback (the parent-level
    resolution). This is what makes non-proportional Move/Resize saves
    backward compatible: entries that only carry `scale` scale both axes
    with it.
    """
    def axis(explicit, shared, fallback):
        raw = explicit if explicit is not None else shared
        try:
            return float(raw) if raw is not None else float(fallback)
        except (TypeError, ValueError):
            return float(fallback)

    return (
        axis(section.get("scale_x"), section.get("scale"), fallback_x),
        axis(section.get("scale_y"), section.get("scale"), fallback_y),
    )


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
    # config.yaml deep-merged with the git-ignored config.local.yaml
    # overrides (see config_io.py).
    cfg = load_merged(CONFIG_DIR)

    appearance = cfg.get("appearance", "light")
    weather_cfg = cfg.get("weather") or {}
    system = cfg.get("system") or {}
    weather_window = weather_cfg.get("window") or {}
    panel = cfg.get("panel") or {}
    panel_window = panel.get("window") or {}

    # Layered resolution: `name` selects the theme whose values act as the
    # baseline, then every inline field present in the merged view (base or
    # local override) patches on top of it. Without `name` the inline fields
    # alone define the city (custom mode). This keeps both classic forms
    # intact while letting config.local.yaml override any single value.
    weather_name = weather_cfg.get("name", "")
    weather = {}
    if weather_name:
        # Theme baseline: assets/themes/weather/<name>/weather.yaml
        weather_path = os.path.join(CONFIG_DIR, "assets", "themes", "weather", weather_name, "weather.yaml")
        with open(weather_path, "r", encoding="utf-8") as f:
            weather = (yaml.safe_load(f) or {}).get("weather", {})
    else:
        weather_name = "custom"
    weather.update({k: v for k, v in weather_cfg.items() if k != "window"})

    weather_scale = float(weather_window.get("scale", 1.0) or 1.0)
    panel_scale = float(panel_window.get("scale", 1.0) or 1.0)
    weather_scale_x, weather_scale_y = resolve_axis_scales(weather_window, weather_scale, weather_scale)
    panel_scale_x, panel_scale_y = resolve_axis_scales(panel_window, panel_scale, panel_scale)
    weather_pm = weather_window.get("per_monitor") or {}
    panel_pm = panel_window.get("per_monitor") or {}

    merged = {
        "api_key": resolve_api_key(),
        "appearance": appearance,
        # Plain-string mirror of `appearance` for the eww labels: with a
        # custom inline map `appearance` is an OBJECT in the JSON defpoll
        # payload, which cannot be concatenated into a label string.
        "appearance_name": appearance if isinstance(appearance, str) else "custom",
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
        "scale_x": weather_scale_x,
        "scale_y": weather_scale_y,
        "weather_per_monitor": weather_pm,
        "panel_enabled": str(panel.get("enabled", True)).lower(),
        "panel_alignment": str(panel_window.get("alignment", "right")).lower(),
        "panel_scale": panel_scale,
        "panel_scale_x": panel_scale_x,
        "panel_scale_y": panel_scale_y,
        "panel_position_x": int(panel_window.get("position_x", 0)),
        "panel_position_y": int(panel_window.get("position_y", 0)),
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
            merged["scale_x"], merged["scale_y"] = resolve_axis_scales(
                wpm, merged["scale_x"], merged["scale_y"]
            )
        ppm = panel_pm.get(monitor)
        if isinstance(ppm, dict):
            merged["panel_scale"] = float(ppm.get("scale", merged["panel_scale"]))
            merged["panel_scale_x"], merged["panel_scale_y"] = resolve_axis_scales(
                ppm, merged["panel_scale_x"], merged["panel_scale_y"]
            )
            merged["panel_position_x"] = int(ppm.get("position_x", merged["panel_position_x"]))
            merged["panel_position_y"] = int(ppm.get("position_y", merged["panel_position_y"]))

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
