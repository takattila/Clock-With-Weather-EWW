# Clock-With-Weather-EWW — Plan

> Feature plans beside the release they belong to. The oldest
> (independent width/height resize, `config.local.yaml` override layer,
> quick-settings context menu) are preserved in git history and on their
> release pages.

---

# v4.0.0 — Theme Editor

> Executed plan behind the v4.0.0 release: a draggable theme editor that
> edits every field an appearance definition can carry, right from the
> context menu, with a live screen eyedropper and two commit flavors
> (Save inline / Save As a new theme).

## Goal

Editing a theme today means hand-editing YAML (`appearance.yaml` / the
inline `appearance:` map) or reskinning one of the shipped themes. The editor
makes every knob visual and live:

1. open the editor from the right-click menu ("Theme editor", both widgets),
   centered on the monitor the menu was raised on,
2. every appearance leaf it editable (theme, icon set/tint/transparency,
   fonts, background, chart colors/glow, panel background/gradient,
   corner radius),
3. colors are picked from a swatch, a hex entry or the SCREEN itself
   (eyedropper), a palette strip copies theme-typical colors into the
   focused field,
4. Save commits the whole normalized appearance inline into
   `config.local.yaml` (shipped theme files untouched, watcher applies
   live); Save As creates a brand-new theme and activates it instantly,
5. the whole flow matches the existing GTK panel conventions (draft-only,
   draggable title strip, ESC / click-outside cancels).

## Design decisions

- **Keep the schema/actor split:** the editor never writes a file itself —
  it builds the same appearance maps `theme.py` parses and hands them to
  the existing writers (`config_io.save_local`), so hot-reload, the merge
  layer and the Theme picker keep working untouched.
- **Draft-only editing:** nothing is written until a footer button is
  pressed; Cancel drops the whole form. The draft is exactly the flat
  model the form renders (`to_draft`), and both commit paths re-derived
  the nested YAML from it (`normalize_appearance`).
- **Two commit flavors:**
  - *Save* → `save_inline_override()`: writes the FULL normalized map as
    the inline `appearance:` + `system.corner_radius` into the git-ignored
    `config.local.yaml`, preserving every other key. The watcher reloads
    the widget live; the theme files stay pristine.
  - *Save As* → `save_as_theme()`: asks for a name, writes a NEW
    `assets/themes/appearance/<name>/appearance.yaml` **minimalized**
    (only the non-default keys, exactly how the checked-in themes read)
    and activates it (`appearance: <name>` in `config.local.yaml`), so it
    appears in the Theme picker immediately.
- **Minimalization rule** (unchanged from the shipped themes): the
  `chart:` block is omitted entirely when all four colors equal
  `font.color.light` and `glow` is off; empty `icon.color`, inactive
  `font.shadow` and default `panel` are never written.
- **Picker on screen:** X11 owns a global pointer grab — the editor takes a
  one-time full-screen capture, shows a marginal overlay with a live hex
  readout and a 6× viewfinder, and applies the pixel under the cursor on
  click. Wayland has no global grab, so the picker degrades to a
  KDE-cursor + grim/gnome-screenshot confirmation dialog; without either it
  says so and directs you to the swatch/hex entry.

## Implementation steps

### 1. Context-menu row — `eww/eww.yuck`

- New "Theme editor" action row right after the Theme submenu row, in BOTH
  widget columns, `onclick` → `theme_ctl.py --widget ${widget} --monitor
  ${monitor}` (nohup-backgrounded), `onhover` → `submenu_hide.py`.
- The menu grows to **17 markup rows / 13 visible rows** per widget
  (was 16/12): clock `B B B S B B B S B B S B B`, panel
  `B B B S B B S B B B S B B`. Header comment updated with the new layout.

### 2. Layout math keeps its sync — `submenu.py` + `measure_menu.py`

- `ROW_SEQUENCES` (clock/panel) and `CONTEXT_ROWS` updated for the (+1)
  row: clock `units` → 8, panel `panel_enabled` → 7, `panel_alignment` → 8.
