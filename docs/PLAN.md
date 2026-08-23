# Context Menu Actions, Editable Resize % & Hard Reset Plan

> **Status: DONE & verified** (2026-08-22, live on this machine):
> full pytest suite passes, `shellcheck` clean on the new bash script.
> This replaces the v2.1.0 local-override record — see git history for that
> document.
>
> Target release: **v2.2.0** (branch `feature/context-menu-items`).

## Phase 2: hover submenus for every selectable item (same release)

Follow-up within v2.2.0: the five selectable quick-settings rows
(AM/PM switch, Theme, Units, Panel, Side) become **hover-only parents** —
pointing at a row shows a picker pane with the possible values, the active
one highlighted; picking an entry writes it through `menu_toggle.py --value`
→ `config_set.py`. Clicking a parent row does nothing.

- **The picker renders INSIDE the ctx_menu window**: a 250px pane to the
  right of the item rows (window widened to 470x550), vertically aligned
  with the hovered row.
- Items are GROUPED with thin separators: actions (Move / Resize / Reset)
  | quick settings (AM/PM / Theme / Units / Panel / Side) | system
  (Hard reset / About). The picker's vertical offset accounts for the
  two separators (`submenu.py` ROWS map). No extra window exists at all — this removes an
  entire class of problems measured with a standalone popup window on
  X11 (invisible override-redirect copies stacking up and eating pointer
  input) and makes Wayland behave exactly like X11.
- **New `scripts/widgets/submenu.py`**: builds the option list per key
  (Theme = every directory under `assets/themes/appearance/`, split across
  two balanced columns), bakes values + active-state class + click handler
  into ONE static yuck definition pushed into the `sub_yuck` eww variable,
  rendered via `(literal ...)`, shown with `sub_show=true` /
  `sub_top=<calibrated row offset>`.
- Measured eww 0.6.0 constraints that shaped this design: handlers on
  widgets created inside `(for ...)` loops never fire; defwindow geometry
  cannot see global defvars; literal-rendered eventboxes deliver clicks but
  not hover events. All three are avoided by construction.
- Dismissal stays with close_popup.py / ctx.py (option click, outside click
  on the per-monitor dismiss layers, ESC, re-opening the menu), which also
  hides the pane. The pane lives exactly as long as its parent menu.


## Phase 3: robustness fixes (same release)

Live testing surfaced three reliability gaps, all fixed:
  * a dismissed per-monitor dismiss layer occasionally SURVIVED its close
    (the IPC close was dropped while the daemon regenerated) — an invisible
    full-screen layer then blocked every right-click on that monitor.
    close_popup.py now VERIFIES via `eww active-windows` that no popup
    window is still listed, retrying ~2s (compositor-independent, works on
    Wayland/KDE too) and force-unmapping X11 survivors;
  * About -> "Open repository": the dismiss layers stayed mapped ABOVE the
    browser on KDE/Wayland (the overlay level sits over every normal
    window), making everything unclickable; about_win.py now closes them
    right before xdg-open.
  * a Save firing on a never-initialized overlay rect (eww defaults:
    100x100 at the origin) wrote scale=MIN + top-left positions for users;
    move_ctl.py now refuses degenerate rects and any save that would place
    the widget completely off its monitor.

## Goal

Turn the right-click context menu into a real quick-settings panel and make
the Move / Resize percentage editable by hand:

1. **New context menu toggles** (all writing git-ignored
   `config.local.yaml`, applied live by the watcher):
   - `AM/PM switch` — `system.hour_format` `"24"` ↔ `"12"`
   - `Theme` — cycle through every theme under
     `assets/themes/appearance/`
   - `Units` — `weather.units` `metric` ↔ `imperial` (°C ↔ °F) with an
     immediate weather refresh (the defpoll alone would take up to 10 min)
   - `Panel shown/hidden` — `panel.enabled`
   - `Side right/left` — `panel.window.alignment`
   - `Hard reset` — factory-reset the local configuration
2. **Editable resize percentage** in the GTK Move / Resize control panel:
   the `%` label becomes a text entry (30–150 %, same clamp as +/-).
3. **`scripts/bin/hard-reset.sh`**: deletes `config.local.yaml` (no backup,
   by design) + stale session state, regenerates the theme and relayouts,
   so everything falls back to the committed `config.yaml` defaults.

## Design decisions

- **Single writer stays single**: `scripts/core/config_set.py` learns the
  new *global* keys (`hour_format`, `appearance`, `units`, `panel_enabled`,
  `panel_alignment`). No script ever writes YAML directly.
- **One orchestrator for all toggles**: new `scripts/widgets/menu_toggle.py`
  reads the merged view (`config_io.load_merged`), computes the next value
  per key semantics and delegates the write to `config_set.py`. The context
  menu buttons call it like they call `move_ctl.py`.
- **Dynamic labels** come from the existing `config` defpoll (5 s): the
  buttons show the current state (`Theme: light ▸`, `Units: °C ▸`, ...).
  Because a custom inline appearance map makes `config.appearance` an
  OBJECT, `config.py` additionally exposes a plain string
  `appearance_name` (`custom` | theme name).
