# Clock-With-Weather-EWW — v2.2.0

**A beautiful, fully customizable clock & weather widget with a live system
monitor panel for your desktop.** Runs natively on **Wayland** (EWW + GTK
layer-shell) and also works on **X11**. Powered by the
[OpenWeatherMap](https://openweathermap.org) API.

**v2.2.0 turns the right-click menu into a quick-settings panel**: switch the
hour format, cycle appearance themes, flip °C/°F, show/hide or re-side the
panel and hard-reset the configuration — all from the context menu, all
written to the git-ignored `config.local.yaml` and applied live. The
Move / Resize dialog gained a hand-typed resize percentage, and a new
`hard-reset.sh` restores the factory defaults with one command.

---

## What changed in v2.2.0

### New: context-menu quick settings

The right-click menu now has **ten items** (labels show the current state):

| Item | What it does |
|---|---|
| Move / Resize | unchanged GTK move / resize session |
| Reset | unchanged per-widget factory geometry |
| `AM/PM: 24h ▸` / `12h ▸` | toggles `system.hour_format` (24 ↔ 12) |
| `Theme: <name> ▸` | cycles through every theme under `assets/themes/appearance/` |
| `Units: °C ▸` / `°F ▸` | flips `weather.units`; the weather is re-fetched instantly instead of waiting for the next 10-minute poll |
| `Panel: shown ▸` / `hidden ▸` | toggles `panel.enabled` (panel windows open/close via relayout) |
| `Side: right ▸` / `left ▸` | flips `panel.window.alignment` |
| `Hard reset` | deletes `config.local.yaml` → every setting returns to the committed defaults |
| About | unchanged |

All toggles run through the new `scripts/widgets/menu_toggle.py`, which
writes with the existing single-writer `scripts/core/config_set.py` into the
git-ignored local override layer; the file watcher applies every change
immediately — the repository stays clean.

### New: hand-typed resize percentage

In the Move / Resize control panel the `%` value between − and + is now an
editable field: type e.g. `80` and press Enter (or leave the field) to resize
exactly, clamped to 30–150% like the buttons. While you are typing, the
keyboard daemon steps aside (no accidental Enter = Save), and uncommitted
drafts snap back when you click elsewhere.

### New: `scripts/bin/hard-reset.sh`

One command factory reset:

```bash
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/hard-reset.sh
```

Deletes the git-ignored `config.local.yaml` (**by design without backup** —
the committed `config.yaml` is never touched), removes stale session state,
regenerates the theme and relayouts the running widget. Also available as the
context menu's "Hard reset" item.

### Changed

- `scripts/core/config_set.py`: new global keys (`hour_format`, `appearance`,
  `units`, `panel_enabled`, `panel_alignment`) writable without
  `--widget`/`--monitor`; `--widget` is now optional (still required for the
  per-widget position/scale/gap keys).
- The context menu window grew to fit ten items (220x440 px).

### Upgrade from v2.x

1. Pull / check out `v2.2.0`.
2. Restart the widget: `bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/start.sh`.
3. Nothing else to do — your existing `config.local.yaml` keeps working; the
   new menu items write into it as usual.

---

## Screenshots

| Dark text with light background | Light text with dark background |
|---|---|
| ![Budapest dark blue](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/budapest-dark-blue.png) | ![New York light bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/new-york-light-bg.png) |

| System panel — light-orange | System panel — dark-orange-bg |
|---|---|
| ![Panel light orange](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/panel-light-orange.png) | ![Panel dark orange bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/panel-dark-orange-bg.png) |

| Right click | Resize weather | Resize panel | About |
|---|---|---|---|
| ![Context menu 1](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/context-menu-01.png) | ![Context menu 2](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/context-menu-02.png) | ![Context menu 3](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/context-menu-03.png) | ![Context menu 4](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/context-menu-04.png) |

---

## Features

- **Clock & Weather** — time, date and live weather (temperature, icon,
  location, description, MIN/MAX/Feels) in one widget.
- **System Monitor Panel** — a side panel with real-time **CPU**, **Memory**
  and **Network Traffic** (Download/Upload) SVG charts.
- **Dynamic Scaling** — the network charts auto-adjust their scale and units
  (KiB/s to MiB/s) based on traffic; the active network interface is detected
  automatically.
- **Quick-settings context menu** — AM/PM switch, theme cycler, °C/°F toggle,
  panel show/hide + side flip and a factory "Hard reset", right on the widget;
  everything applied live through the git-clean local override layer.
- **Git-clean by design** — machine-local settings live in the git-ignored
  `config.local.yaml`; the committed `config.yaml` only changes when *you*
  change a default.
- **Wayland native** — runs via **EWW** + GTK layer-shell; works on X11 too
  (e.g. Linux Mint / Cinnamon).
- **Light & dark ready** — supports appearance on both light and dark
  backgrounds, with a wide gallery of ready-made themes.
- **12 / 24-hour clock** — switch the hour format any time (config, setup
  wizard or right-click menu).
- **Per-widget scaling** — scale the clock and the panel independently, with
  ± steppers *and* a hand-typed exact percentage in the Move / Resize dialog.
- **Taskbar-aware panel** — the panel aligns perfectly to your taskbar with
  per-side gaps (`panel.gap`), and supports **per-monitor positions** via the
  right-click Move / Resize / Reset context menu.
- **Desktop integration** — automatic menu icons and optional desktop
  shortcuts.
- **Live reconfiguration** — a file watcher applies your config/theme/local
  override changes instantly, no restart needed.
- **Continuous integration** — headless unit tests, YAML validation and
  ShellCheck run on every push / pull request; tagged releases are published
  automatically.

---

## Installation

```bash
bash -c "$(curl -fsSLk https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/refs/heads/master/scripts/bin/install.sh)"
```

The installer is **cross-distro** (Arch, Debian/Ubuntu, Fedora/RHEL,
openSUSE): it detects your package manager and installs **eww + all
dependencies**, then sets up the API key, desktop icons and starts the widget.
To skip the interactive API-key prompt:

```bash
export OPENWEATHER_API_KEY=<YOUR-API-KEY>
```

## Start / stop / configure

```bash
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/start.sh      # start the widget
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/stop.sh       # stop the widget
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/setup.sh      # change API key / theme / hour format
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/hard-reset.sh # factory-reset the config
```

## Configuration

Defaults live in a single, heavily commented `config.yaml`; machine-specific
overrides go into the git-ignored `config.local.yaml` (same structure, only
what you want to change):

- `appearance` — a theme name (`light`, `dark`, `dark-orange-bg`, ...) or a
  custom inline appearance map (fonts, colors, icon set + tint, transparency,
  background).
- `weather` — city settings (via a named weather theme or inline), window
  alignment, and **per-monitor** `position_x` / `position_y` / `scale`.
- `system` — hour format (`24`/`12`) and background corner radius.
- `panel` — enable/disable the system panel, alignment, per-monitor offsets,
  and the taskbar `gap` baseline.

The right-click context menu lets you **Move / Resize / Reset** each widget
and flips the most common settings (hour format, theme, units, panel state /
side) directly on screen; the resulting values are written into
`config.local.yaml` and applied live by the file watcher — so the repository
stays clean unless you deliberately edit a default. `hard-reset.sh` (or the
menu's "Hard reset") deletes that local file and returns everything to the
committed defaults.

## Themes

A wide gallery of ready-made **light** and **dark** appearance themes plus
per-city weather themes (`assets/themes/weather/<name>/weather.yaml`) — or define
your own colors inline in `config.yaml` (or locally override them in
`config.local.yaml` without touching the tracked defaults). Cycle through all
appearance themes from the right-click menu.

## Documentation

- **[README](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/README.md)**
  — overview, screenshots and quick start.
- **[WIKI](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/docs/WIKI.md)**
  — dependencies, version-change risks, `config.yaml` reference, project
  structure, EWW/CSS customization and testing.
- **[PLAN](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/docs/PLAN.md)**
  — the executed plan behind the quick-settings context menu, the typed
  resize percentage and the hard reset.

## Compatibility

- **Wayland** (KDE Plasma tested) — EWW + GTK layer-shell.
- **X11** (Linux Mint / Cinnamon tested) — EWW absolute-coordinate placement.
- Python 3.11+, eww 0.5.0+, `PyYAML`, `psutil`, `requests`, `pillow`
  (see the WIKI for the full dependency table).

## Project structure (highlights)

| Path | Purpose |
|---|---|
| `eww/` | the widget tree (`eww.yuck`) and its styling (`eww.scss`) |
| `config.yaml` | the central, commented defaults |
| `config.local.yaml` | git-ignored machine overrides (+ everything the scripts write) |
| `scripts/core|widgets|move|bin/` | data-producing Python scripts grouped by role (`core`: config/workarea/theme/weather/system, `widgets`: panel/about/ctx/menu toggles, `move`: Move/Resize + input daemons) and the bash install/start/setup/reset tooling in `bin` |
| `assets/themes/` | appearance + per-city weather theme YAMLs |
| `logs/`, `run/` | runtime logs and pid files (git-ignored) |
| `charts/` | generated SVG chart files (git-ignored) |
| `tests/` | headless pytest suite (config, geometry, theme, weather, system, panel) |
| `.github/workflows/` | CI + automated release publishing |

---

> Looking for older release notes? They are preserved on their release pages:
> [v2.1.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v2.1.0),
> [v2.0.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v2.0.0),
> [v1.0.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v1.0.0).
