# Clock-With-Weather-EWW — v2.3.0

**A beautiful, fully customizable clock & weather widget with a live system
monitor panel for your desktop.** Runs natively on **Wayland** (EWW + GTK
layer-shell) and also works on **X11**. Powered by the
[OpenWeatherMap](https://openweathermap.org) API.

**v2.3.0 lets you resize width and height independently**: the Move / Resize
dialog gained Width and Height rows (each with − / editable % / +), edge
drags resize a single axis and Shift+arrows do it from the keyboard — while
the classic proportional resize (+/-, corner drag) stays exactly as it was.
Both widgets support it, and each monitor remembers its own width/height
scales.

---

## What changed in v2.3.0

### New: independent width / height resize

The Move / Resize control panel now has THREE resize rows:

| Row | Buttons | Typed % action | Effect |
|---|---|---|---|
| *(unlabeled)* | − / + | `set_scale` | proportional zoom, aspect ratio preserved (as before) |
| **W** | − / + | `set_scale_x` | **width only** |
| **H** | − / + | `set_scale_y` | **height only** |

- Every percentage is an editable field (30–150%, same clamp as before):
  type a value and press Enter or leave the field; invalid input snaps back.
  While you type, the keyboard daemon still steps aside (no accidental
  Enter = Save).
- The anchored edge stays fixed: the panel grows/shrinks leftward from its
  right gap on W changes; the clock realigns to its anchor per axis.
- New keyboard shortcuts (evdev daemon): **Shift+Up/Down** = height ±,
  **Shift+Right/Left** = width ±. Plain arrows still move, +/- still zoom
  proportionally.
- Mouse resizing on the overlay rectangle: **corner drag keeps the aspect
  ratio**, **edge drags resize a single axis** (left/right = width,
  top/bottom = height).

Both the clock and the system panel support everything above; each monitor
stores its own values.

### New config keys: `scale_x` / `scale_y`

A Save that changed the axes independently writes `scale_x` (= width scale)
and `scale_y` (= height scale) into the per_monitor entry of
`weather.window` / `panel.window`, e.g.:

```yaml
panel:
  window:
    per_monitor:
      0: { position_x: 0, position_y: 0, scale_x: 1.00, scale_y: 0.80 }
```

Each axis falls back to the shared `scale` when missing, so existing configs
keep working unchanged — no migration needed. The classic `scale` key is
still written (mirroring the width axis) for older external tooling.

### Changed

- **Single-instance process management + orphan cleanup.** Repeated widget
  restarts used to accumulate orphaned background helpers (measured: 4x
  config watcher, 4x monitor watcher and 2x keyboard daemon pairs after one
  day — ~95 MB of wasted RAM): `stop.sh` killed only the newest instance via
  its pidfile, and the input daemon had no stop path at all. A shared,
  ancestor-protected pattern sweep (`scripts/bin/process_sweep.sh`) now runs
  on start, stop and lazy daemon spawn, so exactly one instance of each
  helper stays alive (verified with a double-start test). Total related RSS
  dropped from ~272 MB to ~95 MB; the GUI daemon itself idles at ~55 MB and
  0% CPU.
- `scripts/move/move_ctl.py`: new actions `zoom_in_x` / `zoom_out_x`,
  `zoom_in_y` / `zoom_out_y`, `set_scale_x` / `set_scale_y`; Reset clears
  position and writes all three scale keys to 1.0; Save persists per-axis
  scales.
- `scripts/move/widget_rect.py`: reports the natural (100%) size for BOTH
  widgets and computes the rectangle with independent axis scales.
- `scripts/move/move_panel.py`: the resize entries share one refactored
  `PctField` implementation; the panel is slightly taller to fit the new rows.
- `eww.yuck` + `start.sh`: windows are scaled with separate X/Y percentages
  (`main_scale_perc_x/y`, `panel_scale_perc_x/y`); the panel's anchored-edge
  translate uses its own axis.
- The Move/Resize session publishes a second percentage variable
  (`move_pct_h`) so both fields always show live values.

### Fixed

- **The context menu now opens instantly.** Ownership resolution and menu
  placement used to spawn 6 helper processes (each re-running the slow
  monitor enumeration and config/YAML parsing), costing ~3.5 s before the
  menu appeared. Everything runs in a single process now, with a short-TTL
  monitor cache and in-process config/font caches: ~0.3 s cold,
  imperceptible afterwards. `menu_pos.py` exposes the placement as a
  reusable function; hotplug invalidates the cache.
- **Moving the panel and pressing Save silently did nothing.** The off-screen
  safety check validated the panel's saved POSITION OFFSETS as if they were
  absolute screen coordinates — every drag AWAY from the anchored edge
  produces a negative offset and was therefore refused invisibly (stderr is
  discarded by design). The check now validates the dragged rectangle itself,
  Save/Cancel run synchronously with inline error feedback in the control
  panel, and `move_ctl.py` appends every action + refusal to
  `logs/move_ctl.log` for future diagnosis.
- **Right-clicking a widget partially covered by the other one opened the
  wrong menu** (e.g. clicking the clock where it slid under the panel's
  transparent bottom strip opened the panel's Move/Resize rectangle). The
  context-menu opener now checks which widget is VISIBLE under the cursor and
  forwards accordingly, so the rectangle always matches the widget you aimed
  at.
- **Right-click stopped working after using Move / Resize until restart.**
  The invisible per-monitor dismiss layers are intentionally kept open for
  the whole move/resize session (click-outside-to-cancel), but ending the
  session with Save / Cancel / Reset — or Enter / ESC on the keyboard — only
  cleared the session file: an invisible full-screen layer stayed above the
  widget and swallowed every further click. The session teardown now closes
  the popup stack itself, and popup closing additionally discovers orphaned
  overlays by instance id from `eww active-windows`, so leftovers can be
  cleaned even when their session file is already gone.
- **Resizing above 100% no longer clips the widget, and shrunken widgets can
  finally be parked at the screen edges.** The eww window is a fixed-size
  transparent canvas whose drawing is scaled visually; the canvas itself used
  to stay at the natural (100%) size — so an enlarged widget was cut off at
  its old bounds, and a shrunken one dragged to e.g. the bottom-right corner
  made the oversized invisible canvas overflow the monitor, which the window
  manager then relocated (dragging the visible widget away from where the
  resize rectangle showed it). The canvas now grows above 100%, and below
  100% it is positioned to always fit while a transform translate places the
  scaled content exactly on the saved rectangle — for both widgets.
- Removed duplicated GTK handler definitions in `scripts/move/move_panel.py`
  (`on_pct_button_press` / `on_pct_focus_in` existed twice since v2.2.0;
  Python silently kept the second copy).

### Upgrade from v2.x

1. Pull / check out `v2.3.0`.
2. Restart the widget: `bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/start.sh`.
3. Nothing else to do — your existing `config.local.yaml` keeps working; the
   new axis scales appear there automatically after the first non-proportional
   Save.

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
- **Quick-settings context menu** — hover AM/PM, theme, °C/°F, panel
  show/hide or side flip to pick the value from an inline submenu, plus a
  factory "Hard reset"; everything applied live through the git-clean local
  override layer.
- **Independent width / height resize** — resize proportionally, or stretch
  only the width / only the height via dedicated dialog rows (with hand-typed
  exact percentages), Shift+arrows or single-axis edge drags; every monitor
  remembers its own scales.
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
  ± steppers *and* hand-typed exact percentages in the Move / Resize dialog.
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
  alignment, and **per-monitor** `position_x` / `position_y` / `scale`
  (+ optional independent `scale_x` / `scale_y`).
- `system` — hour format (`24`/`12`) and background corner radius.
- `panel` — enable/disable the system panel, alignment, per-monitor offsets,
  and the taskbar `gap` baseline.

The right-click context menu lets you **Move / Resize / Reset** each widget
and pick the most common settings (hour format, theme, units, panel state /
side) from hover submenus directly on screen; the resulting values are
written into `config.local.yaml` and applied live by the file watcher — so
the repository stays clean unless you deliberately edit a default.
`hard-reset.sh` (or the menu's "Hard reset") deletes that local file and
returns everything to the committed defaults.

## Themes

A wide gallery of ready-made **light** and **dark** appearance themes plus
per-city weather themes (`assets/themes/weather/<name>/weather.yaml`) — or define
your own colors inline in `config.yaml` (or locally override them in
`config.local.yaml` without touching the tracked defaults). Pick any of them
from the right-click menu's Theme submenu.

## Documentation

- **[README](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/README.md)**
  — overview, screenshots and quick start.
- **[WIKI](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/docs/WIKI.md)**
  — dependencies, version-change risks, `config.yaml` reference, project
  structure, EWW/CSS customization and testing.
- **[PLAN](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/docs/PLAN.md)**
  — the executed plan behind the independent width/height resize.

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
> [v2.2.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v2.2.0),
> [v2.1.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v2.1.0),
> [v2.0.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v2.0.0),
> [v1.0.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v1.0.0).
