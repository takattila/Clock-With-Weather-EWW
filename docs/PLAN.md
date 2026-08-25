# Style-Aware Theme System Plan (v3.0.0)

> Executed plan behind the v3.0.0 release: per-chart colors, panel
> background/gradient, neon glow, the ready-made style themes and the
> edge-clamped theme submenu. Older plans (independent width/height resize,
> `config.local.yaml` override layer, quick-settings context menu) are
> preserved in git history and on their release pages.

## Goal

Reproduce the four desktop-mockup styles (warm sunset, neon, pastel,
metallic blue-orange) — and any future style — through the theme system
instead of hardcoded CSS:

1. every panel chart gets its own color (and the matching panel title
   follows it),
2. the panel gets its own background (solid, translucent or gradient),
3. text and chart lines can glow,
4. a gallery of ready-made style themes ships as plain YAML,
5. everything stays backward compatible: omitted keys = the pre-v3.0
   single-color look.

## Design decisions

- **Schema over CSS**: all new knobs live in `appearance.yaml` (or the
  inline `appearance` map) and flow through the existing
  `theme.py -> eww.theme.json + eww.theme.scss` pipeline, so hot-reload,
  the Theme submenu and `config.local.yaml` overrides keep working
  unchanged.
- **GTK3 CSS limits shape the features**: `text-shadow` and
  `background-image: linear-gradient()` are supported, `box-shadow` and
  gradient TEXT are not — the two-tone metallic clock comes from the
  existing hour (`color.light`) / minutes (`color.dark`) split.
- **Chart glow without SVG filters**: a wide translucent stroke painted
  UNDER the 2px line (double polyline) — renders identically on every
  gdk-pixbuf/librsvg build, no filter support required.
- **Panel colors from JSON**: `panel.py` reads the per-chart colors and the
  glow flag from `eww.theme.json`; the old `$color-light` regex stays as a
  fallback for stale generated files.
- **bg / no-bg convention**: every style ships twice — the base name is
  fully transparent, the `-bg` variant carries the backgrounds (same
  convention as `dark` / `dark-bg`). The transparent variants simply omit
  the `panel:` section and use `background.transparency: 0.0`.
- **Theme submenu overflow** (42 themes = 21 rows ≈ 640px): the ctx_menu
  window height became dynamic (`menu_h`, default 550px). `submenu.py`
  measures the pane, grows the window, clamps the pane top to the screen
  bottom and slides the whole menu up when needed — monotonic (up only),
  so row switches cannot oscillate the window.

## Implementation steps

### 1. Theme schema — `scripts/core/theme.py`

- `parse_appearance()` gained `chart.colors.{cpu,memory,net_down,net_up}`
  (default: `font.color.light`), `chart.glow` (default false),
  `panel.background.{color,transparency,gradient}` (defaults: the widget
  background / none) and `font.shadow.{color,blur}` (default: none).
- `_text_shadow_value()` builds a two-layer GTK `text-shadow` value
  (`0 0 Npx rgba(...,0.85), 0 0 2Npx rgba(...,0.45)`) from color + blur.
- `_contrast_ink()` derives `$menu-ink` / `$panel-ink` from the background
  luminance, so light-background themes (pastel family) automatically get
  a dark menu/submenu/panel ink instead of unreadable white-on-white.
