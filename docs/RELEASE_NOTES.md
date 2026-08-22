# Clock-With-Weather-EWW — v2.0.0

**A beautiful, fully customizable clock & weather widget with a live system
monitor panel for your desktop.** Runs natively on **Wayland** (EWW + GTK
layer-shell) and also works on **X11**. Powered by the
[OpenWeatherMap](https://openweathermap.org) API.

**v2.0.0 is a structural release**: no new features and no visual changes —
the whole repository was reorganized into logical folders. Because file
locations changed, upgrading from v1.x requires the small migration below.

---

## What changed in v2.0.0 (breaking)

| Old location (v1.x) | New location (v2.0.0) |
|---|---|
| `scripts/start.sh`, `stop.sh`, `install.sh`, `setup.sh` | `scripts/bin/` |
| `scripts/*.py` (flat) | `scripts/core/`, `scripts/widgets/`, `scripts/move/` |
| `eww.yuck`, `eww.scss` (repo root) | `eww/` — this is the eww **config dir** now |
| `themes/`, `images/theme/`, `fonts/` | `assets/themes/`, `assets/icons-src/`, `assets/fonts/` |
| `WIKI.md`, `PLAN.md`, `RELEASE_NOTES.md` | `docs/` |
| `*.log` / `*.pid` files in the repo root | `logs/` and `run/` |
| `requirements-dev.txt` | merged into `requirements.txt` |

Also new: the generated theme files (`eww.theme.json/.scss`) are written next
to `eww.yuck` inside `eww/`, and the runtime output folders are kept in git
via `.gitkeep` placeholders.

### Upgrade from v1.x

1. Pull / check out `v2.0.0`.
2. **Recreate your desktop & menu launchers**: the ones created by v1.x point
   to the old `scripts/start.sh`. Either run `bash scripts/bin/setup.sh`
   once, or fix the `Exec=` lines of the existing `.desktop` files to
   `scripts/bin/start.sh`.
3. If you drive `eww` manually, pass the new config dir:
   `eww --config ~/.eww/Clock-With-Weather-EWW/eww ...`.
4. Delete leftover root-level `*.log` / `*.pid` / `start.log` files — new ones
   land in `logs/` and `run/`.
5. pip users: install everything from `pip install -r requirements.txt`
   (`pytest` is included under the testing section).
6. Restart the widget: `bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/start.sh`.

---

## Screenshots

| Dark text with light background | Light text with dark background |
|---|---|
| ![Budapest dark blue](./docs/images/screenshots/budapest-dark-blue.png) | ![New York light bg](./docs/images/screenshots/new-york-light-bg.png) |

| System panel — light-orange | System panel — dark-orange-bg |
|---|---|
| ![Panel light orange](./docs/images/screenshots/panel-light-orange.png) | ![Panel dark orange bg](./docs/images/screenshots/panel-dark-orange-bg.png) |

| Right click | Resize weather | Resize panel | About |
|---|---|---|---|
| ![Context menu 1](./docs/images/screenshots/context-menu-01.png) | ![Context menu 2](./docs/images/screenshots/context-menu-02.png) | ![Context menu 3](./docs/images/screenshots/context-menu-03.png) | ![Context menu 4](./docs/images/screenshots/context-menu-04.png) |

---

## Features

- **Clock & Weather** — time, date and live weather (temperature, icon,
  location, description, MIN/MAX/Feels) in one widget.
- **System Monitor Panel** — a side panel with real-time **CPU**, **Memory**
  and **Network Traffic** (Download/Upload) SVG charts.
- **Dynamic Scaling** — the network charts auto-adjust their scale and units
  (KiB/s to MiB/s) based on traffic; the active network interface is detected
  automatically.
- **Wayland native** — runs via **EWW** + GTK layer-shell; works on X11 too
  (e.g. Linux Mint / Cinnamon).
- **Light & dark ready** — supports appearance on both light and dark
  backgrounds, with a wide gallery of ready-made themes.
- **12 / 24-hour clock** — switch the hour format any time.
- **Per-widget scaling** — scale the clock and the panel independently; each
  shrinks as a single object, so the relative distances between its parts never
  change.
- **Taskbar-aware panel** — the panel aligns perfectly to your taskbar with
  per-side gaps (`panel.gap`), and supports **per-monitor positions** via the
  right-click Move / Resize / Reset context menu.
- **Desktop integration** — automatic menu icons and optional desktop
  shortcuts.
- **Live reconfiguration** — a file watcher applies your config/theme changes
  instantly, no restart needed.
- **Continuous integration** — headless unit tests, YAML validation and
  ShellCheck run on every push / pull request; tagged releases are published
  automatically.

---

## Installation

```bash
bash -c "$(curl -fsSLk https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/refs/heads/master/scripts/bin/install.sh)"
```

> Note: the one-liner above works only after v2.0.0 lands on `master`.

The installer is **cross-distro** (Arch, Debian/Ubuntu, Fedora/RHEL,
openSUSE): it detects your package manager and installs **eww + all
dependencies**, then sets up the API key, desktop icons and starts the widget.
To skip the interactive API-key prompt:

```bash
export OPENWEATHER_API_KEY=<YOUR-API-KEY>
```

## Start / stop / configure

```bash
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/start.sh    # start the widget
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/stop.sh     # stop the widget
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/setup.sh    # change API key / theme / hour format
```

## Configuration

Everything lives in a single, heavily commented `config.yaml`:

- `appearance` — a theme name (`light`, `dark`, `dark-orange-bg`, ...) or a
  custom inline appearance map (fonts, colors, icon set + tint, transparency,
  background).
- `weather` — city settings (via a named weather theme or inline), window
  alignment, and **per-monitor** `position_x` / `position_y` / `scale`.
- `system` — hour format (`24`/`12`) and background corner radius.
- `panel` — enable/disable the system panel, alignment, per-monitor offsets,
  and the taskbar `gap` baseline.

The right-click context menu lets you **Move / Resize / Reset** each widget
directly on screen; the resulting values are written back into `config.yaml`
and applied live by the file watcher.

## Themes

A wide gallery of ready-made **light** and **dark** appearance themes plus
per-city weather themes (`assets/themes/weather/<name>/weather.yaml`) — or define
your own colors inline in `config.yaml`.

## Documentation

- **[README](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/README.md)**
  — overview, screenshots and quick start.
- **[WIKI](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/docs/WIKI.md)**
  — dependencies, version-change risks, `config.yaml` reference, project
  structure, EWW/CSS customization and testing.
- **[PLAN](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/docs/PLAN.md)**
  — the executed directory-restructure record behind this release.

## Compatibility

- **Wayland** (KDE Plasma tested) — EWW + GTK layer-shell.
- **X11** (Linux Mint / Cinnamon tested) — EWW absolute-coordinate placement.
- Python 3.11+, eww 0.5.0+, `PyYAML`, `psutil`, `requests`, `pillow`
  (see the WIKI for the full dependency table).

## Project structure (highlights)

| Path | Purpose |
|---|---|
| `eww/` | the widget tree (`eww.yuck`) and its styling (`eww.scss`) |
| `config.yaml` | the central, commented configuration |
| `scripts/core|widgets|move|bin/` | data-producing Python scripts grouped by role (`core`: config/workarea/theme/weather/system, `widgets`: panel/about/ctx, `move`: Move/Resize + input daemons) and the bash install/start/setup tooling in `bin` |
| `assets/themes/` | appearance + per-city weather theme YAMLs |
| `logs/`, `run/` | runtime logs and pid files (git-ignored) |
| `charts/` | generated SVG chart files (git-ignored) |
| `tests/` | headless pytest suite (config, geometry, theme, weather, system, panel) |
| `.github/workflows/` | CI + automated release publishing |

---

> Looking for the **v1.0.0** notes? They are preserved on the
> [v1.0.0 release page](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v1.0.0).
