# Clock-With-Weather-EWW — v4.0.0

**A beautiful, fully customizable clock & weather widget with a live system
monitor panel for your desktop.** Runs natively on **Wayland** (EWW + GTK
layer-shell) and also works on **X11**. Powered by the
[OpenWeatherMap](https://openweathermap.org) API.

> **Recommendation: v4.0.0** — the current recommended release. Adds a
> visual **Theme editor** to the right-click menu.

**v4.0.0 adds a theme editor: theme every color without touching YAML.**
"Theme editor" next to the Theme picker opens a draggable editor (centered on
the same monitor) that edits every field an appearance definition can carry
— theme, icon set/tint/transparency, fonts, background, per-chart colors,
glow, panel background/gradient and the corner radius. Colors come from a
native swatch, a hex entry or the **screen itself** (eyedropper: on X11 a
direct cursor pick with a live magnifier; on Wayland a best-effort
KDE + screenshot flow). **Save** writes the whole appearance inline into
`config.local.yaml` (the shipped theme files stay untouched, the watcher
applies it live); **Save As** creates a brand-new theme that appears in the
Theme picker right away.

---

## What changed in v4.0.0

### New: Theme editor

- Right-click menu gains **Theme editor** (both the clock and the panel
  column), opening `theme_ctl.py` → `theme_panel.py`: a 560-wide draggable
  window centered on the monitor the menu was raised on, same session
  mechanics as the Weather-settings form (draft-only, title-strip drag,
  keyboard grab while typing, ESC / click-outside cancels).
- **Adaptive window height + cross-monitor drag** (theme editor *and*
  Weather settings): the window's height is capped to fit the **smallest
  connected screen's usable height** (monitor height minus the taskbar, via
  `_NET_WORKAREA`), so it can be placed on every monitor. On X11 the drag is
  clamped to the **whole virtual desktop** (union of all monitors) instead of
  the single monitor where it opened, so a window can be dragged from one
  monitor to another; when the shorter height clips the form, the content
  becomes scrollable (the theme editor already scrolled; the Weather form now
  wraps its fields in a scrolled window too).
- **Live theme preview** (`theme_preview.py`): the editor's new **Preview**
  footer button applies the current draft to the live widget right away —
  colors, fonts, radius, glow, panel and the re-tinted icon PNGs — **without
  saving** (`config.local.yaml` stays untouched, so only **Save** makes it
  permanent). The preview is generated from the in-memory draft via the shared
  `theme.write_theme_files` helper and reloads eww directly (the watcher is
  deliberately not involved, avoiding a reload loop). An un-saved preview
  reverts to the original look on **Reset / Cancel / closing the editor**.
- **Every appearance field** is editable: `theme`, `icon.set`,
  `icon.transparency{light,dark}`, `icon.color{light,dark}` (tint),
  `font.face`, `font.color`, `font.transparency`, `font.shadow{color,blur}`
  (glow), `background{color,transparency}`, `chart.colors{cpu,memory,net,
  up}` + `chart.glow`, `panel.background{color,transparency,gradient}` and
  `system.corner_radius`.
- **Color input three ways:** native GTK swatch, `#rrggbb` hex entry, and
  on-screen **eyedropper** — on X11 a full-screen temporary capture + pointer
  grab with a live hex readout and a 6× magnifier, applied on click; on
  Wayland a best-effort fallback (KDE cursor position + grim /
  gnome-screenshot sample in a confirmation dialog), with a graceful
  message when neither is possible. A **palette strip** up top copies the
  theme's own colors into the focused field.
- **Save** (`save_inline_override`) commits the FULL normalized appearance
  + `system.corner_radius` inline into the git-ignored `config.local.yaml`
  (preserving every other key), so the shipped
  `assets/themes/appearance/*` files stay untouched and the watcher reloads
  the widget live.
