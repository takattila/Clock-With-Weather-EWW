#!/usr/bin/env python3
import sys
import os
import requests
import json
from datetime import datetime

# Usage: ./weather.py <api_key> <city> <lang> <units>

def get_weather():
    if len(sys.argv) < 5:
        print(json.dumps({"error": "Missing arguments"}))
        return

    api_key = sys.argv[1]
    city = sys.argv[2]
    lang = sys.argv[3]
    units = sys.argv[4]

    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&lang={lang}&units={units}&appid={api_key}"
    
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
            
            # Unit string
            unit_symbol = "°C" if units == "metric" else "°F"
            data['unit_symbol'] = unit_symbol
            
            print(json.dumps(data))
        else:
            print(json.dumps({"error": data.get("message", "API Error")}))
            
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    get_weather()
