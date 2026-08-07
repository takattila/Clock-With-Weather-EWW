# Conky widget with clock and current weather report

[![Version](https://img.shields.io/badge/dynamic/json.svg?label=version&url=https://api.github.com/repos/takattila/Clock-With-Weather-Conky/releases/latest&query=tag_name)](https://github.com/takattila/Clock-With-Weather-Conky/releases)
[![Wiki](https://img.shields.io/badge/wiki-docs-orange)](https://github.com/takattila/Clock-With-Weather-Conky/wiki)
[![Screenshots](https://img.shields.io/badge/view-screenshots-blue)](#screenshots)


- This widget uses [openweathermap.org](https://openweathermap.org) API, to get weather information.
- Easy to customize, supports appearance on **light** and **dark** backgrounds. *(See: [Example Themes](./themes/themes.md))*.
- Supports `12` and `24-hour` clock format.
- **System Monitor Panel**: *(See: [Screenshots](#screenshots))*
    - Real-time **CPU** and **Memory** usage charts.
    - **Network Traffic** monitoring (Download/Upload).
    - **Dynamic Scaling**: Network charts automatically adjust their scale and units (KiB/s to MiB/s) based on traffic.
    - **Auto-detection**: Automatically identifies the active network interface (NIC).
- **Multi-monitor Support**: Enhanced geometry detection for specific monitors and automatic workspace area calculation.
- **Desktop Integration**: Automatic creation of Menu icons and optional Desktop shortcuts.

<table>
    <tr>
        <th>
            Dark text with light background
        </th>
        <th>
            Light text with dark background
        </th>
    </tr>
    <tr>
        <td>
            <img src="./images/screenshots/budapest-dark-blue.png">
        </td>
        <td>
            <img src="./images/screenshots/new-york-light-bg.png">
        </td>
    </tr>
</table>

### How the Widget and Panel Work Together

This Conky widget consists of two separate but perfectly synchronized units designed to provide a unified visual experience:

1.  **Clock & Weather Widget (`cwApp.lua`)**: The core component that displays the time, date, and current weather (temperature, icon, location).
2.  **System Monitor Panel (`panelApp.lua`)**: An optional side panel that sits directly next to the clock. It handles the real-time charts (CPU, Memory, Network).

#### Key Features of the Integration:
*   **Seamless Alignment**: The two components are designed to "snap" together. When the Panel is enabled in the settings, both scripts are launched, and the Panel automatically positions itself adjacent to the clock widget, creating a single, cohesive interface.
*   **Unified Styling**: Both units share the same theme configuration (`appearance.lua`). This ensures that colors, fonts, and transparency levels are perfectly matched, whether you choose a light or dark theme.
*   **Multi-monitor Sync**: The system detects multiple displays and can launch this pair on every monitor, maintaining the same clock-panel layout across your entire workspace.
*   **Visual Hierarchy**: The panel uses alternating "light" and "dark" colors for the charts (e.g., CPU vs. Memory, Download vs. Upload). This intentional design choice provides better visual separation, making it easier to distinguish between different data streams at a glance.


- A list of successful tests can be found [here](TESTS.md).


## Get the OpenWeatherMap API key

- Go to the [openweathermap.org/users/sign_up](https://home.openweathermap.org/users/sign_up) page and create your account.
- After the registration, you should receive your API key **via e-mail**.
- For easier installation, export this API key before running the script below:

  ```bash
  export OPENWEATHER_API_KEY=<YOUR-API-KEY>
  ```

[Back to top](#conky-widget-with-clock-and-current-weather-report)

## Installation

You can install it via the command-line with either `wget` or `curl`:

... via wget:

```bash
bash -c "$(wget --no-check-certificate --no-cache --no-cookies -O- https://raw.githubusercontent.com/takattila/Clock-With-Weather-Conky/v1.0.0/scripts/install.sh)"
```

... via curl:

```bash
bash -c "$(curl -fsSLk https://raw.githubusercontent.com/takattila/Clock-With-Weather-Conky/v1.0.0/scripts/install.sh)"
```

[Back to top](#conky-widget-with-clock-and-current-weather-report)

## Start / stop the widget

### 1. Start the widget

```bash
bash ~/.conky/Clock-With-Weather-Conky/scripts/start.sh <YOUR-API-KEY>
```

[Back to top](#conky-widget-with-clock-and-current-weather-report)

### 2. Stop the widget

```bash
bash ~/.conky/Clock-With-Weather-Conky/scripts/stop.sh
```

[Back to top](#conky-widget-with-clock-and-current-weather-report)

## Change settings after installation

```bash
bash ~/.conky/Clock-With-Weather-Conky/scripts/setup.sh
```

Use the above command to **change** the following **settings**:

- city
- country code
- language code
- temperature unit:
  1. metric (for displaying Celsius)
  2. imperial (for displaying Fahrenheit)
- theme number
- hour format (12 or 24)
- window alignment and screen position
- **System Monitor**: toggle the side panel on/off
- **Shortcuts**: enable/disable Desktop icon creation

[Back to top](#conky-widget-with-clock-and-current-weather-report)

## Eww Version (Migration)

The project has been migrated to **eww** (ElKowar's Wacky Widgets).

### Prerequisites
- [eww](https://github.com/elkowar/eww) (0.4.0+)
- Python 3 with the `requests`, `psutil` and `PyYAML` libraries
- `xprop` and `xrandr` (provided by the standard X11 utilities)
- The auto-reload watcher uses the Linux **inotify** API directly via `ctypes` — no extra package is needed.

### How to use
1. Go to the `eww` directory:
   ```bash
   cd eww
   ```
2. Open `config.yaml` and set your OpenWeatherMap API key:
   ```yaml
   api_key: "YOUR_API_KEY"
   appearance: "light"     # appearance theme: themes/appearance/<name>/appearance.yaml
   weather: "default"      # weather theme:   themes/weather/<name>/weather.yaml
   system:
     hour_format: "24"     # "24" or "12"
   ```
3. Start the widget:
   ```bash
   ./start.sh
   ```
4. Stop the widget:
   ```bash
   ./stop.sh
   ```

### Configuration
All settings live in `config.yaml` in the `eww` directory:
- `appearance` — selects the appearance theme (colors, font, transparency) from `themes/appearance/<name>/appearance.yaml`.
- `weather` — selects the weather theme (city, language, temperature unit) from `themes/weather/<name>/weather.yaml`. The weather icon set follows the selected appearance theme.
- `system.hour_format` — `"24"` or `"12"` hour clock format.

### Auto-reload
While the widget is running, a lightweight **inotify-based watcher** (`scripts/watch.py`) monitors `config.yaml` and all theme YAML files. Saving any of them regenerates the theme and reloads the widget immediately — no restart needed. The watcher is event-driven, so it uses almost no CPU while idle. Its log is written to `eww/watch.log`.

### API key
The OpenWeatherMap key is **not** committed — it is read from the
`OPENWEATHER_API_KEY` environment variable or the git-ignored `eww/.api_key`
file (first line, `chmod 600`). See `eww/README.md` → "API key".

### Panel alignment
The system monitor panel automatically sizes itself to the taskbar-free work area (`_NET_WORKAREA`) for any taskbar position (top, bottom or side). The panel is inset from the taskbar and from the opposite screen edge by the **same gap** (`panel.gap`, default 16 px), so the free spacing stays symmetric no matter where the taskbar sits. The charts are laid out so the lowest section (NET UP) never extends past the panel edge.

### Changes in the eww version
- `config.json` was replaced by `config.yaml` (see above); the theme data moved to `themes/appearance/*` and `themes/weather/*` as YAML.
- The `jq` dependency was removed — the widget now reads YAML through `scripts/config.py`.
- Added `scripts/watch.py` for automatic reload on config/theme changes (log: `watch.log`).

---

## Conky Version (Original)

### With panel, theme: light-orange

![](./images/screenshots/panel-light-orange.png)

### With panel, theme: dark-orange-bg

![](./images/screenshots/panel-dark-orange-bg.png)

[Back to top](#conky-widget-with-clock-and-current-weather-report)

## Wiki

For detailed documentation, please visit the [wiki](https://github.com/takattila/Clock-With-Weather-Conky/wiki) page.

[Back to top](#conky-widget-with-clock-and-current-weather-report)

## Example Themes

Click [here to see](./themes/themes.md) the available example themes!

[Back to top](#conky-widget-with-clock-and-current-weather-report)