- **Save As…** (`save_as_theme`) asks for a name, writes a new minimalized
  `assets/themes/appearance/<name>/appearance.yaml` (the same "omit the
  trivial defaults" style the checked-in themes use) and activates it via
  `config.local.yaml`, so it shows up in the Theme picker immediately.
- **Child dialogs follow the editor** — the **Save As** name prompt and the
  color chooser are **centered on the editor** and re-anchored whenever it is
  dragged, clamped to the **whole virtual desktop** (like the editor itself),
  so they come along to whichever monitor the editor lands on. The Save As
  dialog also **opens and types reliably**: its constructor was fixed (a
  `Gtk.MessageDialog.new` call that always raised a PyGObject `TypeError`,
  making the prompt never appear), it now uses the same non-blocking
  `response` + `present()` pattern as the color dialog, and it takes the
  keyboard focus via `Gdk.keyboard_grab` exactly like the editor's own entry
  fields (so the name is typed straight in; Enter saves).
- **Reset** refills the form from the loaded source; **Cancel** discards.
  Every commit is validated first (`#rrggbb`, 0–1 transparencies, blur /
  radius bounds, single-line gradient, no quotes in the font name).
- The context menu grows to **13 visible rows** per widget (17 markup rows);
  the submenu-picker math and the row-measurer were updated to match.

### Fixed

- **The X11 eyedropper now actually shows its live "Color preview".** The
  picker overlay used a stock GTK `POPUP` window, which this Cinnamon/X11
  setup never composites over the desktop — the frozen snapshot, the swatch,
  the hex readout and the magnifier simply did not appear ("clicking Pick
  looked like the editor just closed"). It is now a borderless full-screen
  `TOPLEVEL` (`override-redirect`, keep-above, skipped by the taskbar and
  pager) that truly covers the virtual desktop, so the frozen capture and
  the live readout render on X11.
- **The preview follows the pointer live on X11, exactly like Wayland.** A
  background poll thread (via `xdotool`) tracks the cursor and updates the
  top-left "Color preview" swatch + hex even without constant motion events.
  Wayland is untouched — its layer-shell overlay, its KDE-cursor polling and
  its placement are unchanged.
- **Multi-monitor:** the "Color preview" pins to the top-left of the screen
  the cursor is currently on (not the virtual-desktop origin), so on a
  side-by-side monitor setup the readout stays on the screen being sampled.

### Upgrade from v3.1.1

1. Pull / check out `v4.0.0`.
2. Restart the widget: `bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/start.sh`.
3. Right-click a widget → **Theme editor**. Nothing else to do — your themes
   and `config.local.yaml` keep working unchanged. The editor's own
   `window-theme-editor.png` screenshot is in the README / SCREENSHOTS.

---

# Clock-With-Weather-EWW — v3.1.1

**v3.1.1 fixes the hover picker alignment.** Every time the context menu opens
it now measures its own real row positions and anchors the hover picker
(Theme / AM/PM / °C/°F / Panel / Side) to those pixels, instead of assuming
per-row heights that drift with the desktop's fonts and DPI.

---

## What changed in v3.1.1

### Fixed

- **The hover picker stays on its parent row.** The old code positioned the
  picker with assumed row heights (42 px actions + 15 px separators); real
  desktops render them differently (here: a uniform ~38 px), so the picker sat
  too high — the further down the row, the worse. The menu now measures its
  actual layout every time it opens (`measure_menu.py`) and lines the picker up
  with the real row top. When measuring isn't possible, the previous behavior
  is kept.
- The Theme picker's on-screen fit still holds with 40+ themes: when the list
  is too tall to start at its row it clamps to the screen bottom edge as
  before, only now computed from the measured geometry.

### Upgrade from v3.1.0

1. Pull / check out `v3.1.1`.
2. Restart the widget: `bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/start.sh`.
3. Nothing else to do — the fix is automatic; your themes and
   `config.local.yaml` keep working unchanged.

---

# Clock-With-Weather-EWW — v3.1.0

**v3.1.0 makes the right-click context menu a full settings center and adds
dedicated control windows for the weather and the panel gap**, plus a single
universal ESC that closes every popup. The context menu itself gets several
fixes that make it behave identically on KDE/Wayland and Cinnamon/X11.

---

## What changed in v3.1.0

### New: Weather settings window

`Weather` in the clock's context menu opens a draggable GTK form (centered on
the same monitor) that edits the **city, language code, display language,
units (°C/°F), API URL and API key** as a draft. **Save** validates and
commits the changed values in one go (`config.local.yaml` + the `.api_key`
file) and refreshes the weather instantly — no 10-minute config-poll wait.
**Reset** drops the local weather overrides so the `config.yaml`/theme
defaults win again.

### New: Panel gap control window

`Panel gap` in the panel's context menu opens a draggable control window next
to the panel widget (10px away, on the side with more free space — like the
Move/Resize window). It edits the **top / right / bottom / left** spacing
between the panel and the screen / taskbar edges (`panel.gap`): `+`/`−`
steppers and typed values only change the draft, and **Save** commits them all
in one go.

### New: one universal ESC

The input daemon now treats ESC as global and mode-agnostic: it closes the
context menu, any picker pane, the dismiss layers and the control windows
from **every** mode — and while Move / Resize is editing geometry it
**cancels that editing** (even mid-typing) instead of closing everything.

### Changed: context menu quality

- **The picker never opens by itself.** Opening the menu resets the pane state
  (`sub_show=false` / empty `sub_yuck`), and the close paths clear it too — the
  last hovered picker (e.g. AM/PM) no longer reappears on the next right-click.
- **The pane never gets stuck.** Every row without a submenu (Move / Resize /
  Reset / Weather / Panel gap / Hard reset / About) hides a still-open picker
  when the pointer enters it. These rows are `eventbox`es because eww buttons
  never fire `:onhover`.
- **Same width on every compositor.** The menu column is pinned to a fixed
  290px (= `MENU_COL_W`) and the window to 1040px (375 + 290 + 375). The old
  window sized itself from the label text, which GTK measures differently
  under KDE/Wayland (narrower) and Cinnamon/X11 (wider).
- The rows are regrouped per widget: the clock menu shows Move / Resize /
  Reset / AM/PM / Theme / Units / Weather / Hard reset / About; the panel menu
  Move / Resize / Reset / Theme / Panel / Side / Panel gap / Hard reset /
  About.
- Move / Resize and the new control windows open beside the widget (10px gap,
  the side with more free space) instead of centered over it.

### Fixed

- The context menu and the hover picker could open at slightly different
  sizes/positions depending on the compositor.
- Hovering between submenu rows could leave a picker pane dangling after the
  pointer moved onto an action row.

### Upgrade from v3.0.0

1. Pull / check out `v3.1.0`.
2. Restart the widget: `bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/start.sh`.
3. Nothing else to do — the new windows and the menu fixes are additive; your
   themes and `config.local.yaml` keep working unchanged.

---

## Screenshots (v3.1.0)

| Main display |
|---|
| ![Main display](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/main-display.png) |

| Right click (no picker) | Theme picker |
|---|---|
| ![Right click](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/context-menu-open.png) | ![Theme picker](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/context-menu-theme.png) |

| Weather settings | Move / Resize |
|---|---|
| ![Weather settings](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/window-weather-settings.png) | ![Move / Resize](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/window-move-resize.png) |
| **Panel gap** | **About** |
| ![Panel gap](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/window-panel-gap.png) | ![About](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/window-about.png) |

---

---

# Clock-With-Weather-EWW — v3.0.0

**A beautiful, fully customizable clock & weather widget with a live system
monitor panel for your desktop.** Runs natively on **Wayland** (EWW + GTK
layer-shell) and also works on **X11**. Powered by the
[OpenWeatherMap](https://openweathermap.org) API.

**v3.0.0 turns the theme system style-aware**: every panel chart (CPU /
Memory / NET Down / NET Up) can have its own color, the panel gets its own
background (solid or gradient), and text can glow. Nine ready-made style
themes showcase the new possibilities — **sunset-basic**, **neon**,
**pastel**, **metallic-blue-orange**, **candy-pastel**, **aurora**,
**cyberpunk**, **rose-gold** and **titanium** — each in two variants: a
transparent base version and a `-bg` version with visible widget/panel
backgrounds. Everything is optional: existing themes and configs keep
working exactly as before.

---

## What changed in v3.0.0

### New: style-aware theme system

The `appearance` definition (theme YAML or inline map) accepts four new,
optional sections:

| New key | Effect | Default (omitted) |
|---|---|---|
| `chart.colors.{cpu, memory, net_down, net_up}` | per-chart line/fill color | all charts use `font.color.light` (the pre-v3.0 behavior) |
| `chart.glow` | neon glow under the chart lines (wide translucent stroke painted below the 2px line) | `false` |
| `panel.background.{color, transparency}` | the system panel's own background, independent of the widget background | falls back to `background.color` / `background.transparency` |
| `panel.background.gradient` | GTK CSS gradient as the panel background image, e.g. `linear-gradient(to bottom, #1b3a5c, #0d1f33)` | none |
| `font.shadow.{color, blur}` | neon text glow (two-layer GTK `text-shadow`) on the clock digits and the panel titles | no shadow |

The matching panel **titles follow their chart color** (CPU title orange,
MEMORY title green, ... in the style themes), and the generated
`eww.theme.scss` gained the `$chart-*`, `$panel-bg-*` and `$text-shadow`
variables (documented in the
[WIKI](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/docs/WIKI.md)).

### New: eighteen ready-made style themes (9 styles x 2 variants)

Each style comes as a transparent base theme and a `-bg` variant with
visible widget/panel backgrounds (the same convention as `dark` /
`dark-bg`):

| Style | Base (transparent) | With background | Palette (cpu / memory / net down / net up) |
|---|---|---|---|
| Warm sunset | `sunset-basic` | `sunset-basic-bg` | orange / green / magenta / blue |
| Cyberpunk neon (glowing charts, two-tone cyan-pink clock) | `neon` | `neon-bg` | orange / cyan / pink / lime |
| Soft pastel | `pastel` | `pastel-bg` | peach / light green / pink / light blue |
| Metallic steel (gradient panels) | `metallic-blue-orange` | `metallic-blue-orange-bg` | orange / sky / silver / blue |
| Candy pastel | `candy-pastel` | `candy-pastel-bg` | pink / mint / lavender / peach |
| Aurora glow (glowing charts + text) | `aurora` | `aurora-bg` | green / teal / violet / blue |
| Techno neon (glowing charts + text) | `cyberpunk` | `cyberpunk-bg` | yellow / cyan / magenta / purple |
| Rose gold metallic (shimmer glow, gradient) | `rose-gold` | `rose-gold-bg` | copper / champagne / dusty rose / lilac |
| Titanium metallic (gradient panels) | `titanium` | `titanium-bg` | platinum / steel / silver / electric blue |

Pick them from the right-click Theme submenu like any other theme — new
themes under `assets/themes/appearance/` are picked up automatically.

### Changed

- The panel chart generator reads the per-chart colors (and the glow flag)
  from `eww.theme.json`; the `$color-light` regex remains as a fallback for
  older generated files.
- The active-value highlight of the right-click submenu
  (`.sub-btn.active`) used a hardcoded red; it now follows the theme's
  light font color.
- **The right-click Theme submenu never clips anymore.** With 40+ themes
  the picker is now edge-aware: the context-menu window is sized down to
  the monitor bottom at open time, the picker clamps to the bottom screen
  edge and adds a third column when the list is too tall, and near the
  right screen edge it flips to the LEFT side of the menu — every column
  stays fully visible on every monitor, on either widget.

### Fixed

- **Light widget elements no longer sit on light backgrounds.** When a
  theme's main text would vanish on its own painted background (light text
  on a light box — e.g. the pastel `-bg` variants), `theme.py` flips that
  background to a contrasting, hue-preserving tone (`pastel-bg`'s
  `#f5f7fa` renders as dark slate `#111822`). Only painted backgrounds are
  affected; fully transparent themes are untouched.
- **Light-background themes keep the context menu, submenu and panel
  status text readable.** The menu/submenu ink used to follow
  `font.color.light` unconditionally — white text on the white menu
  background of the pastel-style themes. `theme.py` now derives the ink
  from the background luminance (`$menu-ink` / `$panel-ink`): dark
  backgrounds keep the classic light ink, light backgrounds flip to a
  dark gray automatically. No theme key needed; existing themes are
  pixel-identical.

### Upgrade from v2.x

1. Pull / check out `v3.0.0`.
2. Restart the widget: `bash ~/.eww/Clock-With-Weather-EWW/scripts/bin/start.sh`.
3. Nothing else to do — every new appearance key is optional and falls back
   to the previous behavior, so your existing themes and
   `config.local.yaml` keep working unchanged. Try the new style themes
   from the right-click menu's Theme submenu.

---

## Screenshots

| Sunset basic | Sunset basic — bg |
|---|---|
| ![Sunset basic](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-sunset-basic.png) | ![Sunset basic bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-sunset-basic-bg.png) |

| Neon | Neon — bg |
|---|---|
| ![Neon](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-neon.png) | ![Neon bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-neon-bg.png) |

| Pastel | Pastel — bg |
|---|---|
| ![Pastel](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-pastel.png) | ![Pastel bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-pastel-bg.png) |

| Metallic blue-orange | Metallic blue-orange — bg |
|---|---|
| ![Metallic blue-orange](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-metallic-blue-orange.png) | ![Metallic blue-orange bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-metallic-blue-orange-bg.png) |

| Candy pastel | Candy pastel — bg |
|---|---|
| ![Candy pastel](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-candy-pastel.png) | ![Candy pastel bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-candy-pastel-bg.png) |

| Aurora | Aurora — bg |
|---|---|
| ![Aurora](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-aurora.png) | ![Aurora bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-aurora-bg.png) |

| Cyberpunk | Cyberpunk — bg |
|---|---|
| ![Cyberpunk](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-cyberpunk.png) | ![Cyberpunk bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-cyberpunk-bg.png) |

| Rose gold | Rose gold — bg |
|---|---|
| ![Rose gold](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-rose-gold.png) | ![Rose gold bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-rose-gold-bg.png) |

| Titanium | Titanium — bg |
|---|---|
| ![Titanium](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-titanium.png) | ![Titanium bg](https://raw.githubusercontent.com/takattila/Clock-With-Weather-EWW/master/docs/images/screenshots/theme-titanium-bg.png) |

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
- **Style-aware theming** — per-chart colors, panel background with optional
  gradient and neon text/chart glow; nine ready-made style themes
  (sunset-basic, neon, pastel, metallic-blue-orange, candy-pastel, aurora,
  cyberpunk, rose-gold, titanium), each in a transparent and a `-bg`
  variant, showcase it.
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

- `appearance` — a theme name (`light`, `dark`, `neon`, `pastel`, ...) or a
  custom inline appearance map (fonts, colors, icon set + tint, transparency,
  background, per-chart colors, panel background/gradient, text shadow).
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

A wide gallery of ready-made **light** and **dark** appearance themes — now
including the nine **style themes** (`sunset-basic`, `neon`, `pastel`,
`metallic-blue-orange`, `candy-pastel`, `aurora`, `cyberpunk`, `rose-gold`,
`titanium`, each in a transparent and a `-bg` variant) with per-chart colors,
gradient panel backgrounds and glow — plus per-city weather themes
(`assets/themes/weather/<name>/weather.yaml`). Or define your own colors
inline in `config.yaml` (or locally override them in `config.local.yaml`
without touching the tracked defaults). Pick any of them from the
right-click menu's Theme submenu; see the WIKI's "Creating style themes"
section for the full recipe.

## Documentation

- **[README](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/README.md)**
  — overview, screenshots and quick start.
- **[SCREENSHOTS](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/docs/SCREENSHOTS.md)**
  — gallery of all 42 themes plus the context menu in action.
- **[WIKI](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/docs/WIKI.md)**
  — dependencies, version-change risks, `config.yaml` reference, project
  structure, EWW/CSS customization, style themes and testing.
- **[PLAN](https://github.com/takattila/Clock-With-Weather-EWW/blob/master/docs/PLAN.md)**
  — the executed plan behind the style-aware theme system.

## Compatibility

- **Wayland** (KDE Plasma tested) — EWW + GTK layer-shell.
- **X11** (Linux Mint / Cinnamon tested) — EWW absolute-coordinate placement.
- Every v3.0.0 style feature (per-chart colors, gradient panel background,
  text/chart glow) is plain GTK3 CSS + SVG rendering, identical on both
  compositors — verified on X11/Cinnamon and Wayland/KDE.
- Python 3.11+, **eww 0.6.0 recommended** (0.5.0+ works), `PyYAML`,
  `psutil`, `requests`, `pillow` (see the WIKI for the full dependency
  table).

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
> [v2.3.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v2.3.0),
> [v2.2.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v2.2.0),
> [v2.1.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v2.1.0),
> [v2.0.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v2.0.0),
> [v1.0.0](https://github.com/takattila/Clock-With-Weather-EWW/releases/tag/v1.0.0).