- `measure_menu.py` `ROWS = 13` and `B_ROWS` new indices, so the measured
  `menu_rows.json` stays accept.

### 3. Editor core — `scripts/move/theme_panel.py`

- Flat draft model (`FIELD_KEYS`), pure headless helpers (`normalize_hex`,
  `rgb_hex`, `pixel_color_at`, `to_draft`, `normalize_appearance`,
  `minimalize_appearance`, `validate`/`validate_draft`,
  `available_icon_sets`, `load_source`, `save_inline_override`,
  `save_as_theme`).
- `ThemePanel`: 560×760 window, title-strip drag, keyboard grab with the
  "typing" marker, per-field rows (combo / slider / spin / toggle /
  ColorField), palette strip, X11 eyedropper overlay + Wayland fallback,
  footer Cancel / Reset / Save / Save As….
- Session lifecycle identical to `weather_panel.py` (`"theme"` mode,
  `session_active()` poll, `close_popup()` on exit).

### 4. Launcher — `scripts/move/theme_ctl.py`

- Mirrors `weather_ctl.py`: resolves the monitor from `monitors.py`,
  centers 560×760 on it, closes the context menu, keeps the per-monitor
  dismiss overlays open (click-outside-to-cancel), writes the `"theme"`
  session, spawns the panel backgrounded.

### 5. Tests

- `tests/test_theme_panel.py`: hex/pixel parsing, draft round-trips,
  minimalization rules, validation, icon-set discovery, both writers
  against a temp config dir (real repo files never touched).
- `tests/test_submenu.py`: updated to 13 rows / new CONTEXT_ROWS indices.
- `suite: 333 passed` (was 297).

### 6. Documentation

- RELEASE_NOTES (v4.0.0), README (features + right-click menu + settings-window
  screenshot), SCREENSHOTS (theme-editor shot), PLAN (this file), session.py
  docstring (`"theme"` mode).

## Verification (executed)

- Headless: `pytest tests/` — 333 passed (297 baseline + 36 new editor tests).
- Runtime (X11/Cinnamon, live desktop): right-click → Theme editor centers the
  window on the same monitor; eyedropper picks a real desktop color; Save
  reloads the widget live (watcher); Save As creates a theme that appears in
  the picker; Reset/Cancel/ESC/click-outside behave like the other panels.

## Follow-up — window-stacking fix (Option A)

> The editor's own window is override-redirect (X11) / layer-shell OVERLAY
> (Wayland), so it floats above the full-monitor dismiss overlays. The native
> sub-windows it could open did NOT: the color chooser (a `Gtk.ColorButton`),
> the `ComboBoxText` popups and the Save-As dialog are ordinary windows, so
> they rendered BELOW the editor, unwinnable against the 250 ms editor
> re-raise, and every click on them was eaten by a dismiss overlay
> (click-outside → editor closes). Chosen fix: **A** — every sub-window
> floats exactly like the editor, the dismiss overlays stay (click-outside
> still works). Alternative **B** (drop the per-monitor dismiss overlays so
> no overlay can steal the clicks) was rejected: it would have left the
> editor itself unwinnable against any on-focus re-raise of the menu.

## Design decisions (Option A)

- **Every sub-window emulates the editor's stacking:** the color dialog, the
  dropdowns and the Save-As dialog all become override-redirect (X11) /
  layer-shell OVERLAY (Wayland), so they sit in the same always-on-top layer
  as the editor and never fall behind it.
- **No native transient widgets at all:** the GTK color chooser
  (`Gtk.ColorButton`/`ComboBoxText`) is replaced by an explicit dialog +
  plain painted buttons. The only way a normal (stacking-below) window can
  appear is if a stock widget is used — so none are left.
- **Child-aware re-raise:** the 250 ms editor re-raise is what starved the
  sub-windows and fed the click-outside handler. While a child is open, the
  child — not the editor — is the one kept raised.
- **Dismiss overlays unchanged:** click-outside-to-cancel keeps working;
  only the stacking of the editor's own children changes.

## Implementation steps

### 1. Rename — `eww/eww.yuck` + docs