- **Keyboard safety while typing**: the evdev daemon sees every physical
  key globally; without care, Enter typed in the % entry would SAVE the
  session and `-`/`+` would zoom. The session file therefore gets a
  `"typing": true` flag while the entry has focus, during which the daemon
  ignores all keys.
- **Hard reset deletes without backup** (user decision); the committed
  `config.yaml` is never touched, so nothing can get lost that matters.

## Implementation steps

### 1. `scripts/core/config_set.py` — global keys

- `--widget` becomes OPTIONAL (widget-scoped keys still require it;
  `gap_*` still requires `--widget panel`).
- New branch handled before the widget keys; none of these accept
  `--monitor`:
  | key | allowed values | stored path | type |
  |---|---|---|---|
  | `hour_format` | `12` \| `24` | `system.hour_format` | str |
  | `appearance` | existing dir under `assets/themes/appearance/` | `appearance` | str |
  | `units` | `metric` \| `imperial` | `weather.units` | str |
  | `panel_enabled` | `true` \| `false` | `panel.enabled` | bool |
  | `panel_alignment` | `right` \| `left` | `panel.window.alignment` | str |

### 2. `scripts/widgets/menu_toggle.py` (new)

- `--key {hour_format|appearance|units|panel_enabled|panel_alignment}`.
- Flip/cycle logic:
  - `hour_format`: swap `24`/`12`
  - `units`: swap `metric`/`imperial`; afterwards refresh the weather
    immediately by re-running `weather.py` with the same arguments as the
    defpoll (with the NEW units) and `eww update weather_info=<json>`
  - `panel_enabled` / `panel_alignment`: write only — the watcher's
    automatic `start.sh --relayout` applies both
  - `appearance`: next directory alphabetically (wrap-around); unknown or
    custom-map current values start the cycle at the first theme
- Prints what it wrote (same style as `config_set.py`).

### 3. `scripts/bin/hard-reset.sh` (new)

1. `rm -f config.local.yaml` and stale `generated/input_session.json`
2. best-effort `theme.py` regeneration + `start.sh --relayout`
   (harmless if the eww daemon is not running; the running watcher would
   also pick up the deletion on its own)

### 4. Context menu UI (`eww/eww.yuck`, `eww/eww.scss`)

- Final item order: Move, Resize, Reset, AM/PM switch, Theme, Units,
  Panel shown/hidden, Side right/left, Hard reset, About.
- Toggle onclicks follow the Reset pattern
  (`close_popup.py && <script>`); slower ones (units refresh) are
  backgrounded with `nohup ... &`.
- Window geometry: 4 -> 10 items means `190px` -> ~430px height and
  `180px` -> 220px width.

### 5. Editable resize %

- `scripts/move/move_ctl.py`: new action `set_scale --value <percent>`
  clamped to `MIN_SCALE..MAX_SCALE`, reusing the zoom_in/out positioning
  logic (anchored corner / panel right-gap kept fixed).
- `scripts/move/move_panel.py`:
  - `%` Gtk.Label -> Gtk.Entry (centered, ~4 chars)
  - apply on Enter (`activate`) AND on focus-out; invalid input reverts
    to the current value
  - the 250 ms `move_pct` poll never overwrites the entry mid-edit
    (`pct_editing` flag on focus-in/out)
  - focus plumbing: window accepts focus again; on X11 the override-
    redirect toplevel takes X input focus on entry click
  - writes/removes the session `"typing"` flag around edits
- `scripts/move/input_daemon.py`: in `move` mode ignore ALL keys while
  `session["typing"]` is set (ESC included — click outside the entry
  first, then ESC cancels as usual).

### 6. Tests

- `tests/test_config_set.py`: global-key coverage (string/bool coercion,
  value validation, `--monitor` rejection, missing `--widget` rejection,
  base-file untouched).
- `tests/test_menu_toggle.py` (new): flip logic for every key, theme
  cycle incl. wrap-around and custom-map fallback, units weather-refresh
  call, eww/config_set invocations mocked via monkeypatch.

### 7. Documentation

- `docs/RELEASE_NOTES.md`: rewritten for v2.2.0.
- `README.md`: context-menu feature bullets.
- `docs/WIKI.md`: menu description, new writable keys, resize entry.

## Verification (executed)

1. `pytest tests/` — **133 passed** (existing + new global-key / toggle tests).
2. `shellcheck scripts/bin/hard-reset.sh` — clean.
3. Live smoke test on this machine: `menu_toggle.py --key hour_format /
   panel_alignment / panel_enabled` flipped the values and the merged readers
   reported them within a second (`config.local.yaml` restored afterwards);
   the new yuck labels were verified with an isolated eww daemon — zero
   expression errors once the `config` defpoll is populated (the transient
   empty-var errors right after daemon start match the existing
   `config.hour_format == "12"` visibility pattern of the main widget).
4. Hard reset path reviewed step-by-step (theme regen + relayout are the same
   best-effort calls the watcher performs; safe when the widget is stopped).
