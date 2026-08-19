# Clock-With-Weather-EWW

[![Version](https://img.shields.io/badge/dynamic/json.svg?label=version&url=https://api.github.com/repos/takattila/Clock-With-Weather-EWW/releases/latest&query=tag_name)](https://github.com/takattila/Clock-With-Weather-EWW/releases)
[![Wiki](https://img.shields.io/badge/wiki-docs-orange)](https://github.com/takattila/Clock-With-Weather-EWW/wiki)
[![Screenshots](https://img.shields.io/badge/view-screenshots-blue)](#screenshots)


- This widget uses [openweathermap.org](https://openweathermap.org) API, to get weather information.
- Easy to customize, supports appearance on **light** and **dark** backgrounds. *(See: [Example Themes](./themes/themes.md))*.
- Supports `12` and `24-hour` clock format.
- **Wayland native**: runs via **EWW** (`ElKowar's Wacky Widgets`) + GTK layer-shell; it also works on X11.
- **Clock & Weather widget**: date, year, hour/minute/second, AM/PM (12 h), HDD/CPU/RAM/SWAP table, weather icon, city, temperature, description and MIN/MAX/Feels-like stats.
- **Dynamic width**: the clock's window width hugs its content (ends right after the city name), so the Move/Resize rectangle and the widget background always match the visible widget.
- **System Monitor Panel**: *(See: [Screenshots](#screenshots))*
    - Real-time **CPU** and **Memory** usage charts.
    - **Network Traffic** monitoring (Download/Upload).
    - **Dynamic Scaling**: Network charts automatically adjust their scale and units (KiB/s to MiB/s) based on traffic.
    - **Auto-detection**: Automatically identifies the active network interface (NIC).
    - Can be **disabled** entirely (`panel.enabled: false`).
- **Interactive context menu**: right-click the clock or the panel to **Move**, **Resize**, **Reset** or open the **About** dialog (see the "Interactive features" section).
- **Move / Resize with live preview**: a GTK control panel (arrow buttons, ± zoom, Save/Cancel) plus keyboard control (arrow keys, `+`/`-`, `Enter`, `Esc`); the clock and panel can also be dragged/resized directly with the mouse on a full-screen overlay rectangle.
- **About dialog**: a GTK window showing the repository, runtime and configuration info, centered on the screen and draggable; opens the project page with one click.
- **Scaling**: both widgets have an overall zoom factor (`scale`), from 0.3x to 1.5x, set globally or **per monitor**.
- **Multi-monitor**: one clock and one panel instance per monitor, each with its own position/scale; display hotplug and resolution changes are detected and the layout is re-applied automatically.
- **Hot reload**: an inotify watcher regenerates the theme and reloads EWW the moment `config.yaml` / a theme YAML is saved — no restart needed.
- **Taskbar-aware panel**: the panel aligns to the taskbar with per-side gaps (`panel.gap`), defaulting to the same spacing on every side.
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

This EWW widget consists of two separate but perfectly synchronized windows designed to provide a unified visual experience:

1.  **Clock & Weather Widget (`main_window`)**: The core component that displays the time, date, and current weather (temperature, icon, location).
2.  **System Monitor Panel (`panel_window`)**: An optional side panel that sits directly next to the clock. It handles the real-time charts (CPU, Memory, Network).

#### Key Features of the Integration:
*   **Seamless Alignment**: The two components are designed to "snap" together. When the Panel is enabled in the settings, both windows are opened, and the Panel automatically positions itself adjacent to the clock widget, creating a single, cohesive interface.
*   **Unified Styling**: Both units share the same theme configuration (`config.yaml` → `themes/appearance/<name>/appearance.yaml`). This ensures that colors, fonts, and transparency levels are perfectly matched, whether you choose a light or dark theme.
*   **Taskbar-aware Panel**: The panel is aligned to the taskbar with per-side gaps (taskbar side, opposite screen edge and lateral edge), configurable via `panel.gap` — a single number or a per-side map (see the "Panel alignment" section).
*   **Configurable panel side**: `panel.window.alignment: right|left` places the full-height panel flush to the right or left screen edge, independent of the taskbar (see the "Panel alignment" section).
*   **Visual Hierarchy**: The panel uses alternating "light" and "dark" colors for the charts (e.g., CPU vs. Memory, Download vs. Upload). This intentional design choice provides better visual separation, making it easier to distinguish between different data streams at a glance.

### Interactive features (context menu, Move / Resize, About)

Both the clock and the panel have a **context menu** — right-click them and choose:

| Menu item | What it does |
|---|---|
| **Move** | Opens a full-screen transparent overlay with a rectangle around the widget plus a GTK control panel. Move the widget with the mouse (drag the rectangle), the arrow buttons, or the **arrow keys**. Save or Cancel when done. |
| **Resize** | The same overlay and panel, but the rectangle's corners/size are changed instead. Use the mouse, the **`+` / `-`** buttons (zoom, 0.3x–1.5x) or the keyboard (**`+`**/**`-`**). Enter saves, Esc cancels. |
| **Reset** | Restores the factory defaults directly in `config.yaml` (clock: position 0/0, scale 1.0; panel: 16 px gaps on every side, scale 1.0). |
| **About** | Opens the About dialog (below). |

The saved position/scale are written to `config.yaml` and picked up instantly by the config watcher (the widget re-lays-out itself).

**Keyboard control** during a Move/Resize session is handled by an invisible evdev daemon (`scripts/input_daemon.py`): it reads the physical keyboard through `/dev/input/event*`, creates **no window**, and only acts while a session is active (a small `generated/input_session.json` file). Keys: arrows = move, `+`/`-` = zoom in/out, `Enter` = save, `Esc` = cancel. Clicking outside the rectangle also cancels.

**About dialog** (`scripts/about_win.py`, GTK): a draggable window centered on the screen with three sections:

- **Repository** — URL, branch/tag, commit, date, author, commit message (from `git`).
- **Runtime** — compositor (Wayland/X11), monitor resolution, EWW and Python versions, OS.
- **Configuration** — appearance, icon set, corner radius, font, city, units, language, hour format, scale.

An **Open repository** button (`xdg-open`) and a **Close** button sit at the bottom. The dialog closes by clicking the Close button, pressing `Esc`, or clicking anywhere outside it.


- A list of successful tests can be found [here](TESTS.md).


## Get the OpenWeatherMap API key

- Go to the [openweathermap.org/users/sign_up](https://home.openweathermap.org/users/sign_up) page and create your account.
- After the registration, you should receive your API key **via e-mail**.
- For easier installation, export this API key before running the script below:

  ```bash
  export OPENWEATHER_API_KEY=<YOUR-API-KEY>
  ```

[Back to top](#clock-with-weather-eww)

## Installation

You can install it via the command-line with either `wget` or `curl` (root
privileges are needed; the script asks for them):

... via wget:

```bash
bash -c "$(wget --no-check-certificate --no-cache --no-cookies -O- https://raw.githubusercontent.com/takattila/Clock-With-Weather-Conky/refs/heads/feature/wayland/scripts/install.sh)"
```

... via curl:

```bash
bash -c "$(curl -fsSLk https://raw.githubusercontent.com/takattila/Clock-With-Weather-Conky/refs/heads/feature/wayland/scripts/install.sh)"
```

[Back to top](#clock-with-weather-eww)

## Start / stop the widget

### 1. Start the widget

```bash
bash ~/.conky/Clock-With-Weather-EWW/scripts/start.sh
```

[Back to top](#clock-with-weather-eww)

### 2. Stop the widget

```bash
bash ~/.conky/Clock-With-Weather-EWW/scripts/stop.sh
```

[Back to top](#clock-with-weather-eww)

## Change settings after installation

```bash
bash ~/.conky/Clock-With-Weather-EWW/scripts/setup.sh
```

Use the above command to **change** the following **settings**:

- OpenWeatherMap API key
- appearance theme
- weather theme (city)
- hour format (12 or 24)
- **Shortcuts**: enable/disable Desktop icon creation

The panel side (`panel.window.alignment`) and the clock position
(`weather.window.*`) are edited directly in `config.yaml` (see the
"Configuration" section) — the running widget picks both up automatically
via the config watcher.

[Back to top](#clock-with-weather-eww)

## Screenshots

### With panel, theme: light-orange

![](./images/screenshots/panel-light-orange.png)

### With panel, theme: dark-orange-bg

![](./images/screenshots/panel-dark-orange-bg.png)

[Back to top](#clock-with-weather-eww)

---

# Detailed documentation

The installer is **cross-distro**: it detects the package manager (`yum`,
`apt`, `pacman`, `zypper`, `dnf`) and installs **eww + all of its
dependencies**:

| Distribution | eww install path |
|---|---|
| Arch Linux / EndeavourOS / Manjaro | `pacman -S eww` (official `extra` repo); falls back to a source build if unavailable |
| Debian / Ubuntu | **source build** (`cargo`, rustup) + `libgtk-3-dev`, `libgtk-layer-shell-dev`, `pango`, `gdk-pixbuf2`, `cairo`, `glib2`, `libdbusmenu-gtk3` dev packages |
| Fedora / RHEL / CentOS (`dnf`/`yum`) | **source build** + `gtk3-devel`, `gtk-layer-shell-devel`, `pango-devel`, `gdk-pixbuf2-devel`, `cairo-devel`, `glib2-devel`, `libdbusmenu-gtk3-devel` |
| openSUSE (`zypper`) | **source build** + the equivalent `-devel` packages |

The source build automatically picks the Wayland feature when
`WAYLAND_DISPLAY` is set, otherwise the X11 feature.

What the installer does, in order:

1. base tools (`curl`, `gawk`, `git`),
2. eww runtime dependencies (Python modules, `xprop`, `xrandr`, Noto fonts),
3. `eww` itself (package or source build),
4. clones the repo to `~/.conky/` and checks out the latest release tag,
5. installs the `NotoSans-Regular.ttf` font,
6. asks for the **OpenWeatherMap API key** → saves it to `.api_key`
   (chmod 600, git-ignored),
7. creates the **desktop / menu icons** (menu always, desktop optionally),
8. starts the widgets (`scripts/start.sh`): daemon + both windows + watcher.

> Tip: to skip the interactive API-key prompt, export
> `DEFAULT_OPENWEATHER_API_KEY` before running the script (or set the
> `OPENWEATHER_API_KEY` variable, see the "API key" section).

---

## 1. Dependencies

### Required

| Dependency | Minimum / tested version | Role |
|---|---|---|
| `eww` | 0.5.0+ (tested: `0.5.0 d87c2fd`) | renders the windows and the widget tree |
| `python3` | 3.14+ (tested: 3.14.6) | the data-producing scripts |
| `python3-requests` | 2.x (tested: 2.34.2) | OpenWeatherMap API call (`weather.py`) |
| `python3-psutil` | 5.x–7.x (tested: 7.2.2) | CPU/RAM/SWAP/HDD/network (`system.py`, `panel.py`) |
| `python3-yaml` | 6.x (tested: 6.0.3) | reading the YAML configs (`config.py`, `theme.py`) |
| `python3-pillow` | 10.x (tested: 10.2.0) | tinting the icon PNGs to `icon.color` (`theme.py`) |
| `xprop` | any | reading `_NET_WORKAREA` (panel height) |
| `xrandr` | any | resolution / workarea fallback |
| `Noto Sans` font | any | the only font family used |

The four Python packages (`requests`, `psutil`, `PyYAML`, `pillow`) are also
listed in [`requirements.txt`](requirements.txt) for manual / pip-based setups
(`pip install -r requirements.txt`); the installer (`install.sh`) installs
them from your distribution's repositories instead.

### For testing / development

| Dependency | Role |
|---|---|
| `spectacle` | taking screenshots for verification |
| `PIL` (pillow) | image measurement / comparison (development aid) — also a runtime dependency (see above) |

### X11 support

This widget runs natively on **Wayland** (EWW + GTK layer-shell) and also on
**X11**. On X11 (e.g. Linux Mint / Cinnamon) there is no layer-shell, so EWW
places the windows with absolute screen coordinates:

- the installer builds EWW with the X11 feature when `WAYLAND_DISPLAY` is not
  set (see the dependency table above),
- `start.sh` skips the KDE Plasma check (there is no `plasmashell` on X11),
- `workarea.py` detects the compositor and computes the panel offsets for
  absolute X11 coordinates (see the "Panel alignment" section).

The separate **`Clock-With-Weather-Conky`** project (a repository for the X11
Conky widget) is **not** required by this widget: the theme settings are stored
under `themes/` as **YAML**, so this widget works fully standalone.

---

## 2. Version-change risks ("widget does not start")

The widget is sensitive to the following version changes. Most failure symptoms
are silent (empty window, missing text), so after starting **always check the
terminal** (`eww` logs `defpoll` errors).

| What changes | Symptom | Cause / solution |
|---|---|---|
| **`eww` major version** (0.5 → 0.6/1.0) | the widget does not start, or CSS fails to load | The `yuck` syntax (`:geometry`, `defpoll`, `:anchor`) and the SCSS `@import` API may change. Check the [eww releases](https://github.com/elkowar/eww/releases). |
| **`eww` minor/patch** | rarely a problem | If the `daemon` reports `Error while forwarding command` after the config loads, it can happen, but the widget still renders — don't panic, measure the screen. |
| **`python` major** (3.x → 4.x) | `system.py` / `panel.py` errors | Depends on the availability of `psutil`/`requests` binary wheels. |
| **`psutil` major** | `panel.py` produces no JSON | API differences (e.g. `cpu_times` order, `net_io_counters`). Symptom: the panel window is empty. |
| **`PyYAML` missing** | the clock and the `defpoll`s are empty | `config.py` / `theme.py` read the YAML configs via `import yaml` — without it nothing is read. Symptom: the whole widget is empty. |
| **`xprop` missing** | the panel height is wrong | `workarea.py` falls into the fallback chain (`xrandr` → 1080). |
| **`Noto Sans` not installed** | everything is shifted | `fc-match "Noto Sans"` → must be `NotoSans-Regular.ttf`. To switch fonts, change `$font-face` in `eww.theme.scss` and recalibrate the margins. |
| **KDE/kwin version** | window offset | The window is centered relative to the workarea (see the "Window geometry" section). |

**Most important rule:** every value in the `defpoll`s is the output of an
external command (`date`, `./scripts/*.py`). If any command fails or is
missing, an **empty/raw `null`** value goes into the widget, which is often an
"invisible" error.

---

## 3. Starting the widget

```bash
cd ~/.conky/Clock-With-Weather-EWW
./scripts/start.sh
```

`scripts/start.sh` does the following:

0. **KDE Plasma check** *(Wayland only)* — on a Wayland session, if
   `plasmashell` is not running, `scripts/setup-test-env.sh restore` restores
   the normal desktop (and restarts plasmashell); if there is no backup, it
   starts `plasmashell` directly so the widget can be displayed. On X11 (e.g.
   Linux Mint/Cinnamon) this step is skipped, because the widget does not need a
   desktop shell there.
1. **`theme.py`** — generates the `eww.theme.scss` and `eww.theme.json` files
   from the `appearance` field of `config.yaml` +
   `themes/appearance/<name>/appearance.yaml` (colors, font, icon set,
   background transparency).
2. **`monitors.py`** — detects the compositor (Wayland/X11) and enumerates the
   connected monitors (`index` matches `eww open --screen N`).
3. **`workarea.py --per-monitor`** — for every monitor reads `_NET_WORKAREA`,
   the `panel.gap` value(s) and the `panel.window.alignment` (passed as
   `--align left|right`) from `config.yaml`, then computes the `panel_window`
   geometry (anchor + offsets + height) so the panel is inset from the taskbar,
   from the opposite screen edge and from the lateral screen edge by the
   configured per-side gap (Req 2), and flush to the left or right screen edge
   when `panel.window.alignment` is set. The offsets are interpreted for the
   current compositor (Wayland layer-shell vs. absolute X11 coordinates, see
   the "Panel alignment" section). The layout is written to `.layout.json`.
4. **`widget_rect.py`** — computes the clock widget's top-left position and its
   **natural** (unscaled, dynamic) size for every monitor from
   `weather.window.alignment` / `position_x/y` / `scale` (resolved per monitor).
5. Kills the old daemon: `eww --config . kill`
6. `eww --config . daemon`, then for **every** monitor
   `eww --config . open --id main_<N> --screen N main_window` (+
   `--id panel_<N> --screen N panel_window` when `panel.enabled: true`).
7. Starts the background helpers: the inotify **config watcher**
   (`watch.py`), the **monitor hotplug watcher** (`monitor_watch.py`) and the
   invisible **keyboard daemon** (`input_daemon.py`, via passwordless sudo).

### Stopping

```bash
cd ~/.conky/Clock-With-Weather-EWW
./scripts/stop.sh
```

`scripts/stop.sh` stops the eww daemon for this config directory
(`eww --config . kill`), which closes both windows. Manually that is:

```bash
eww --config ~/.conky/Clock-With-Weather-EWW kill
```

### Setup and desktop / menu icons

The installer and the widget create **`.desktop` launchers**:

- `start-clock-with-weather-eww.desktop` — starts the widget (`scripts/start.sh`).
- `setup-clock-with-weather-eww.desktop` — opens the setup (terminal).

**Menu icons** are always created in `~/.local/share/applications/`; **desktop
icons** are created optionally (the installer/setup asks whether you want
them) in `$(xdg-user-dir DESKTOP)`.

To change the settings (API key, appearance theme, weather theme, hour format)
and (re)create the icons interactively:

```bash
cd ~/.conky/Clock-With-Weather-EWW
./scripts/setup.sh
```

### Configuration (`config.yaml`)

The central config is **YAML**. It selects the active appearance and weather
theme; the city, language and unit settings come from the selected
`themes/weather/<name>/weather.yaml` (or, alternatively, can be defined
**inline** in `config.yaml`, see below):

```yaml
# config.yaml
appearance: light       # theme name -> themes/appearance/<name>/appearance.yaml,
                        # or a custom map (see the "Configuration" section)
weather:
  name: default         # -> themes/weather/<name>/weather.yaml,
                        # or omit it and define the city settings inline (see below)
  window:               # clock widget position (same names as a Conky alignment)
    alignment: middle_middle   # top_left..middle_middle
    position_x: 0       # pixel offset of the clock from its anchor
    position_y: 0
    scale: 1.0          # overall zoom factor of the clock (0.3..1.5)
    per_monitor: {}     # per-monitor overrides, e.g. {0: {scale: 1.0}, 1: {position_x: -40, scale: 0.8}}
system:
  hour_format: "24"     # "24" | "12"
  corner_radius: 20     # bg corner rounding (px) for BOTH widgets; 0 = square
panel:
  enabled: true         # start the system monitor panel? true | false
  window:
    alignment: right    # right (default) | left — full-height panel side
    position_x: 0       # pixel offset of the panel from its anchor
    position_y: 0
    scale: 1.0          # overall zoom factor of the panel (0.3..1.5)
    per_monitor: {}     # per-monitor overrides (same syntax as above)
  gap: 16               # spacing (px) on every side of the panel (Req 2)
                        # or per-side: gap: { top: 16, right: 16, bottom: 16, left: 16 }
                        # or block style (braces/commas optional):
                        # gap:
                        #   top: 16
                        #   right: 16
                        #   bottom: 16
                        #   left: 16
```

The `weather` field accepts **two forms**:

1. **A theme name (`weather.name`)** — loads
   `themes/weather/<name>/weather.yaml` (the classic behavior).
2. **An inline map (no `name` key)** — the weather details are defined right in
   `config.yaml` (a `name` key, if present, takes precedence):

   ```yaml
   weather:
     city: Tatabánya
     language_code: hu
     lang: hu
     units: metric
     api_url: https://api.openweathermap.org/data/2.5/weather
     window:               # optional clock position
       alignment: middle_middle
       position_x: 0
       position_y: 0
       scale: 1.0
       per_monitor: {}
   ```

The `appearance` field accepts **two forms**:

1. **A theme name (string)** — `appearance: light` selects
   `themes/appearance/<name>/appearance.yaml` (the classic behavior).
2. **A custom map (object)** — an inline appearance definition with the same
   structure as `themes/appearance/<name>/appearance.yaml`:

   ```yaml
   appearance:
     theme: light        # image folder under images/theme/<theme>/ (light | dark)
     icon:
       set: dovora        # icon set under images/theme/<theme>/weather/<set>/
       color:             # icon color (tinted into the PNGs) - optional;
         light: '#ffffff' #   used when theme is "light"
         dark: '#9e9e9e'  #   used when theme is "dark"
                          #   (omit -> icons keep their original color)
       transparency:      # icon opacity (applied to all icons)
         light: 1.0       #   when theme is "light"
         dark: 0.5        #   when theme is "dark"
     font:
       face: Noto Sans
       color:
         light: '#ffffff' # main text color ($color-light)
         dark: '#9e9e9e'  # secondary text color ($color-dark)
       transparency:
         light: 1.0       # opacity of $color-light texts
         dark: 1.0        # opacity of $color-dark texts
     background:
       transparency: 0.0  # 0.0 = fully transparent, 1.0 = opaque
       color: '#000000'
   ```

| Field | Values | Effect |
|---|---|---|
| `appearance` | `light`, `dark`, `light-bg`, ... **or** a custom map | a theme name selects `themes/appearance/<name>/appearance.yaml`; a custom map (`theme`, `icon`, `font`, `background`) defines the appearance inline (see the "Configuration" section) |
| `appearance.icon.color` | `#rrggbb` (light / dark) | icon color, tinted into the PNGs by `theme.py` (Pillow); `light` is used when the theme is "light", `dark` when "dark". Omit it to keep the icons' original colors |
| `weather.name` | `default`, `budapest`, `berlin`, ... | which `themes/weather/<name>/weather.yaml` provides `city`, `lang`, `units`. Omit the `name` key to define the city settings **inline** in `config.yaml` (`city`, `language_code`, `lang`, `units`, `api_url`); a `name` key, if present, takes precedence |
| `weather.city` | string | inline-mode only: the city queried from the weather API (when `weather.name` is absent) |
| `weather.language_code` | `hu`, `en`, `fr`, ... | inline-mode only: the country code of the city (when `weather.name` is absent) |
| `weather.lang` | `hu`, `en`, `fr`, ... | inline-mode only: the display language of the weather description (when `weather.name` is absent) |
| `weather.units` | `metric` / `imperial` | inline-mode only: °C vs °F (when `weather.name` is absent) |
| `weather.api_url` | URL | the OpenWeatherMap API endpoint used by `weather.py` (default: `https://api.openweathermap.org/data/2.5/weather`); taken from the selected theme or the inline map |
| `weather.window.alignment` | `top_left`, `top_right`, `top_middle`, `bottom_left`, `bottom_right`, `bottom_middle`, `middle_left`, `middle_right`, `middle_middle` | where the clock widget is anchored |
| `weather.window.position_x` / `position_y` | integer px | pixel offset of the clock widget from its anchor |
| `weather.window.scale` | float, 0.3–1.5 | overall zoom factor of the clock (window size AND content); e.g. `0.8` smaller, `1.5` bigger |
| `weather.window.per_monitor` | map of monitor index → overrides | per-monitor values for `position_x` / `position_y` / `scale` / `alignment`; monitor index matches `eww open --screen N` (see `scripts/monitors.py`). Any listed key overrides the global value on that monitor only |
| `system.hour_format` | `24` / `12` | the `%H` / `%I` format of the `defpoll hour`; `12` also shows a small AM/PM indicator under the hour digits |
| `system.corner_radius` | integer px | bg corner rounding for both the clock/weather widget and the panel; `0` = sharp corners (written by `theme.py` into `$bg-radius` in `eww.theme.scss`) |
| `panel.enabled` | `true` / `false` | whether the system monitor panel is started (default `true`) |
| `panel.window.alignment` | `right` / `left` | the horizontal side of the full-height panel (see the "Panel alignment" section) |
| `panel.window.position_x` / `position_y` | integer px | pixel offset of the panel widget from its anchor |
| `panel.window.scale` | float, 0.3–1.5 | overall zoom factor of the panel (window size AND content) |
| `panel.window.per_monitor` | map of monitor index → overrides | per-monitor values for `scale` (and the other `panel.window.*` keys), same syntax as `weather.window.per_monitor` |
| `panel.gap` | integer px **or** map | the panel is inset from the taskbar, the opposite screen edge and the lateral edge. A single number applies to every side; a map `{ top:, right:, bottom:, left: }` sets each side independently (braces/commas optional, e.g. block style) — missing sides default to 16 px. See the "Panel alignment" section |

The widget itself cannot parse YAML, so `scripts/config.py` reads `config.yaml`
+ the selected weather theme and prints the merged values as JSON for the
`defpoll`s (see the "Structure" section). `jq` is no longer needed.

#### API key (`OPENWEATHER_API_KEY`)

The OpenWeatherMap key is **not** stored in `config.yaml` (that file is part of
the repository). It is resolved by `scripts/config.py` in this order:

1. the `OPENWEATHER_API_KEY` environment variable,
2. a local, git-ignored file **`.api_key`** (first line, `chmod 600`),
3. empty string → the weather block falls back to an API error message.

Setup (pick one):

```sh
# Option A - environment variable (start.sh also exports it if set)
export OPENWEATHER_API_KEY="your_key"

# Option B - local file (git-ignored), recommended for desktop use
printf 'your_key\n' > .api_key && chmod 600 .api_key
```

`start.sh` exports `OPENWEATHER_API_KEY` from `.api_key` before starting the
daemon, so both ways work no matter how the widget is launched. Editing
`.api_key` takes effect within the next weather poll (10 minutes).

---

## 4. Setting up a test environment (KDE Plasma)

> This section is **KDE/Plasma-specific** and only applies to a Wayland session.
> On X11 (Linux Mint / Cinnamon) there is no `plasmashell`; `start.sh` skips the
> Plasma check there and the widget renders on the normal desktop.

Measuring the widget needs a clean desktop: no other widgets, no desktop icons,
and a plain background (solid color or a wallpaper image). For this, the
**`scripts/setup-test-env.sh`** script:

```bash
cd ~/.conky/Clock-With-Weather-EWW

./scripts/setup-test-env.sh hide                # test mode: widgets + icons hidden, solid background
./scripts/setup-test-env.sh hide "#112233"      # ... with a custom background color
./scripts/setup-test-env.sh hide "/path/to/wallpaper.jpg"  # ... with a wallpaper image
./scripts/setup-test-env.sh status              # current state
./scripts/setup-test-env.sh restore             # restore the normal desktop
```

### What does the script do?

1. **Backup** — saves the current
   `~/.config/plasma-org.kde.plasma.desktop-appletsrc` to
   `...desktop-appletsrc.backup` (only once, to preserve the normal desktop).
2. **Test background** — either generates a solid PNG with PIL
   (`~/.config/eww-test-background.png`, default color `#2d3034`, overridable
   with the `EWW_TEST_BG_COLOR` environment variable), or copies a given
   wallpaper image (e.g. `hide /path/to/wallpaper.jpg`) to
   `~/.config/eww-test-background.png`.
3. **File swap** — with plasmashell stopped, a test copy of the appletsrc is
   written. The desktop containments are detected **dynamically** (by
   `plugin` + `formfactor`), nothing is hardcoded. The script removes the
   desktop widget applets and the icon positions, sets the test wallpaper and
   drops the `[ScreenMapping]` section; video-wallpaper sections are also
   removed. **The panel/taskbar is kept untouched**, so the workarea stays
   realistic.
4. **Restart** — plasmashell is restarted with `nohup plasmashell & disown`
   so the changes take effect.

### Notes (verified facts, 2026-08-05)

- Plasma version: **6.7.3**; use `kquitapp6` (`kquitapp5` does not exist).
- In the `plasma-org.kde.plasma.desktop-appletsrc` file, widgets do **not**
  have a separate visibility state — they either exist or not. The script
  therefore **swaps whole files** instead of editing the running config in
  place: the test copy is written while plasmashell is stopped, so the daemon
  cannot overwrite the changes when it exits.
- The desktop containments are **not** at fixed indices (on this machine the
  panel is `[Containments][23]`, the desktops `[Containments][43]`/`[51]`),
  so the script detects them dynamically instead of assuming
  `[Containments][1]`.
- `plasmashell` runs **manually** (the `plasma-plasmashell.service` is
  inactive), so the script restarts it with `nohup plasmashell & disown`.
- For manual testing you can also use the KDE Session (System Settings →
  Users → Create Session): a clean environment without file moving.

---

## 5. Structure — what does what

### `eww.yuck` — the widget tree and the data sources

The file has three main parts:

1. **`defpoll` blocks** — the data. Every `defpoll` runs a shell command at
   intervals and loads its output into the widget:

   | defpoll | Interval | Command |
   |---|---|---|
   | `hour` | 1s | `date +%H` (or `%I` in 12-hour format) |
   | `minutes` | 1s | `date +:%M` |
   | `seconds` | 1s | `date +%S` |
   | `meridiem` | 1s | `date +%p` (AM/PM, shown only in 12-hour format) |
   | `date_year` | 1m | `date +%Y.` |
   | `date_day` | 1m | `date "+| %B %d. | %A"` (en_US locale) |
   | `system_info` | 5s | `./scripts/system.py` (JSON) |
   | `weather_info` | 10m | `./scripts/weather.py <key> <city> <lang> <units> <api_url>` (JSON) |
   | `panel` | 1s | `./scripts/panel.py` (JSON + SVG charts) |
   | `config` | 5s | `./scripts/config.py` (merged JSON from `config.yaml` + weather theme) |
   | `theme` | 5s | `cat eww.theme.json` |

   > The `config`/`theme` intervals are only a **safety net**. In normal use the
   > inotify watcher (`scripts/watch.py`, see below) reloads the widget the
   > moment a YAML config/theme file is saved, so changes appear instantly.

2. **`defwidget widget_clock_weather`** — the main window. An `overlay` +
   dynamic sizer (natural width ends at the city name, 247 px high) in which
   every element is **absolutely positioned** with `margin-left`/`margin-top`
   (see the "Modifying how elements are displayed" section). The elements:
   year/date, hour/minute/second, AM/PM chip (12 h), HDD/RAM, CPU/SWAP, divider
   line, weather icon, city, temperature, description, MIN/MAX/Feels. The whole
   content is wrapped in an eww `transform` widget so `scale` zooms it.

3. **`defwidget widget_panel`** — the system monitor panel. Four
   `panel-section`s: `CPU`, `MEMORY`, `NET DOWN`, `NET UP`. Each has a title
   (`panel-title`), a status text (`panel-status`) and an SVG chart
   (`panel-chart`).

4. **`defwindow` blocks** — `main_window` (dynamic width, 247 high, centered)
   and `panel_window` (250 wide, full height, top-right/left). Both are opened
   **once per monitor** (`--id main_<N>` / `panel_<N>`, `--screen N`) with the
   per-monitor position and scale passed as arguments; their content is scaled
   with an eww `transform` widget. `ctx_menu` (the right-click menu) and
   `dismiss_overlay` (a transparent full-monitor surface that closes the
   popups when clicked outside) handle the interactive popups. On X11 the
   `main_window_x11` / `panel_window_x11` variants are used (`:stacking
   "background"`, WM-managed) so the widgets stay below opened windows.

### `scripts/` — data-producing Python and shell scripts

| Script | Output | Responsibility |
|---|---|---|
| `system.py` | `{hdd, ram, cpu, swap}` | `psutil`/`shutil`-based system info, dynamic `format_bytes` (B/KB/MB/GB/TB) |
| `weather.py` | OpenWeatherMap JSON + `temp_fmt`, `unit_symbol`, `icon_path` | API call to the configured `api_url`, rounding, °C/°F |
| `panel.py` | `{cpu_file, mem_file, down_file, up_file, cpu_txt, ...}` | generating chart SVGs (`charts/*.svg`, 100-point scrolling history), active NIC detection |
| `theme.py` | `eww.theme.scss` + `eww.theme.json` + tinted icons under `generated/icons/` | `config.yaml` `appearance` + `themes/appearance/<name>/appearance.yaml` → EWW theme (+ PNG tinting when `appearance.icon.color` is set) |
| `config.py` | merged JSON / `--key` values | `config.yaml` + `themes/weather/<name>/weather.yaml` **or** the inline `weather` map → the values for the `defpoll`s; `--key <name> [--monitor N]` returns a single (per-monitor resolved) value |
| `monitors.py` | JSON (compositor + monitor list) | compositor detection (Wayland/X11) and per-compositor monitor enumeration (index matches `eww open --screen N`); `--signature` mode reads only `/sys/class/drm` for the hotplug watcher |
| `widget_rect.py` | JSON (clock/panel rect + natural size) | computing the top-left position and the **natural** (unscaled, dynamic) size of the clock/panel window from `config.yaml` (`alignment` / `position_x/y` / `scale`, resolved per monitor) — the same anchor math eww uses |
| `workarea.py` | JSON (screen / workarea / taskbar position / panel geometry / compositor) | reading `_NET_WORKAREA`, detecting the taskbar position and computing the symmetric panel geometry (`panel.gap`), honoring the `--align left|right` panel side (`panel.window.alignment`); detects Wayland vs. X11 and computes the offsets for the current compositor; `--per-monitor` lays out every monitor, `--gaps-for-rect` inverts a dragged rectangle back into per-side gaps; also logs a human-readable summary to stderr |
| `watch.py` | — | inotify-based watcher (`ctypes`, no packages, ~0 CPU idle): on a change to `config.yaml` / theme YAMLs it runs `theme.py` + `eww reload`; a `config.yaml` change also triggers `start.sh --relayout`; log: `watch.log`, PID: `watch.pid` |
| `monitor_watch.py` | — | monitor hotplug watcher: detects connect/disconnect / resolution changes (udev DRM events + a cheap `/sys/class/drm` signature poll) and re-lays-out the windows via `start.sh --relayout`; log: `monitor_watch.log`, PID: `monitor_watch.pid` |
| `start.sh` | — | starting the widget (section 3): Plasma check (Wayland only), theme generation, display-env bootstrap, per-monitor layout (`layout_windows`), `eww daemon` + opening windows, watcher + monitor watcher + input daemon start. `--relayout` recomputes the layout without restarting the daemon |
| `stop.sh` | — | stopping the widget (`eww --config . kill`) |
| `install.sh` | — | cross-distro installer (the "Installation" section): installs eww + all dependencies, clones the repo, sets the API key, creates the desktop/menu icons and starts the widgets |
| `setup.sh` | — | interactive setup: API key, appearance/weather theme, hour format, and desktop/menu icon creation (menu icons always, desktop icons optional) |
| `setup-test-env.sh` | — | enabling/disabling and restoring the KDE Plasma test environment (section 4): `hide` / `status` / `restore` |
| `git-filter-repo.sh` | — | vendored **git-filter-repo** (history-rewriting tool, Python 3 + git only): used to scrub secrets (e.g. an API key) from the whole git history — run `git-filter-repo.sh --replace-text <rules>` in the repo root |

### `scripts/` — interactive popups (context menu, Move/Resize, About)

These GTK/popup helpers implement the interactive features (see the
"Interactive features" section at the top):

| Script | Responsibility |
|---|---|
| `ctx.py` | opens the context menu (`ctx_menu` + the `dismiss_overlay`) at the right-click point; `--widget clock\|panel --monitor N` |
| `close_popup.py` | closes every popup (context menu, dismiss overlay) and clears the session |
| `move.py` | Move/Resize session launcher: reads the current widget rect (`widget_rect.py`), sets the overlay preview values, opens the rectangle overlay + the control panel and activates the keyboard daemon |
| `move_rect.py` | the full-screen transparent **rectangle overlay** (GTK): drag/resize the widget with the mouse; writes the preview to `eww update move_*`; watching the session file to quit |
| `move_panel.py` | the draggable GTK **control panel** with Move/Resize buttons |
| `move_ctl.py` | handles the control-panel buttons / keyboard actions: `left/right/up/down`, `zoom_in/zoom_out` (0.3–1.5x), `reset`, `save`, `cancel`; Save/Reset write the result to `config.yaml` via `config_set.py` |
| `config_set.py` | writes a single `config.yaml` value (used by Save/Reset; supports per-monitor overrides) |
| `input_daemon.py` | the invisible evdev keyboard daemon (arrow keys / `+`/`-` / `Enter` / `Esc`) — reads `/dev/input/event*` directly, creates **no window** |
| `session.py` | shared session-file helpers (`generated/input_session.json`) for the popup / Move-Resize daemon, plus lazy daemon (re)start |
| `about.py` | collects the git repository metadata (`--open` spawns the About window + the dismiss overlay + the ESC session) |
| `about_win.py` | the GTK **About dialog** (draggable, centered on screen): Repository / Runtime / Configuration sections, Open-repository + Close buttons |

### `charts/` — generated SVGs

`panel.py` writes a new, timestamped SVG to `charts/` on every poll
(`cpu_00042.svg`, ...), and returns the file name in the `defpoll panel` JSON.
Old ones are deleted automatically (it keeps 3 per type). **Don't commit
them** — gitignored (`.gitignore`).

### `images/`, `themes/`, `fonts/`

The widget directory is **self-contained** (ready for a standalone repo): the
shared assets are stored here.

- `images/theme/<theme>/elements/` — line, location icon, thermometer, arrows.
- `images/theme/<theme>/weather/<icon-set>/` — weather icons
  (`01d.png`, `02d`, ...). `theme.py` takes the `icon_set` from the selected
  `themes/appearance/<name>/appearance.yaml`.
- `generated/icons/<theme>/...` — **git-ignored** working copies of the active
  theme's icons. `theme.py` recreates this folder on every start / config
  change: with `appearance.icon.color` set the PNGs are tinted (Pillow), without
  it they are copied unchanged. `eww.yuck` always loads the icons from here.
- `themes/appearance/<name>/appearance.yaml` — the appearance themes.
- `themes/weather/<name>/weather.yaml` — the city settings (`city`,
  `language_code`, `lang`, `units`).
- `fonts/NotoSans-Regular.ttf` — the bundled font (the GTK side still needs the
  `Noto Sans` family installed via fontconfig).

---

## 6. Modifying how elements are displayed (EWW CSS)

All formatting is in the **`eww.scss`** file. `eww.yuck` only provides the
**structure** and the **data**; size, color and position are all CSS.

### The basic rule: the positioning method

- Every element in the widget overlay is **absolutely positioned**:
  `margin-left` = X coordinate, `margin-top` = Y coordinate (positions the top
  of the label). The overlay is `main_w x main_h`: the height is the natural
  content height (247 px at scale 1.0), the **width is dynamic** — it hugs the
  content and ends right after the city name.

Example, the temperature label:

```scss
.temp-label {
  font-size: 44px;
  font-weight: bold;
  color: $color-light;
  margin-left: 460px;   /* X position */
  margin-top: 128px;    /* Y position */
}
```

### The more important CSS classes and what they affect

| Class | What it displays | Main rules |
|---|---|---|
| `.year-label`, `.date-label` | year, date line | `font-size: 20px`, `margin-left/margin-top` |
| `.hour-label`, `.minutes-label` | hour / minute | `font-size: 145px`, `margin-left: 10/170`, `margin-top: 18` |
| `.seconds-label` | seconds | `font-size: 20px`, `margin-left: 370`, `margin-top: 154` |
| `.meridiem-label` / `.meridiem-chip` | AM/PM indicator (12h only) | `font-size: 28px`, bold, bottom of the hour digits; the 54x32 chip masks the digit with the widget background color — always at least 60% opaque, so it stays visible even when the widget background is fully transparent (`background.transparency: 0.0`) |
| `.hdd-label`...`.swap-value` | system info table (HDD/CPU \| values \| RAM/SWAP \| values), 2 lines | 4 columns (x=16/65/219/276, ~15px equal gaps, last gap to the divider), rows y=178/192 (14px pitch, like the weather rows); `.sys-label` (light, bold 15px) + `.sys-value` (dark 15px) |
| `.divider` | divider line | `margin-left: 414`, `margin-top: 14` |
| `.weather-icon` | weather icon | 64x64 via `:image-width/height` (in the yuck) |
| `.city-icon`, `.city-label` | city icon + name | icon 20x20; label `font-size: 30px`, bold |
| `.temp-icon`, `.temp-label` | thermometer + temperature | icon 32x32; label `font-size: 44px`, bold |
| `.details-icon`, `.details-label` | description | 15px |
| `.stat-min/...` | MIN/MAX/Feels | 15px |
| `.panel-title`, `.panel-status`, `.panel-chart` | panel parts | 22px bold / 14px / SVG |

### Theme variables (`eww.theme.scss`)

The file is generated by `theme.py`; don't edit it by hand (it is lost on the
next start). Instead modify `themes/appearance/<name>/appearance.yaml` or use a
custom `appearance` map in `config.yaml`:

```scss
$theme: "light";
$icon-set: "dovora";
$icon-alpha: 1.0;          // icon.transparency (light|dark, chosen by $theme)
$font-face: "Noto Sans";
$color-light: #ffffff;
$color-dark: #9e9e9e;
$color-light-alpha: 1.0;   // font.transparency.light -> rgba($color-light, ...)
$color-dark-alpha: 1.0;    // font.transparency.dark -> rgba($color-dark, ...)
$bg-color: #000000;
$bg-alpha: 0.0;
```

The **icon color** is not a CSS variable: `appearance.icon.color` (light|dark,
chosen by `$theme`) is applied to the PNGs themselves by `theme.py` (see the
"Configuration" section), so the tint works even though GTK/EWW cannot colorize
images at render time.

### Resize / reposition workflow

1. Modify `eww.scss`.
2. `eww --config ~/.conky/Clock-With-Weather-EWW reload`
3. `spectacle -b -o shot.png` and image measurement (PIL) — see the "Verified
   facts" section.

### Panel alignment (taskbar-relative, "Req 2")

The `panel_window` (250 px wide) is positioned so that the free spacing on the
**taskbar side, the opposite screen edge and the lateral screen edge** is the
configured gap on every side. `start.sh` computes this from `_NET_WORKAREA` +
`config.yaml → panel.gap` (default **16 px**; either a single number or a
per-side map `{ top:, right:, bottom:, left: }`) via `scripts/workarea.py`,
which detects the taskbar position and applies the per-side gaps:

| Taskbar position | Panel geometry result |
|---|---|
| **top** | `anchor "top right"`, `x = gap.right`, `y = gap.top` (Wayland) / `y = workarea.y + (frame − workarea.y) + gap.top` (X11), height `= screen_h − frame − gap.top − gap.bottom` → gaps from the taskbar frame, the screen bottom and the right edge |
| **bottom** | `anchor "bottom right"`, `x = gap.right`, bottom margin `= gap.bottom`, height `= panel_bottom − (workarea.y + gap.top)` → gaps from the taskbar frame, the screen top and the right edge |
| **right** | the panel moves to the **left** edge: `anchor "top left"`, `x = gap.left`, `y = gap.top`, height `= workarea_h − gap.top − gap.bottom` |
| **left** | `anchor "top right"`, `x = gap.right`, `y = gap.top`, height `= workarea_h − gap.top − gap.bottom` |
| **none** | `anchor "top right"`, flush right (`x = gap.right`), inset top/bottom by `gap.top` / `gap.bottom`, height `= screen_h − gap.top − gap.bottom` |

Setting `config.yaml → panel.window.alignment: left` overrides the horizontal
side of the full-height panel: the anchor becomes `"top left"` / `"bottom left"`
and `x = gap.left`, while the height and the taskbar top/bottom gaps stay as
computed above. `right` (the default) keeps the taskbar-derived behavior.

On KDE/Plasma the top/bottom gap is measured from the taskbar's **visual frame**
(the KWin scripting API is queried for it), because a floating taskbar's frame
extends beyond the exclusive zone reported by `_NET_WORKAREA`; without the frame
info the geometry falls back to the exclusive zone.

> Note: the `:x`/`:y` offsets are interpreted differently depending on the
> compositor, and `workarea.py` (via `detect_compositor()`) switches between the
> two modes automatically:
>
> - **Wayland** (KDE/gtk layer-shell): the offsets are relative to the
>   **workarea** top-left — the taskbar is an exclusive zone that shifts the
>   window — so for a top taskbar `:y` equals the gap itself.
> - **X11** (e.g. Linux Mint/Cinnamon): there is no layer-shell, so EWW places
>   the window with **absolute screen coordinates**. The top-anchored `:y` must
>   include the taskbar height (`workarea.y + gap`); the bottom case is measured
>   from the screen bottom and the horizontal offsets from the screen's right
>   edge, so they already match the workarea.

The values are written into the `panel_window` geometry of `eww.yuck` at
startup (the committed `config.yaml` on this machine: 30 px top taskbar,
`panel.gap` `{ top: 5, bottom: 10, left: 0, right: 0 }` → on the 1920×1080
screen `:y "35px" :height "1035px"` with `panel.window.alignment: right`).
`PANEL_HEIGHT` is exported for
`panel.py` so the chart heights match the inset panel.

---

## 7. Verified facts and measurement method

### Window geometry

- Widget size: **dynamic width × 247** (the width ends after the city name;
  with the default city it is ~745 px) at scale 1.0. On the screen the window
  origin is **x=587, y=392**.
- This is the result of KDE workarea centering (plain center alignment would
  be y415, because EWW aligns to the taskbar-free area). **Don't change the
  anchoring** — this is expected behavior.

### Transparent background

- The `main-container` / `panel-container` has
  `background-color: rgba($bg-color, $bg-alpha)` — with `bg-alpha: 0.0` it is
  fully transparent, only the texts/icons are visible.
- Against the solid background of the test environment (section 4) the
  black/white texts can be verified.

### Screenshot measurement (development aid)

```bash
export DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000
eww --config ~/.conky/Clock-With-Weather-EWW reload
sleep 2
spectacle -b -o /tmp/opencode/shots/check.png
```

Then with PIL the coordinates of the colored pixels (the widget origin is
x=587, y=392):

```python
from PIL import Image
import numpy as np
a = np.array(Image.open('/tmp/opencode/shots/check.png').convert('RGB')).astype(int)
lum = a.mean(axis=2)
sub = lum[392:392+250, 587:587+745]  # widget area
m = sub > 100
rows = np.where(m.sum(axis=1) > 0)[0]
cols = np.where(m.sum(axis=0) > 0)[0]
print('content:', (rows.min()+392, rows.max()+392), (cols.min()+587, cols.max()+587))
```

---

## 8. Known issues / TODO (from the port process)

- [ ] The `stats-row` did not render earlier (diagnostic debugging finished
      with the layout commits; in `eww.yuck` the stats elements are in
      `widget_clock_weather`, see `stat-min/max/feels`).
- [ ] The `time-row` label-clipping bug (t13/t14/t15 matrix) **solved** in the
      current layout; the `eww.scss` margins described here are the final,
      verified values.

---

## Related documentation

- The X11-specific widget `Clock-With-Weather-Conky` (this widget's
  non-Wayland counterpart) lives in its own repository.