- Menu label `"Edit theme"` → `"Theme editor"` (row + header comment) and the
  matching wording in the client-side comments / documentation.

### 2. Custom color dialog — `theme_panel.open_color_dialog`

- A `Gtk.ColorChooserDialog` configured override-redirect + keep-above (X11) /
  layer-shell OVERLAY (Wayland), modal, positioned beside the editor and
  re-raised by `tick()` while it is open.
- The swatch fields AND the palette strip become plain `Gtk.Button`s painted
  with the current color — no native chooser, so no invisible normal window
  under the editor can ever appear.

### 3. Custom dropdowns — Theme / Icon set

- The editable pairs sit in a POPUP menu window (override-redirect by
  construction) triggered from a button row; pointer-grab + click-outside
  closes it.
- Choosing an option writes straight into the draft model
  (`dropdowns_vals`), so the existing `load_widgets` / `collect_draft`
  round-trip keeps working unchanged.

### 4. `tick()` child guard

- While a child (dialog / dropdown) is open, `tick()` raises the child
  instead of the editor — the 250 ms re-raise can neither bury it nor feed
  the click-outside handler.

### 5. Save As dialog

- Same override-redirect treatment as the color dialog (identical root cause).

### 6. Tests

- Editor tests stay headless and untested by design (GTK widgets);
  `tests/test_theme_panel.py` unchanged. Suite stays at `333 passed`.

## Verification

- `pytest tests/` — 333 passed.
- Live (X11/Cinnamon): the color dialog and both dropdowns open ABOVE the
  editor, stay open when clicked (no accidental close), and ESC /
  click-outside / Save / Save As / eyedropper still behave like the other
  panels.

## Follow-up — on-screen picker rendering (found during Option A)

> While verifying the eyedropper under Option A, two latent X11 bugs surfaced:
> the picker overlay rendered a solid BLACK full-screen window (it only drew
> a corner readout + loupe and leaned on RGBA transparency, which Cinnamon
> does not honour for the POPUP), so clicking **Pick** appeared to "close the
> editor" (the editor hides while picking) with no visible picker; and the
> loupe's `cr.select_font_face("Sans", cr.FONT_SLANT_NORMAL, …)` crashed with
> `AttributeError` (those are `cairo` module constants, not context attrs).

- **`_pick_draw`** now renders the one-time full-screen capture
  (`self.pick["bg"]`) as the overlay background via
  `Gdk.cairo_set_source_pixbuf`, then draws the corner readout + 6×
  viewfinder on top — a visible picker even when the composited alpha is
  ignored, exactly matching the "one-time full-screen capture" design.
- **`_pick_x11`** stores the captured `pixbuf` (`"bg"`) and queues an initial
  draw so the first frame is not black.
- **Font constants:** `FONT_SLANT_NORMAL` / `FONT_WEIGHT_BOLD` now come from
  the `cairo` module (`import cairo`, guarded) instead of the context, fixing
  the `AttributeError` that otherwise killed the loupe/readout draw.

### Verification

- Live (X11/Cinnamon): clicking Pick shows the frozen desktop snapshot with a
  live hex readout and a 6× magnifier; clicking a pixel applies that color
  and the editor reappears; the process stays alive throughout
  (`mean brightness` of the captured overlay ≈ the desktop, not 0).
- `pytest tests/` — 333 passed.

## Follow-up — dropdown follows a dragged editor (found during Option A)

> Opening any Basics dropdown and then dragging the editor by its title bar
> left the POPUP list stranded where it had opened. `on_press` grabs the
> pointer over the editor to drag it, dropping the dropdown's own grab — so
> the dropdown stayed mapped but its position was never recomputed once
> `self.win_x/win_y` moved.

- Tracking: `_open_menu` now records `self.dropdown_open = key` (cleared in
  `_close_menu` / `_child_destroyed`).
- Reposition: `on_motion`, after `set_position(...)` moves the window and a
  dropdown is open, calls `_position_menu(self.dropdown_open)` so the POPUP
  is re-anchored to its trigger using the new `win_x/win_y` — clamped the
  same way as on open.

