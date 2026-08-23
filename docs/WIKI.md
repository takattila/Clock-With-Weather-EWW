# WIKI — Technical Documentation

> Detailed technical documentation for **Clock-With-Weather-EWW**.
> For an overview and installation instructions, see the [README](README.md).

---

## Detailed documentation

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
4. clones the repo to `~/.eww/` and checks out the latest release tag,
5. installs the `NotoSans-Regular.ttf` font,
6. asks for the **OpenWeatherMap API key** → saves it to `.api_key`
   (chmod 600, git-ignored),
7. creates the **desktop / menu icons** (menu always, desktop optionally),
8. starts the widgets (`scripts/bin/start.sh`): daemon + both windows + watcher.

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
| `pytest` | running the headless unit tests (`pip install -r requirements.txt`) |

### Continuous integration (GitHub Actions)

The repository runs headless checks on every push / pull request
(`.github/workflows/ci.yml`):

- `pytest` for the logic that is testable without a display: `config.py`,
  `config_set.py`, `workarea.py`, `theme.py`, `weather.py` (mocked
  `requests`), `system.py` and `panel.py` (mocked `psutil`). Run them locally
  with:

  ```bash
  pip install -r requirements.txt
  python -m pytest tests/ -v
  ```

- `find scripts -name "*.py" -print0 | xargs -0 python -m py_compile` — syntax check for every Python script (including the core/widgets/move subfolders).
- YAML validation — `config.yaml` + all `assets/themes/**/*.yaml` must parse.
- ShellCheck on `scripts/bin/*.sh` (severity `-S error`; `tools/git-filter-repo.sh`
  is a vendored Python tool despite its `.sh` extension, so it is excluded).

Pushing a `v*` tag also triggers `.github/workflows/release.yml`, which creates
a GitHub Release with a changelog generated from `git log` (the README version
badge reads `releases/latest`).

EWW rendering / screenshot jobs are intentionally **not** part of CI: they need
a real display + GTK + an `eww` source build. The `tools/screenshots` capture
tool stays a manual/on-desktop step.

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
under `assets/themes/` as **YAML**, so this widget works fully standalone.

---

## 2. Version-change risks ("widget does not start")

The widget is sensitive to the following version changes. Most failure symptoms
are silent (empty window, missing text), so after starting **always check the
terminal** (`eww` logs `defpoll` errors).

