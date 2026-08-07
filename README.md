# Clock-With-Weather-EWW

[![Version](https://img.shields.io/badge/dynamic/json.svg?label=version&url=https://api.github.com/repos/takattila/Clock-With-Weather-EWW/releases/latest&query=tag_name)](https://github.com/takattila/Clock-With-Weather-EWW/releases)
[![Wiki](https://img.shields.io/badge/wiki-docs-orange)](https://github.com/takattila/Clock-With-Weather-EWW/wiki)
[![Screenshots](https://img.shields.io/badge/view-screenshots-blue)](#screenshots)


- This widget uses [openweathermap.org](https://openweathermap.org) API, to get weather information.
- Easy to customize, supports appearance on **light** and **dark** backgrounds. *(See: [Example Themes](./themes/themes.md))*.
- Supports `12` and `24-hour` clock format.
- **Wayland native**: runs via **EWW** (`ElKowar's Wacky Widgets`) + GTK layer-shell; it also works on X11.
- **System Monitor Panel**: *(See: [Screenshots](#screenshots))*
    - Real-time **CPU** and **Memory** usage charts.
    - **Network Traffic** monitoring (Download/Upload).
    - **Dynamic Scaling**: Network charts automatically adjust their scale and units (KiB/s to MiB/s) based on traffic.
    - **Auto-detection**: Automatically identifies the active network interface (NIC).
- **Taskbar-aware panel**: the panel aligns to the taskbar with a symmetric gap on both sides.
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
*   **Taskbar-aware Panel**: The panel is aligned to the taskbar with a symmetric gap on the taskbar side and on the opposite screen edge (see the "Panel alignment" section).
*   **Visual Hierarchy**: The panel uses alternating "light" and "dark" colors for the charts (e.g., CPU vs. Memory, Download vs. Upload). This intentional design choice provides better visual separation, making it easier to distinguish between different data streams at a glance.


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
bash -c "$(wget --no-check-certificate --no-cache --no-cookies -O- https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/scripts/install.sh)"
```

... via curl:

```bash
bash -c "$(curl -fsSLk https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/scripts/install.sh)"
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

[Back to top](#clock-with-weather-eww)

## Screenshots

### With panel, theme: light-orange

![](./images/screenshots/panel-light-orange.png)

### With panel, theme: dark-orange-bg

![](./images/screenshots/panel-dark-orange-bg.png)

[Back to top](#clock-with-weather-eww)

## Wiki

For detailed documentation, please visit the [wiki](https://github.com/takattila/Clock-With-Weather-EWW/wiki) page.

[Back to top](#clock-with-weather-eww)

## Example Themes

Click [here to see](./themes/themes.md) the available example themes!

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
| `xprop` | any | reading `_NET_WORKAREA` (panel height) |
| `xrandr` | any | resolution / workarea fallback |
| `Noto Sans` font | any | the only font family used |

### For testing / development

| Dependency | Role |
|---|---|
| `spectacle` | taking screenshots for verification |
| `PIL` (pillow) | image measurement / comparison (development aid) |

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
2. **`workarea.py`** — reads `_NET_WORKAREA` and the `panel.gap` value from
   `config.yaml`, then computes the `panel_window` geometry (anchor + offsets
   + height) so the panel is inset from the taskbar **and** from the opposite
   screen edge by the **same gap** (Req 2). The offsets are interpreted for
   the current compositor (Wayland layer-shell vs. absolute X11 coordinates,
   see the "Panel alignment" section). The computed values override the
   `panel_window` geometry in `eww.yuck` at runtime. If the X display is
   unreachable, the committed geometry is kept (no clobbering with a
   fallback).
3. Kills the old daemon: `eww --config . kill`
4. `eww --config . daemon` + `eww --config . open main_window` + `eww --config . open panel_window`

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
`themes/weather/<name>/weather.yaml`:

```yaml
# config.yaml
appearance: light       # -> themes/appearance/<name>/appearance.yaml
weather: default        # -> themes/weather/<name>/weather.yaml
system:
  hour_format: "24"     # "24" | "12"
  corner_radius: 20     # bg corner rounding (px) for BOTH widgets; 0 = square
panel:
  gap: 16               # symmetric spacing (px) around the panel (Req 2)
```

| Field | Values | Effect |
|---|---|---|
| `appearance` | `light`, `dark`, `light-bg`, ... | which `themes/appearance/<name>/appearance.yaml` colors to use |
| `weather` | `default`, `budapest`, `berlin`, ... | which `themes/weather/<name>/weather.yaml` provides `city`, `lang`, `units` |
| `system.hour_format` | `24` / `12` | the `%H` / `%I` format of the `defpoll hour` |
| `system.corner_radius` | integer px | bg corner rounding for both the clock/weather widget and the panel; `0` = sharp corners (written by `theme.py` into `$bg-radius` in `eww.theme.scss`) |
| `panel.gap` | integer px | the panel is inset from the taskbar and from the opposite screen edge by this same gap (see the "Panel alignment" section) |

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
   | `date_year` | 1m | `date +%Y.` |
   | `date_day` | 1m | `date "+| %B %d. | %A"` (en_US locale) |
   | `system_info` | 5s | `./scripts/system.py` (JSON) |
   | `weather_info` | 10m | `./scripts/weather.py <key> <city> <lang> <units>` (JSON) |
   | `panel` | 1s | `./scripts/panel.py` (JSON + SVG charts) |
   | `config` | 5s | `./scripts/config.py` (merged JSON from `config.yaml` + weather theme) |
   | `theme` | 5s | `cat eww.theme.json` |

   > The `config`/`theme` intervals are only a **safety net**. In normal use the
   > inotify watcher (`scripts/watch.py`, see below) reloads the widget the
   > moment a YAML config/theme file is saved, so changes appear instantly.

2. **`defwidget widget_clock_weather`** — the main window. An `overlay` + fixed
   `745x250` sizer in which every element is **absolutely positioned** with
   `margin-left`/`margin-top` (see the "Modifying how elements are displayed"
   section). The elements: year/date, hour/minute/second, HDD/RAM, CPU/SWAP,
   divider line, weather icon, city, temperature, description, MIN/MAX/Feels.

3. **`defwidget widget_panel`** — the system monitor panel. Four
   `panel-section`s: `CPU`, `MEMORY`, `NET DOWN`, `NET UP`. Each has a title
   (`panel-title`), a status text (`panel-status`) and an SVG chart
   (`panel-chart`).

4. **`defwindow` blocks** — `main_window` (745x250, center) and
   `panel_window` (250 wide, top-right, full height).

### `scripts/` — data-producing Python and shell scripts

| Script | Output | Responsibility |
|---|---|---|
| `system.py` | `{hdd, ram, cpu, swap}` | `psutil`/`shutil`-based system info, dynamic `format_bytes` (B/KB/MB/GB/TB) |
| `weather.py` | OpenWeatherMap JSON + `temp_fmt`, `unit_symbol`, `icon_path` | API call, rounding, °C/°F |
| `panel.py` | `{cpu_file, mem_file, down_file, up_file, cpu_txt, ...}` | generating chart SVGs (`charts/*.svg`, 100-point scrolling history), active NIC detection |
| `theme.py` | `eww.theme.scss` + `eww.theme.json` | `config.yaml` `appearance` + `themes/appearance/<name>/appearance.yaml` → EWW theme |
| `config.py` | merged JSON / `--key` values | `config.yaml` + `themes/weather/<name>/weather.yaml` → the values for the `defpoll`s |
| `workarea.py` | JSON (screen / workarea / taskbar position / panel geometry / compositor) | reading `_NET_WORKAREA`, detecting the taskbar position and computing the symmetric panel geometry (`panel.gap`); detects Wayland vs. X11 and computes the offsets for the current compositor; also logs a human-readable summary to stderr |
| `watch.py` | — | inotify-based watcher (`ctypes`, no packages, ~0 CPU idle): on a change to `config.yaml` / theme YAMLs it runs `theme.py` + `eww reload`; log: `watch.log`, PID: `watch.pid` |
| `start.sh` | — | starting the widget (section 3): Plasma check (Wayland only), theme generation, taskbar alignment, `eww daemon` + opening windows, watcher start |
| `stop.sh` | — | stopping the widget (`eww --config . kill`) |
| `install.sh` | — | cross-distro installer (the "Installation" section): installs eww + all dependencies, clones the repo, sets the API key, creates the desktop/menu icons and starts the widgets |
| `setup.sh` | — | interactive setup: API key, appearance/weather theme, hour format, and desktop/menu icon creation (menu icons always, desktop icons optional) |
| `setup-test-env.sh` | — | enabling/disabling and restoring the KDE Plasma test environment (section 4): `hide` / `status` / `restore` |
| `git-filter-repo.sh` | — | vendored **git-filter-repo** (history-rewriting tool, Python 3 + git only): used to scrub secrets (e.g. an API key) from the whole git history — run `git-filter-repo.sh --replace-text <rules>` in the repo root |

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

- Every element in the `745x250` overlay is **absolutely positioned**:
  `margin-left` = X coordinate, `margin-top` = Y coordinate (positions the top
  of the label).

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
| `.hdd-label`...`.swap-value` | system info, 2 lines | `.sys-label` (light, bold 15px) + `.sys-value` (dark 15px) |
| `.divider` | divider line | `margin-left: 414`, `margin-top: 14` |
| `.weather-icon` | weather icon | 64x64 via `:image-width/height` (in the yuck) |
| `.city-icon`, `.city-label` | city icon + name | icon 20x20; label `font-size: 30px`, bold |
| `.temp-icon`, `.temp-label` | thermometer + temperature | icon 32x32; label `font-size: 44px`, bold |
| `.details-icon`, `.details-label` | description | 15px |
| `.stat-min/...` | MIN/MAX/Feels | 15px |
| `.panel-title`, `.panel-status`, `.panel-chart` | panel parts | 22px bold / 14px / SVG |

### Theme variables (`eww.theme.scss`)

The file is generated by `theme.py`; don't edit it by hand (it is lost on the
next start). Instead modify `themes/appearance/<name>/appearance.yaml`:

```scss
$theme: "light";
$icon-set: "dovora";
$font-face: "Noto Sans";
$color-light: #ffffff;
$color-dark: #9e9e9e;
$bg-color: #000000;
$bg-alpha: 0.0;
```

### Resize / reposition workflow

1. Modify `eww.scss`.
2. `eww --config ~/.conky/Clock-With-Weather-EWW reload`
3. `spectacle -b -o shot.png` and image measurement (PIL) — see the "Verified
   facts" section.

### Panel alignment (taskbar-relative, "Req 2")

The `panel_window` (250 px wide) is positioned so that the free spacing on the
**taskbar side and on the opposite screen edge is equal**. `start.sh` computes
this from `_NET_WORKAREA` + `config.yaml → panel.gap` (default **16 px**) via
`scripts/workarea.py`, which detects the taskbar position:

| Taskbar position | Panel geometry result |
|---|---|
| **top** | `anchor "top right"`, `y = gap` (Wayland) / `y = workarea.y + gap` (X11), height `= workarea_h − 2·gap` → gap(panel→taskbar) = gap(panel→screen bottom) |
| **bottom** | `anchor "bottom right"`, `y = taskbar_h + gap` (bottom margin), height `= workarea_h − 2·gap` → gap(panel→taskbar) = gap(panel→screen top) |
| **right** | the panel moves to the **left** edge: `anchor "top left"`, `x = (workarea_w − 250)/2` → gap(panel→taskbar) = gap(panel→left screen edge) |
| **left** | `anchor "top right"`, `x = (workarea_w − 250)/2` → gap(panel→taskbar) = gap(panel→right screen edge) |
| **none** | `anchor "top right"`, flush right, inset top/bottom by `gap` |

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
startup (the committed default reflects the current machine: 30 px taskbar,
`gap=16` → `:y "16px" :height "1018px"`, verified to render at screen
`y=46..1063`, i.e. a 16 px gap on both sides). `PANEL_HEIGHT` is exported for
`panel.py` so the chart heights match the inset panel.

---

## 7. Verified facts and measurement method

### Window geometry

- Widget size: **745x250**. On the screen the window origin is **x=587, y=392**.
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