### Verification

- Live (X11/Cinnamon): with the Theme dropdown open, dragging the editor
  moves the dropdown by the same offset (verified in the window tree); the
  suite stays `333 passed`.

---

# Follow-up — adaptive window height + cross-monitor drag (after v4.0.0)

> The theme editor (and the Weather-settings window) should adapt to the
> current screen height — if the screen is shorter than the window, the window
> becomes as tall as the screen minus the taskbar — and it should be possible
> to drag the windows from one monitor to another.

## Design decisions

- **"Screen" = the smallest connected monitor's usable height.** Per the user's
  choice, the height basis is the *smallest-resolution monitor*; the usable
  height subtracts the taskbar via `_NET_WORKAREA` (the same work area the
  widget already respects — here a 30px top panel over all monitors). So the
  resolved height `win_h = min(natural, min(usable heights))` lets the window
  fit *every* monitor and therefore be dragged to the smallest one.
- **Sizing/centering live in the launcher** (`theme_ctl.py` /
  `weather_ctl.py`): they compute `win_h`, pass `--win-h` to the panel, and
  center using the *resolved* height (not the natural `POSE_H`/`PANEL_H`).
- **Cross-monitor drag on X11** = clamp to the union of all monitors (computed
  from `Gdk.Display.get_monitors()`), not the single monitor it opened on.
  Wayland keeps its single-monitor layer-shell clamp (best-effort only).
- **Shrunk content scrolls** instead of clipping: the theme editor already
  wrapped its body in a `Gtk.ScrolledWindow`; the Weather form now does the
  same (fields still stretch when there is room).

## Implementation steps

1. `scripts/core/monitors.py`: add `get_net_workarea()`, `usable_height(mon,
   workarea)`, `adaptive_window_height(monitors, natural_h, workarea)` and
   `desktop_bounds(monitors)`.
2. `theme_ctl.py` / `weather_ctl.py`: compute `win_h = adaptive_window_height(...)`,
   center with it, pass `--win-h`; new docstrings.
3. `theme_panel.py` / `weather_panel.py`: accept `--win-h`, store
   `self.win_h`/`self.win_w`, use them for the size request + geometry hints,
   clamp the X11 drag to the full-desktop box (`desk_*`); Weather wraps its
   fields in a scroll window; new docstrings.

## Verification

- `tests/test_monitors.py` (9 cases) covers the adaptive-height math and the
  desktop bounding box; full suite `342 passed` (was 333).
- Live (X11/Cinnamon, eDP-1 1368×768 + DP-1 1920×1080, 30px top panel): the
  theme editor opens **588×738** (not 760) and its drag moves it from monitor 0
  to monitor 1 (x 300 → 1450) instead of clamping to the origin monitor.

---

# Follow-up — live theme preview without saving (after v4.0.0)

> "Can there be a preview in the theme editor without saving?" — apply the
> settings to the live widget without clicking Save; a later Save makes the
> values permanent. Answers (chosen): a dedicated **Preview** footer button,
> **including icon re-tinting** (full fidelity), and an un-saved preview
> **reverts on Reset / Cancel / editor close**.

## The problem

Today the widget only updates through the inotify watcher (`watch.py`), which
fires ONLY when `config.local.yaml` / the theme dirs change and deliberately
ignores the runtime outputs `eww/eww.theme.json` + `eww.theme.scss` (to avoid a
reload loop). So a live preview must drive the same `theme.py` + `eww reload`
pipeline itself, from an in-memory draft, WITHOUT writing `config.local.yaml` —
and must be able to undo.

## Implementation

- `scripts/core/theme.py`: extracted `write_theme_files(config_dir, data)` so
  `theme.py:main()` and the preview worker emit the identical theme files from
  the same resolved appearance dict (single source of truth).
