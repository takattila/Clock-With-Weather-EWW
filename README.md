# Clock-With-Weather-EWW

[![Version](https://img.shields.io/github/v/release/takattila/Clock-With-Weather-EWW?label=version)](https://github.com/takattila/Clock-With-Weather-EWW/releases)
[![CI](https://github.com/takattila/Clock-With-Weather-EWW/actions/workflows/ci.yml/badge.svg)](https://github.com/takattila/Clock-With-Weather-EWW/actions/workflows/ci.yml)

A beautiful, fully customizable **clock & weather widget** with a live
**system monitor panel** for your desktop. Runs natively on **Wayland**
(EWW + GTK layer-shell) and also works on **X11**.
Powered by the [OpenWeatherMap](https://openweathermap.org) API.

<table>
    <tr>
        <th>Dark text with light background</th>
        <th>Light text with dark background</th>
    </tr>
    <tr>
        <td><img src="./docs/images/screenshots/budapest-dark-blue.png"></td>
        <td><img src="./docs/images/screenshots/new-york-light-bg.png"></td>
    </tr>
</table>

---

## Quick Start

### 1. Get an OpenWeatherMap API key

Create a free account at [openweathermap.org](https://home.openweathermap.org/users/sign_up)
— the key arrives by e-mail.

### 2. Install

One-liner, root privileges are requested by the script (the installer is
**cross-distro**: it detects your package manager and installs **eww + all
dependencies**):

... via `curl`:

```bash
bash -c "$(curl -fsSLk https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/refs/heads/master/scripts/bin/install.sh)"
```

... or via `wget`:

```bash
bash -c "$(wget --no-check-certificate --no-cache --no-cookies -O- https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/refs/heads/master/scripts/bin/install.sh)"
```

> Tip: to skip the interactive API-key prompt, export your key first:
> `export OPENWEATHER_API_KEY=<YOUR-API-KEY>`

### 3. Start / stop / configure

```bash
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/start.sh    # start the widget
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/stop.sh     # stop the widget
bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/setup.sh    # change API key / theme / hour format
```

---

## Screenshots

### System Monitor Panel

<table>
    <tr>
        <th>With panel — theme: light-orange</th>
        <th>With panel — theme: dark-orange-bg</th>
    </tr>
    <tr>
        <td><img src="./docs/images/screenshots/panel-light-orange.png"></td>
        <td><img src="./docs/images/screenshots/panel-dark-orange-bg.png"></td>
    </tr>
</table>

### Right click on the Widgets

<table>
    <tr>
        <th>Right click</th>
        <th>Resize Weather</th>
    </tr>
    <tr>
        <td><img src="./docs/images/screenshots/context-menu-01.png"></td>
        <td><img src="./docs/images/screenshots/context-menu-02.png"></td>
    </tr>
    <tr>
        <th>Resize Panel</th>
        <th>About</th>
    </tr>
    <tr>
        <td><img src="./docs/images/screenshots/context-menu-03.png"></td>
        <td><img src="./docs/images/screenshots/context-menu-04.png"></td>
    </tr>
</table>

---

## Features

- **Clock & Weather** — time, date and live weather (temperature, icon,
  location, description, MIN/MAX/Feels) in one widget.
- **System Monitor Panel** — a side panel with real-time **CPU**, **Memory**
  and **Network Traffic** (Download/Upload) charts.
- **Dynamic Scaling** — the network charts automatically adjust their scale and
  units (KiB/s to MiB/s) based on traffic, and the active network interface is
  detected automatically.
- **Wayland native** — runs via **EWW** + GTK layer-shell; works on X11 too.
- **Light & dark ready** — supports appearance on both light and dark
  backgrounds, with a wide gallery of ready-made themes.
- **12 / 24-hour clock** — switch the hour format any time.
- **Per-widget scaling** — scale the clock and the panel independently; each
  shrinks as a single object, so the relative distances between its parts never
  change.
- **Taskbar-aware panel** — the panel aligns perfectly to your taskbar with
  per-side gaps (`panel.gap`).
- **Desktop integration** — automatic menu icons and optional desktop shortcuts.
- **Live reconfiguration** — a file watcher applies your config/theme changes
  instantly, no restart needed.

---

## How the Widget and Panel Work Together

The widget is built from **two separate but perfectly synchronized windows**:

1. **Clock & Weather** — the core component showing the time, date and weather.
2. **System Monitor Panel** — an optional side panel that snaps directly next
   to the clock and renders the live charts.

They share a **unified theme** (colors, fonts, transparency), so they always
look like a single, cohesive interface — whether you pick a light or dark theme.

---

## Themes

A wide gallery of ready-made **light** and **dark** appearance themes, plus
per-city weather themes — or define your own colors inline. See the
[configuration docs](docs/WIKI.md#configuration-configyaml) for how to switch and
customize them.

---

## Project Structure

```
Clock-With-Weather-EWW/
├── eww/                # the eww config dir: eww.yuck + eww.scss (+ generated theme files)
├── scripts/
│   ├── core/           # config / theme / watch / weather / system data scripts
│   ├── widgets/        # panel charts, context menu, About popups
│   ├── move/           # Move/Resize overlay + input daemons
│   └── bin/            # start.sh, stop.sh, install.sh, setup.sh
├── assets/
│   ├── themes/         # appearance + per-city weather YAMLs
│   ├── icons-src/      # source icons (tinted copies go to generated/)
│   └── fonts/          # bundled Noto Sans
├── docs/               # WIKI, PLAN, release notes + screenshots
├── tools/              # screenshot tooling, vendored git-filter-repo
├── tests/              # headless pytest suite
├── config.yaml         # central, commented user configuration
└── logs/  run/  charts/  generated/   # git-ignored runtime outputs
```

---

## Documentation

- **[WIKI — Technical documentation](docs/WIKI.md)** — dependencies, configuration
  (`config.yaml`), project structure, EWW/CSS customization, testing and more.
- **[PLAN — restructuring log](docs/PLAN.md)** — the executed directory
  restructure (eww/, scripts/core|widgets|move|bin/, assets/, docs/, logs/, run/)
  with verification results.
- **Screenshots** — [view all](#screenshots).

---

<p align="center">
  Made with ❤️ for beautiful desktops.
</p>