| What changes | Symptom | Cause / solution |
|---|---|---|
| **`eww` major version** (0.5 → 0.6/1.0) | the widget does not start, or CSS fails to load | The `yuck` syntax (`:geometry`, `defpoll`, `:anchor`) and the SCSS `@import` API may change. Check the [eww releases](https://github.com/elkowar/eww/releases). |
| **`eww` minor/patch** | rarely a problem | If the `daemon` reports `Error while forwarding command` after the config loads, it can happen, but the widget still renders — don't panic, measure the screen. On 0.6.0 two more gotchas were measured on this machine: **event handlers on widgets created inside `(for ...)` loops never fire** (that is why the hover submenu is rendered from a prebuilt `literal`, see scripts/widgets/submenu.py), and a nested `button` inside an `eventbox` swallows the box's own enter/leave events (hover rows are therefore plain eventboxes, not buttons). Also: rapidly re-opening the same window id leaks the previous override-redirect X window, and a `close` issued while the daemon regenerates can be silently dropped — close_popup.py verifies via `eww active-windows` (compositor-independent, works on Wayland too) and retries until every popup is really gone, force-unmapping strays on X11. |
| **`python` major** (3.x → 4.x) | `system.py` / `panel.py` errors | Depends on the availability of `psutil`/`requests` binary wheels. |
| **`psutil` major** | `panel.py` produces no JSON | API differences (e.g. `cpu_times` order, `net_io_counters`). Symptom: the panel window is empty. |
| **`PyYAML` missing** | the clock and the `defpoll`s are empty | `config.py` / `theme.py` read the YAML configs via `import yaml` — without it nothing is read. Symptom: the whole widget is empty. |
| **`xprop` missing** | the panel height is wrong | `workarea.py` falls into the fallback chain (`xrandr` → 1080). |
| **`Noto Sans` not installed** | everything is shifted | `fc-match "Noto Sans"` → must be `NotoSans-Regular.ttf`. To switch fonts, change `$font-face` in `eww.theme.scss` and recalibrate the margins. |
| **KDE/kwin version** | window offset | The window is centered relative to the workarea (see the "Window geometry" section). |

**Most important rule:** every value in the `defpoll`s is the output of an
external command (`date`, `../scripts/<group>/*.py`). If any command fails or is
missing, an **empty/raw `null`** value goes into the widget, which is often an
"invisible" error.

---

## 3. Starting the widget

```bash
cd ~/.eww/Clock-With-Weather-EWW
./scripts/bin/start.sh
```

`scripts/bin/start.sh` does the following:

0. **KDE Plasma check** *(Wayland only)* — on a Wayland session, if
   `plasmashell` is not running, `scripts/bin/setup-test-env.sh restore` restores
   the normal desktop (and restarts plasmashell); if there is no backup, it
   starts `plasmashell` directly so the widget can be displayed. On X11 (e.g.
   Linux Mint/Cinnamon) this step is skipped, because the widget does not need a
   desktop shell there.
1. **`theme.py`** — generates the `eww.theme.scss` and `eww.theme.json` files
   (written into the eww config dir, next to `eww.yuck`)
   from the `appearance` field of `config.yaml` +
   `assets/themes/appearance/<name>/appearance.yaml` (colors, font, icon set,
   background transparency).
2. **`workarea.py`** — reads `_NET_WORKAREA`, the `panel.gap` value(s) and the
   `panel.window.alignment` (passed as `--align left|right`) from `config.yaml`,
   then computes the `panel_window` geometry (anchor + offsets
   + height) so the panel is inset from the taskbar, from the opposite screen
   edge and from the lateral screen edge by the configured per-side gap
   (Req 2), and flush to the left or right screen edge when
   `panel.window.alignment` is set. The offsets are interpreted for
   the current compositor (Wayland layer-shell vs. absolute X11 coordinates,
   see the "Panel alignment" section). The computed values override the
   `panel_window` geometry in `eww.yuck` at runtime. If the X display is
   unreachable, the committed geometry is kept (no clobbering with a
   fallback).
3. Kills the old daemon: `eww --config eww kill`
4. `eww --config eww daemon`, then `start.sh` opens the windows with per-monitor geometry (`eww --config eww open --id main_<N> ...`).

### Stopping

```bash
cd ~/.eww/Clock-With-Weather-EWW
./scripts/bin/stop.sh
```

`scripts/bin/stop.sh` stops the eww daemon for this config directory
(`eww --config eww kill`), which closes both windows. Manually that is:

```bash
eww --config ~/.eww/Clock-With-Weather-EWW/eww kill
```

### Setup and desktop / menu icons

The installer and the widget create **`.desktop` launchers**:

- `start-clock-with-weather-eww.desktop` — starts the widget (`scripts/bin/start.sh`).
- `setup-clock-with-weather-eww.desktop` — opens the setup (terminal).

**Menu icons** are always created in `~/.local/share/applications/`; **desktop
icons** are created optionally (the installer/setup asks whether you want
them) in `$(xdg-user-dir DESKTOP)`.

To change the settings (API key, appearance theme, weather theme, hour format)
and (re)create the icons interactively:

```bash
cd ~/.eww/Clock-With-Weather-EWW
./scripts/bin/setup.sh
```

### Configuration (`config.yaml`)

The central config is **YAML**. It selects the active appearance and weather
theme; the city, language and unit settings come from the selected
`assets/themes/weather/<name>/weather.yaml` (or, alternatively, can be defined
**inline** in `config.yaml`, see below):

```yaml
# config.yaml
appearance: light       # theme name -> assets/themes/appearance/<name>/appearance.yaml,
                        # or a custom map (see the "Configuration" section)
weather:
  name: default         # -> assets/themes/weather/<name>/weather.yaml,
                        # or omit it and define the city settings inline (see below)
  window:               # clock widget position (same names as a Conky alignment)
    alignment: middle_middle   # top_left..middle_middle
    position_x: 0       # pixel offset of the clock from its anchor
    position_y: 0
system:
  scale:                  # widget scale, one per widget: 1.0 = 100% | 0.8 = 80%
    weather: 1.0          #   clock widget  (a single number also works -> both)
    panel: 1.0            #   system monitor panel
  hour_format: "24"     # "24" | "12"
  corner_radius: 20     # bg corner rounding (px) for BOTH widgets; 0 = square
panel:
  window:
    alignment: right    # right (default) | left — full-height panel side
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
   `assets/themes/weather/<name>/weather.yaml` (the classic behavior).
2. **An inline map (no `name` key)** — the weather details are defined right in
   `config.yaml`:

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
   ```

The two forms also **mix**: with `name` set, the theme provides the baseline
values and any inline fields present patch on top of it — handy for local
overrides (`config.local.yaml` may override a single value of a themed city,
e.g. just `units`, without redefining the rest).

The `appearance` field accepts **two forms**:

1. **A theme name (string)** — `appearance: light` selects
   `assets/themes/appearance/<name>/appearance.yaml` (the classic behavior).
2. **A custom map (object)** — an inline appearance definition with the same
   structure as `assets/themes/appearance/<name>/appearance.yaml`:

   ```yaml
   appearance:
     theme: light        # image folder under assets/icons-src/<theme>/ (light | dark)
     icon:
       set: dovora        # icon set under assets/icons-src/<theme>/weather/<set>/
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
| `appearance` | `light`, `dark`, `light-bg`, ... **or** a custom map | a theme name selects `assets/themes/appearance/<name>/appearance.yaml`; a custom map (`theme`, `icon`, `font`, `background`) defines the appearance inline (see the "Configuration" section) |
| `appearance.icon.color` | `#rrggbb` (light / dark) | icon color, tinted into the PNGs by `theme.py` (Pillow); `light` is used when the theme is "light", `dark` when "dark". Omit it to keep the icons' original colors |
| `weather.name` | `default`, `budapest`, `berlin`, ... | which `assets/themes/weather/<name>/weather.yaml` provides `city`, `lang`, `units`. Omit the `name` key to define the city settings **inline** in `config.yaml` (`city`, `language_code`, `lang`, `units`, `api_url`). The forms mix: with `name` set, inline fields patch the theme's baseline (useful for `config.local.yaml` overrides) |
| `weather.city` | string | the city queried from the weather API; in theme mode it patches/overrides the theme's city |
| `weather.language_code` | `hu`, `en`, `fr`, ... | the country code of the city; in theme mode it patches/overrides the theme's value |
| `weather.lang` | `hu`, `en`, `fr`, ... | the display language of the weather description; in theme mode it patches/overrides the theme's value |
| `weather.units` | `metric` / `imperial` | °C vs °F; in theme mode it patches/overrides the theme's value |
| `weather.api_url` | URL | the OpenWeatherMap API endpoint used by `weather.py` (default: `https://api.openweathermap.org/data/2.5/weather`); taken from the selected theme or the inline map |
| `weather.window.alignment` | `top_left`, `top_right`, `top_middle`, `bottom_left`, `bottom_right`, `bottom_middle`, `middle_left`, `middle_right`, `middle_middle` | where the clock widget is anchored |
| `weather.window.position_x` / `position_y` | integer px | pixel offset of the clock widget from its anchor |
| `system.scale.weather` | float | scaling factor for the **clock** widget: every font, spacing, position and icon is multiplied by it, so the widget scales as one object and the relative distances between its parts never change. `1.0` = 100% (default), `0.8` = 80%. Written by `theme.py` into `$scale-weather` (`eww.theme.scss`) + `scale.weather` (`eww.theme.json`); `start.sh` scales the window geometry to match. `weather.window.position_x`/`position_y` screen offsets are NOT scaled |
| `system.scale.panel` | float | scaling factor for the **panel** widget (same semantics as `scale.weather`, above). Written into `$scale-panel` + `scale.panel`; `workarea.py` scales the panel window geometry to match. A single number (`scale: 0.8`) is also accepted and applies to **both** widgets |
| `system.hour_format` | `24` / `12` | the `%H` / `%I` format of the `defpoll hour`; `12` also shows a small AM/PM indicator under the hour digits |
| `system.corner_radius` | integer px | bg corner rounding for both the clock/weather widget and the panel; `0` = sharp corners (written by `theme.py` into `$bg-radius` in `eww.theme.scss`) |
| `panel.window.alignment` | `right` / `left` | the horizontal side of the full-height panel (see the "Panel alignment" section) |
| `panel.gap` | integer px **or** map | the panel is inset from the taskbar, the opposite screen edge and the lateral edge. A single number applies to every side; a map `{ top:, right:, bottom:, left: }` sets each side independently (braces/commas optional, e.g. block style) — missing sides default to 16 px. See the "Panel alignment" section |

The widget itself cannot parse YAML, so `scripts/core/config.py` reads `config.yaml`
+ the selected weather theme and prints the merged values as JSON for the
`defpoll`s (see the "Structure" section). `jq` is no longer needed.

Several of these keys can also be changed at runtime without touching any
file by hand: `scripts/core/config_set.py` writes them into
`config.local.yaml` (`--key hour_format|appearance|units|panel_enabled|
panel_alignment --value ...`, no `--widget`/`--monitor` needed), and the
right-click quick-settings menu exposes them as hover submenus (see the
"Right-click quick-settings menu" section).

#### API key (`OPENWEATHER_API_KEY`)

The OpenWeatherMap key is **not** stored in `config.yaml` (that file is part of
the repository). It is resolved by `scripts/core/config.py` in this order:

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
**`scripts/bin/setup-test-env.sh`** script:

```bash
cd ~/.eww/Clock-With-Weather-EWW

./scripts/bin/setup-test-env.sh hide                # test mode: widgets + icons hidden, solid background
./scripts/bin/setup-test-env.sh hide "#112233"      # ... with a custom background color
./scripts/bin/setup-test-env.sh hide "/path/to/wallpaper.jpg"  # ... with a wallpaper image
./scripts/bin/setup-test-env.sh status              # current state
./scripts/bin/setup-test-env.sh restore             # restore the normal desktop
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

### `eww/eww.yuck` — the widget tree and the data sources

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
   | `system_info` | 5s | `../scripts/core/system.py` (JSON) |
   | `weather_info` | 10m | `../scripts/core/weather.py <key> <city> <lang> <units> <api_url>` (JSON) |
   | `panel` | 1s | `../scripts/widgets/panel.py` (JSON + SVG charts) |
   | `config` | 5s | `../scripts/core/config.py` (merged JSON from `config.yaml` + weather theme) |
   | `theme` | 5s | `cat eww.theme.json` |

   > The `config`/`theme` intervals are only a **safety net**. In normal use the
   > inotify watcher (`scripts/core/watch.py`, see below) reloads the widget the
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

The scripts are grouped by role: `scripts/core/` (config/theme/watch/system
data), `scripts/widgets/` (panel, context menu, About popups),
`scripts/move/` (Move/Resize overlay + input daemons) and `scripts/bin/`
(start/stop/install/setup shell tooling).

| Script | Output | Responsibility |
|---|---|---|
| `system.py` | `{hdd, ram, cpu, swap}` | `psutil`/`shutil`-based system info, dynamic `format_bytes` (B/KB/MB/GB/TB) |
| `weather.py` | OpenWeatherMap JSON + `temp_fmt`, `unit_symbol`, `icon_path` | API call to the configured `api_url`, rounding, °C/°F |
| `panel.py` | `{cpu_file, mem_file, down_file, up_file, cpu_txt, ...}` | generating chart SVGs (`charts/*.svg`, 100-point scrolling history), active NIC detection |
| `theme.py` | `eww.theme.scss` + `eww.theme.json` + tinted icons under `generated/icons/` | `config.yaml` `appearance` + `assets/themes/appearance/<name>/appearance.yaml` → EWW theme (+ PNG tinting when `appearance.icon.color` is set) |
| `config.py` | merged JSON / `--key` values | `config.yaml` + `assets/themes/weather/<name>/weather.yaml` **or** the inline `weather` map → the values for the `defpoll`s |
| `workarea.py` | JSON (screen / workarea / taskbar position / panel geometry / compositor) | reading `_NET_WORKAREA`, detecting the taskbar position and computing the symmetric panel geometry (`panel.gap`), honoring the `--align left|right` panel side (`panel.window.alignment`); detects Wayland vs. X11 and computes the offsets for the current compositor; also logs a human-readable summary to stderr |
| `watch.py` | — | inotify-based watcher (`ctypes`, no packages, ~0 CPU idle): on a change to `config.yaml` / theme YAMLs it runs `theme.py` + `eww reload`; a `config.yaml` change also triggers `start.sh --relayout`; log: `logs/watch.log`, PID: `run/watch.pid` |
| `start.sh` | — | starting the widget (section 3): Plasma check (Wayland only), theme generation, taskbar alignment + panel side (`panel.window.alignment`), `eww daemon` + opening windows, watcher start |
| `stop.sh` | — | stopping the widget (`eww --config eww kill`) |
| `install.sh` | — | cross-distro installer (the "Installation" section): installs eww + all dependencies, clones the repo, sets the API key, creates the desktop/menu icons and starts the widgets |
| `setup.sh` | — | interactive setup: API key, appearance/weather theme, hour format, and desktop/menu icon creation (menu icons always, desktop icons optional) |
| `setup-test-env.sh` | — | enabling/disabling and restoring the KDE Plasma test environment (section 4): `hide` / `status` / `restore` |
| `menu_toggle.py` (`scripts/widgets/`) | — | context-menu quick settings: with `--value` writes an exact value, without it flips/cycles (hour_format 24↔12, appearance next theme alphabetically, units °C↔°F with an instant weather refresh, panel_enabled, panel_alignment); delegates to `config_set.py`, the watcher applies the change live |
| `submenu.py` (`scripts/widgets/`) | — | hover submenus of the five selectable context-menu rows: builds the option list per key (Theme dynamically from `assets/themes/appearance/`, two balanced columns), prebuilds the whole picker as a static yuck literal into `sub_yuck` and shows it in the ctx_menu window's side pane, vertically aligned with the hovered row |
| `hard-reset.sh` (`scripts/bin/`) | — | factory reset: deletes the git-ignored `config.local.yaml` (**no backup**) + a stale input session, regenerates the theme from the committed defaults and relayouts; also available as the context menu's "Hard reset" item |
| `git-filter-repo.sh` | — | vendored **git-filter-repo** (history-rewriting tool, Python 3 + git only): used to scrub secrets (e.g. an API key) from the whole git history — run `git-filter-repo.sh --replace-text <rules>` in the repo root |

### `charts/` — generated SVGs

`panel.py` writes a new, timestamped SVG to `charts/` on every poll
(`cpu_00042.svg`, ...), and returns the file name in the `defpoll panel` JSON.
Old ones are deleted automatically (it keeps 3 per type). **Don't commit
them** — gitignored (`.gitignore`).

### `assets/` (`icons-src/`, `themes/`, `fonts/`)

The widget directory is **self-contained** (ready for a standalone repo): the
shared assets are stored here.

- `assets/icons-src/<theme>/elements/` — line, location icon, thermometer, arrows.
- `assets/icons-src/<theme>/weather/<icon-set>/` — weather icons
  (`01d.png`, `02d`, ...). `theme.py` takes the `icon_set` from the selected
  `assets/themes/appearance/<name>/appearance.yaml`.
- `generated/icons/<theme>/...` — **git-ignored** working copies of the active
  theme's icons. `theme.py` recreates this folder on every start / config
  change: with `appearance.icon.color` set the PNGs are tinted (Pillow), without
  it they are copied unchanged. `eww.yuck` always loads the icons from here.
- `assets/themes/appearance/<name>/appearance.yaml` — the appearance themes.
- `assets/themes/weather/<name>/weather.yaml` — the city settings (`city`,
  `language_code`, `lang`, `units`).
- `assets/fonts/NotoSans-Regular.ttf` — the bundled font (the GTK side still needs the
  `Noto Sans` family installed via fontconfig).

---

## 6. Modifying how elements are displayed (EWW CSS)

All formatting is in the **`eww/eww.scss`** file. `eww.yuck` only provides the
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
| `.meridiem-label` / `.meridiem-chip` | AM/PM indicator (12h only) | `font-size: 28px`, bold, bottom of the hour digits; the 54x32 chip masks the digit with the widget background color — always at least 60% opaque, so it stays visible even when the widget background is fully transparent (`background.transparency: 0.0`) |
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
next start). Instead modify `assets/themes/appearance/<name>/appearance.yaml` or use a
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

### Right-click quick-settings menu

Right-clicking either widget opens the `ctx_menu` eww window (470x500 px:
the 220px menu column plus a picker pane on its right, opened at the cursor
by `scripts/widgets/ctx.py` + `scripts/move/menu_pos.py`; transparent
full-screen dismiss layers on EVERY connected monitor close it on outside
clicks — clicking on another screen dismisses the popups too — ESC works as
well).
The five selectable rows are **hover-only parents**: pointing at one opens a
small submenu next to it (`scripts/widgets/submenu.py`) with the possible
values, the active one highlighted; picking an entry writes it and closes
the popups.

| Row | Submenu values | Config key |
|---|---|---|
| Move / Resize / Reset | — (click actions: GTK move/resize session, factory geometry) |
| AM/PM switch | `24h` / `12h` | `system.hour_format` |
| Theme | every theme under `assets/themes/appearance/`, two columns | `appearance` |
| Units | `°C (metric)` / `°F (imperial)` — picking one also re-fetches the weather instantly so °C/°F does not wait for the 10-minute poll | `weather.units` |
| Panel | shown / hidden (applied by the watcher's relayout) | `panel.enabled` |
| Side | right / left | `panel.window.alignment` |
| Hard reset | runs `scripts/bin/hard-reset.sh`: deletes `config.local.yaml` (no backup), so every setting returns to the committed default |
| About | the GTK About dialog |

Submenu mechanics:

- The picker is NOT a separate window: it renders INSIDE the ctx_menu
  window, in a 250px-wide pane to the right of the item rows, vertically
  aligned with the hovered row. This sidesteps every X11/Wayland window
  placement pitfall and works identically on both compositors.
- `submenu.py` prebuilds the whole picker as one static yuck definition —
  every option row an `eventbox` with its click handler and the active value
  highlighted (Theme = all themes in two balanced columns) — pushes it into
  the `sub_yuck` eww variable and shows the pane (`sub_show=true`,
  `sub_top=<row offset>`). Handlers inside `(for ...)` loops never fire on
  eww 0.6.0, which is why the definition is generated instead of looped.
- LIFETIME: the pane lives exactly as long as the context menu. There are no
  hover-out timers: option clicks, outside clicks, ESC and re-opening the
  menu all go through close_popup.py / ctx.py which hide the pane together
  with the menu. (Timer/generation races measured earlier made this fragile,
  so they are gone on purpose.)
- Values are written through `menu_toggle.py --key <key> --value <value>`
  → `config_set.py` into the git-ignored `config.local.yaml`; the watcher
  regenerates / reloads / relayouts automatically.
- The parent-row labels still show the current state from the `config`
  defpoll (5 s refresh), so right after a selection they can lag up to 5 s.

### Hand-typed resize percentage

In the Move / Resize control panel (`scripts/move/move_panel.py`) the value
between − and + is an editable entry, not just a label:

- type a percentage (30–150) and press **Enter** — or just leave the field;
- on focus-out an uncommitted draft is discarded and the field snaps back to
  the live value polled from the eww variable `move_pct` every 250 ms;
- typed values are applied by `move_ctl.py --action set_scale --value N`,
  which clamps to 30–150% and keeps the anchored corner / panel side gap
  fixed exactly like the ± buttons do.

While the field owns the keyboard, the panel marks the session file with
`"typing": true`; the evdev daemon ignores every key during that time
(otherwise Enter would save and −/+ would zoom while typing). Click outside
the field first if you want ESC to cancel the session.

### Resize / reposition workflow

1. Modify `eww.scss`.
2. `eww --config ~/.eww/Clock-With-Weather-EWW reload`
3. `spectacle -b -o shot.png` and image measurement (PIL) — see the "Verified
   facts" section.

### Panel alignment (taskbar-relative, "Req 2")

The `panel_window` (250 px wide) is positioned so that the free spacing on the
**taskbar side, the opposite screen edge and the lateral screen edge** is the
configured gap on every side. `start.sh` computes this from `_NET_WORKAREA` +
`config.yaml → panel.gap` (default **16 px**; either a single number or a
per-side map `{ top:, right:, bottom:, left: }`) via `scripts/core/workarea.py`,
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
eww --config ~/.eww/Clock-With-Weather-EWW reload
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