- `scripts/move/theme_preview.py` (NEW, detached worker):
  - `--apply <appearance.json> <radius>` → `parse_appearance` + `bg_radius` →
    `generate_icons` (re-tint) → `write_theme_files` → `eww reload` (5-attempt
    retry) → writes `generated/preview.json` marker with an undo snapshot.
  - `--restore` → regenerate from the REAL merged config (`theme.py` normal
    run) + `eww reload`, clear the marker (idempotent no-op without a marker).
  - Never touches `config.local.yaml` / the theme dirs → the watcher is NOT
    triggered, no reload loop.
- `scripts/move/theme_panel.py`:
  - New **Preview** footer button → `on_preview()` reuses `validate_draft`/font
    guards (no config write), serializes `normalize_appearance(draft)` to a temp
    JSON, spawns the worker detached, sets `preview_active`.
  - `_revert_preview()` spawns `--restore`; called from `destroy`, `tick` (covers
    ESC/click-outside), `on_close` (Cancel) and `on_reset`.
  - Save keeps its existing `config.local.yaml` path and clears `preview_active`
    (never reverts). Docstring updated.

## Verification

- `tests/test_theme_preview.py` (5 cases): apply writes the same generated
  theme files as `parse_appearance` + marker with snapshot; invalid input
  rejected; restore clears the marker and is idempotent. Plus a
  `write_theme_files` JSON/SCSS parity test in `test_theme.py`. Suite
  `348 passed` (was 342).
- Live (X11/Cinnamon): open editor → change a font/background color + an icon
  tint → **Preview** → widget + icons update within ~1–2 s; `config.local.yaml`
  remains untouched; **Cancel**/close reverts; then **Preview** + **Save**
  persists.

---

# Follow-up — Save As dialog + color chooser follow the editor (after v4.0.0)

> The Save As (and color) dialog should move together with the Theme editor
> when it is dragged. "Save As doesn't work" turned out to describe the same
> expectation: the dialog must reliably appear, take the typed theme name, and
> stay glued to the editor wherever it is dragged (clamped to the whole
> virtual desktop, so it follows onto another monitor).

## The problem

`on_motion` repositioned the editor and the open *dropdown* during a drag but
never the `self.child` *dialogs* (Save As + color chooser), which were anchored
once at open time (`_child_move` using `EDITOR_W + 12` and clamped to the
ORIGIN monitor). So a dialog stayed behind (or bounced back) when the editor
moved.

"Save As doesn't open" was a separate, harder bug: `Gtk.MessageDialog.new(...)`
is a C-only factory that PyGObject rejects on a Gtk.Dialog subclass
(`TypeError: Dialog constructor cannot be used to create instances of a
subclass MessageDialog`), so constructing the dialog always raised — the GTK
signal handler swallowed it, leaving the impression that "nothing happened".
It also used `dialog.run()`, a blocking nested main loop that fights the
editor's own session poll.

"Can't type the theme name" was the last bug: the dialog is override-redirect
(like the editor), so `present()` cannot steer the window manager into giving
it the keyboard focus. The editor's own entry fields work because they call
`Gdk.keyboard_grab` on X11 — the dialog did not.

## Implementation

