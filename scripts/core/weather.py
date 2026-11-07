#!/usr/bin/env python3
import sys
import os
import requests
import json
from datetime import datetime

# Usage: ./weather.py <api_key> <city> <lang> <units> <api_url>

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
CACHE_FILE = os.path.join(CONFIG_DIR, "generated", "weather_cache.json")

# OpenWeatherMap `weather[0].main` values that mean precipitation is falling.
# `main` is always a SINGLE token from OWM's fixed vocabulary ("Rain",
# "Thunderstorm", "Clear", ...), so a case-insensitive membership test is exact
# - not a substring match. Deliberately EXCLUDED: Mist / Fog / Haze / Smoke /
# Dust / Sand / Ash (airborne particles, nothing falls out of the sky) and
# Tornado (the widget's own icon already reports it, and the rain layer is a
# cosmetic effect - it should not claim it is raining).
PRECIPITATION = ("rain", "drizzle", "thunderstorm", "squall", "shower", "snow")


def write_cache(data):
    """Mirror the successful payload to generated/weather_cache.json.

    The eww `weather_info` defpoll only re-runs every 10 minutes, so the
    raindrop layer (scripts/core/rain.py) reads this file instead of polling
    the API itself. Never fatal: a failed write just means the rain stays on
    its last known state until the next successful fetch.
    """
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def get_weather():
    if len(sys.argv) < 6:
        print(json.dumps({"error": "Missing arguments"}))
        return

    api_key = sys.argv[1]
    city = sys.argv[2]
    lang = sys.argv[3]
    units = sys.argv[4]
    api_url = sys.argv[5].rstrip("/") or "https://api.openweathermap.org/data/2.5/weather"

    url = f"{api_url}?q={city}&lang={lang}&units={units}&appid={api_key}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if response.status_code == 200:
            # Add some formatted values
            data['temp_fmt'] = f"{round(data['main']['temp'])}"
            data['temp_min_fmt'] = f"{round(data['main']['temp_min'])}"
            data['temp_max_fmt'] = f"{round(data['main']['temp_max'])}"
            data['feels_like_fmt'] = f"{round(data['main']['feels_like'])}"
            data['icon_path'] = data['weather'][0]['icon']

            # Precipitation flag for the raindrop layer (v5.0.0). `condition`
            # is the raw `weather[0].main` (e.g. "Clear", "Rain", "Snow") and
            # `is_raining` is True only while something actually falls, so the
            # "auto" mode can leave a dry sky dry. Defaults to False on any
            # unexpected shape rather than raising.
            try:
                condition = str(data['weather'][0].get('main', '')).strip()
            except (KeyError, IndexError, TypeError):
                condition = ''
            data['condition'] = condition
            data['is_raining'] = condition.lower() in PRECIPITATION

            # Unit string
            unit_symbol = "°C" if units == "metric" else "°F"
            data['unit_symbol'] = unit_symbol
            
            print(json.dumps(data))
            write_cache(data)
        else:
            print(json.dumps({"error": data.get("message", "API Error")}))
            
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    get_weather()