- `_bg_for_text()` flips PAINTED backgrounds (alpha > 0) to a contrasting,
  hue-preserving tone when the main text would vanish on them — light text
  on a light box is exactly the failure mode of the pastel `-bg` variants
  (`pastel-bg`'s `#f5f7fa` renders as dark slate `#111822`).
- `main()` emits the new fields into `eww.theme.json` and as
  `$chart-cpu/memory/down/up`, `$chart-glow`, `$panel-bg-color/alpha/image`,
  `$text-shadow`, `$menu-ink`, `$panel-ink` into `eww.theme.scss` (the
  original 11 vars untouched).

### 2. Widget tree + styling — `eww/eww.yuck` + `eww/eww.scss`

- Per-panel title classes (`panel-title-cpu/memory/down/up`), colored from
  the matching `$chart-*` variable.
- `.panel-container` uses `$panel-bg-color/alpha` + `background-image:
  $panel-bg-image`.
- `$text-shadow` on the clock digits and `.panel-title` (none by default).
- `.sub-btn.active`: hardcoded `red` replaced with `rgba($color-light, 0.35)`.
- ctx_menu window height: `:height {menu_h}` (dynamic, default "550px"
  from `ctx.py`).

### 3. Chart generator — `scripts/widgets/panel.py`

- `load_chart_color()` → `load_chart_colors()`: per-type colors + glow flag
  from `eww.theme.json`, regex fallback.
- `render_chart(..., glow=False)`: optional wide (6px, alpha 0.25) stroke
  under the main line.

### 4. Theme submenu overflow — `submenu.py` + `ctx.py`

Two constraints discovered on the way: `eww update` cannot change
window-arg variables (`menu_h`, `pos_y`) of a RUNNING window, and the
global `_NET_WORKAREA` height is the union of all monitors — not the
monitor the menu sits on. The final mechanism therefore decides everything
at menu-open time and adapts the pane with plain (live-updatable)
variables only:

- `ctx.py` sizes the window DOWN TO THE MONITOR BOTTOM at open
  (`menu_h = monitor_h - y - margin`, floored at 550px, per-monitor height
  from the monitors JSON) and stores `menu_h` / `monitor_h` / `y` in the
  input session.
- `submenu.py` (`session_geometry()` → `open_item()`) clamps the pane top
  so its bottom stays inside the window AND above the screen bottom, and
  switches the theme picker to three columns (`sub_w` pane width follows)
  when two would not fit.
- Horizontal: `submenu.horizontal_layout()` — near the right monitor edge
  the window opens shifted left and the pane flips to the LEFT side of the
  menu column (`sub_left`, two yuck pane instances toggled by `:visible`),
  so the widest (3-column) picker never clips.
- The extra transparent window area is click-through to the same
  close_popup handler as the dismiss overlays.

### 5. Ready-made style themes — `assets/themes/appearance/`

Nine styles × two variants (18 new theme directories):

| Style | Base / `-bg` | Palette (cpu / mem / down / up) | Extras |
|---|---|---|---|
| Warm sunset | `sunset-basic(-bg)` | orange / green / magenta / blue | translucent warm panels (-bg) |
| Neon | `neon(-bg)` | orange / cyan / pink / lime | glow + text shadow, two-tone clock |
| Pastel | `pastel(-bg)` | peach / light green / pink / light blue | light translucent panels (-bg) |
| Metallic steel | `metallic-blue-orange(-bg)` | orange / sky / silver / blue | steel-blue gradient (-bg) |
| Candy pastel | `candy-pastel(-bg)` | pink / mint / lavender / peach | soft light panels (-bg) |
| Aurora | `aurora(-bg)` | green / teal / violet / blue | glow + mint text shadow |
| Techno neon | `cyberpunk(-bg)` | yellow / cyan / magenta / purple | glow + dark gradient (-bg) |
| Rose gold | `rose-gold(-bg)` | copper / champagne / dusty rose / lilac | warm shimmer shadow, plum gradient (-bg) |
| Titanium | `titanium(-bg)` | platinum / steel / silver / electric blue | dark steel gradient (-bg) |

Monochrome icon sets are tinted per theme (`icon.color`), matching the
chart palettes.

### 6. Tests

- `test_theme.py`: style-key parsing (defaults + full map) and
  `_text_shadow_value()` cases.
- `test_panel.py`: `load_chart_colors()` (JSON, SCSS fallback, default),
  `render_chart(glow=True)` double stroke, `main()` wiring.
- `test_submenu.py`: `pane_height()`, row alignment on tall screens, pane
  top clamp on short screens, window grow, upward menu slide, monotonic
  no-down guard.

### 7. Documentation

RELEASE_NOTES (v3.0.0), README (features/themes/screenshots), WIKI
(config keys, theme variables, "Creating style themes" recipe, submenu
mechanics), PLAN (this file), `config.yaml` appearance comment block.

## Verification (executed)

- `pytest tests/` — 222 passed.
- `theme.py` run for every new theme: parsed values match the design
  tables (chart colors, glow flags, panel backgrounds, gradients, shadows).
- X11/Cinnamon live test: `eww reload` clean; neon/aurora/titanium-bg
  screenshots show per-chart colors, glow strokes, gradient panels and the
  two-tone clocks; theme switching through the submenu applies live.
- Theme submenu with 42 themes, verified on BOTH monitors: the full list
  renders with nothing clipped — bottom-edge clamp + adaptive columns on
  the 768px-tall monitor, and the left-side flip next to the right-side
  panel on the 1920px one.
- Fresh context-menu screenshots captured for the README (right click,
  Resize Weather, Resize Panel, About) and a per-theme gallery added to
  `docs/SCREENSHOTS.md`.
- Wayland/KDE: no compositor-specific code paths touched (GTK CSS + SVG
  only); the window-placement helpers (`detect.py`, `start.sh`,
  `*_x11` window variants) are unchanged.