- `theme_panel.py`:
  - Extracted pure `_child_position(w, h)` — CENTERS the dialog on the editor
    (`win_x + (win_w-w)//2`, `win_y + (win_h-h)//2`) and clamps to the WHOLE
    virtual desktop (`desk_*`), so dialogs follow across monitors.
    `_child_move()` now uses it.
  - `on_motion`: when a dialog child is open (not a dropdown), call
    `_child_move(self.child)` after moving the editor, so it follows the drag.
  - Save As dialog: fixed the constructor to the PyGObject builder form
    (`Gtk.MessageDialog(parent=..., flags=..., type=..., buttons=...,
    text=...)`), dropped the blocking `dialog.run()` in favour of the same
    non-blocking `connect("response")` + `present()` pattern the color dialog
    uses, and added a `_grab_dialog_keyboard` helper that does
    `Gdk.keyboard_grab(dialog.get_window(), ...)` on X11 (exactly like the
    editor's own fields) plus `entry.grab_focus()` /
    `entry.set_activates_default(True)` (Enter = OK). `_save_as_response`
    releases the grab and saves via the unchanged `save_as_theme`.
- Tests: `test_child_position_follows_editor` and
  `test_child_position_clamps_to_virtual_desktop` cover the centered follow +
  clamp math headlessly. Suite `350 passed`.

## Verification

- Live (X11/Cinnamon): `on_save_as()` returns with no TypeError; the dialog is
  centered on the editor (measured `245,362` vs editor `100,80,560,738`, i.e.
  `+(560-270)//2`, `+(738-174)//2`) — and `xdotool type rosegold` lands
  `rosegold` in the entry with `toplevel_focus: true`. Drag the editor → the
  (centered) dialog follows and lands on the target monitor; Enter writes
  `assets/themes/appearance/<name>/appearance.yaml` and the theme appears in
  the right-click Theme submenu on the next open.

---

# Style-Aware Theme System Plan (v3.0.0)

> Executed plan behind the v3.0.0 release: per-chart colors, panel
> background/gradient, neon glow, the ready-made style themes and the
> edge-clamped theme submenu. The v4.0.0 theme-editor plan sits above.

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

# Follow-up — weather widget system data: text ↔ progress bars (shipped as v4.1.0)

## Goal

Let the clock's right-click menu switch how the HDD / RAM / CPU / SWAP data
in its right-hand column is shown: the classic used/total text table, or
percentage **progress bars** — in the same spot, without changing the widget
size. Config key `system.progress_mode` (`"text"` (default) | `"progress"`).

## Design decisions

- The data stays VISIBLE in both modes (the chosen UX is a text ↔ bar format
  switch, not a show/hide) — decided with the user.
- Both views are `:visible` boxes in `widget_clock_weather` that render at
  the exact same columns/rows (x=16/176 labels, bars x=48/208, % x=148/308;
  rows y=178/192), so the natural width / geometry is identical either way —
  the watcher's `eww reload` applies the flip, no relayout needed.
- `scripts/core/system.py` now also emits `progress_{hdd,ram,cpu,swap}`
  percentages (HDD = used×100/total; RAM = `mem.percent`; CPU / SWAP =
  their existing percent). The old `hdd/ram/cpu/swap` text fields are
  unchanged, so text mode is untouched.
- The toggle reuses the proven hover-submenu pipeline:
  `submenu.py` (Rendszer row) → `menu_toggle.py` (text↔progress flip) →
  `config_set.py` (global `system.progress_mode`).
- The Rendszer row lives in the **clock** menu only; it inserts one more
  button row before the last separator, so the clock column is now **14**
  collapsed rows (panel stays 13). `CONTEXT_ROWS`, `ROW_SEQUENCES` and
  `measure_menu.py`'s `ROWS`/`B_ROWS` were updated to stay in sync.

## Tests

- `test_system.py`: `progress_*` percentages (HDD 800/1000 → 80, RAM 25,
  CPU 42, SWAP 12).
- `test_submenu.py`: Rendszer options/active, clock now 14 rows vs panel 13,
  updated row indices (Rendszer = 10) and measured-tops counts.
- `test_menu_toggle.py`: `progress_mode` flips both ways + `main()` writes.
- `test_config_set.py`: progress_mode stored as string, text/progress
  validation, global (no `--monitor`).
- `test_config.py`: default `progress_mode == "text"`.

## Verification (executed)

- `pytest tests/` — 356 passed.
- `eww --config eww reload` — clean (exit 0, no SCSS/CSS errors).
- Live (X11/Cinnamon, 1920×1080 + 1368×768): the **System** row flips the
  widget's system-data column between the text table and the percentage bars
  instantly; the widget size, geometry and the drag/scroll/monitor logic are
  unchanged by the mode.
- Screenshots: a `progress_mode: "progress"` capture of **every one of the 45
  themes** (`docs/images/screenshots/progress-<theme>.png`, cropped to the
  clock widget that carries the HDD / RAM / CPU / SWAP row) was added to
  docs/SCREENSHOTS.md, alongside the existing `progress-bars-main.png` and
  `progress-context-menu.png` hero shots; README and RELEASE_NOTES (v4.1.0)
  document the toggle.
