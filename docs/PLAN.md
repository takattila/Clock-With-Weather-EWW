# Independent Width / Height Resize Plan

> **Status: DONE & verified** (2026-08-23):
> full pytest suite passes (160 tests), every touched Python file
> `py_compile`s clean and `bash -n` passes on `start.sh`.
> This replaces the v2.2.0 context-menu record — see git history for that
> document.
>
> Target release: **v2.3.0**.

## Goal

Until now every resize path shared ONE scale factor per widget and monitor
(`weather.window.per_monitor[N].scale` / `panel.window.per_monitor[N].scale`),
so the aspect ratio was always preserved. This release adds **axis-independent
resizing** for BOTH widgets (clock + system panel):

1. **Width only** — increase/decrease the width without touching the height.
2. **Height only** — increase/decrease the height without touching the width.

while keeping every existing proportional behavior intact (+/- buttons,
corner drag, hand-typed percentage).

## Design decisions

- **Two scale factors per monitor**: Move/Resize Save writes `scale_x`
  (= dragged_width / natural_width) and `scale_y` (= dragged_height /
  natural_height) into the per_monitor entry, plus a `scale` mirror of
  `scale_x` so older readers keep working. Readers resolve each axis as
  `scale_x -> scale -> 1.0` (`config.py::resolve_axis_scales`), so existing
  configs that only carry `scale` scale both axes uniformly — no migration
  needed.
- **Single shared session state gains one variable**: `move_pct_h` (height %)
  next to `move_pct` (width %). The GTK control panel polls both; they differ
  after any single-axis operation.
- **Anchoring rules per touched axis** (the other axis keeps its previous
  position so W and H steps compose freely):
  - width change: panel keeps its right gap fixed (`x = frame_w - right_gap -
    w`, grows/shrinks leftward); clock realigns horizontally to its anchor +
    position_x;
  - height change: clock realigns vertically to its anchor + position_y;
    panel keeps y (top/gap-derived baseline — same as the proportional path
    always did).
- **Mouse semantics on the overlay rectangle**: corner drags stay aspect-
  preserving; EDGE drags become single-axis (left/right = width, top/bottom =
  height) — matching common resizer UX.
- **Keyboard**: Shift+Arrow = single-axis zoom in the evdev daemon
  (Shift+Up/Down height ±, Shift+Right/Left width ±); plain arrows still move,
  +/- stays proportional. The daemon already tracked the shift state.
- **UI stays one dialog**: the Resize section of `move_panel.py` grows to
  three rows — unlabeled proportional row (kept from v2.2.0), "W" row,
  "H" row — each with − / editable-% / + . The entry plumbing (typing flag,
  X11 keyboard grab, poll-overwrite guard, duplicated in the old code twice)
  is factored into one `PctField` class used three times.

## Implementation steps

### 1. Config layer — two independent scales

- `scripts/core/config.py`: new merged keys `scale_x` / `scale_y` (clock) and
  `panel_scale_x` / `panel_scale_y` (panel), resolved per monitor through
  `resolve_axis_scales(entry, fallback_x, fallback_y)` with the chain above;
  legacy `scale` / `panel_scale` keys unchanged.
- `scripts/core/config_set.py`: accepts `scale_x` / `scale_y` as widget-scoped
  per-monitor float keys (same validation/coercion as `scale`).
- `config.yaml`: documents the optional keys under both per_monitor sections.

### 2. Geometry source — `scripts/move/widget_rect.py`

- Reports `natural_w` / `natural_h` for BOTH widgets (the panel's natural
  size is `PANEL_WIDTH` x gap-derived layout height; previously only the
  clock reported them and move_ctl reverse-engineered the panel base from the
  single scale).
- `clock_rect()` / `panel_rect()` compute width with the x-axis scale and
  height with the y-axis scale.

### 3. Actions — `scripts/move/move_ctl.py`

- New actions: `zoom_in_x` / `zoom_out_x`, `zoom_in_y` / `zoom_out_y`,
  `set_scale_x` / `set_scale_y` (exact % via --value). The existing
  `zoom_in` / `zoom_out` / `set_scale` stay proportional (both axes).
- Current per-axis scales come from the live session rectangle
  (`move_w/base_w`, `move_h/base_h`) so repeated steps compose; clamp stays
  0.3..1.5 per axis.
- Only the touched dimension is recomputed and re-anchored (rules above);
  every resize action writes move_w/move_h + move_pct/move_pct_h together.
- `save`: writes `scale_x`, `scale_y` AND `scale` (= scale_x mirror);
  off-screen/degenerate guards unchanged (they already validate w/h
  separately).
- `reset`: clears position and writes `scale` / `scale_x` / `scale_y` = 1.00.

### 4. Session plumbing — move.py / move_rect.py / input_daemon.py

- `move.py`: seeds `move_pct_h` next to `move_pct` from the rect vs natural
  sizes; control-panel height constant MC_H 250 -> 320.
- `move_rect.py`: per-axis press state (`s0x`/`s0y`); `_resize_to` scales a
  single axis on edge drags and both on corners; `flush()` also publishes
  `move_pct_h`.
- `input_daemon.py`: Shift+arrow mapping (checked before the plain-arrow
  moves).

### 5. Control panel UI — `scripts/move/move_panel.py`

- Three-row Resize section built by a small `pct_row()` helper; each row's
  editable entry is a `PctField(varname, action)` instance handling its own
  typing flag, X11 grab, select-all-on-click, Enter/focus-out apply and poll
  refresh.
- Removes the accidentally duplicated `on_pct_button_press` /
  `on_pct_focus_in` definitions (present twice since v2.2.0).
- `.axis-label` CSS class for the W/H row labels.

### 6. Render path — eww.yuck + start.sh

- `eww.yuck`: `(defvar move_pct_h 100)`; `widget_clock_weather` /
  `widget_panel` and all four defwindows take separate
  `*_scale_perc_x` / `*_scale_perc_y` arguments feeding
  `transform :scale-x` / `:scale-y`.
- `start.sh`: reads `scale_x` / `scale_y` (+ panel variants), opens the
  windows with the split percentages; `panel_translate_x = 250*(1/scale_x-1)`
  and bottom-anchor `panel_translate_y = ph*(1/scale_y-1)` use their own axis.

### 7. Tests

- `tests/test_config.py`: axis defaults (1.0), inheritance from the shared
  per-monitor `scale`, and independent overrides via config.local.yaml.
- `tests/test_config_set.py`: scale_x/scale_y writes for clock + panel
  (float coercion, per-monitor paths) and invalid-value rejection.

## Follow-up fix: canvas geometry (clipping + edge placement)

Live testing of the feature surfaced two rendering bugs with one shared root
cause: the eww window (a fixed transparent canvas) stayed at the NATURAL
size while the transform only scaled the drawing inside it.

  * above 100% the enlarged drawing was clipped at the canvas bounds;
  * below 100% a widget parked near a screen edge made the oversized
    invisible canvas overflow the monitor — the X11 WM then relocated the
    managed window, so the visible widget landed away from where the
    Move/Resize rectangle showed it (measured: target (1692,880), actual
    (1291,833) = exactly the overflow).

A probe window proved GTK propagates child minimum sizes to the toplevel,
so shrinking the canvas below 100% is impossible while any inner element
requests natural pixels. Fix (both widgets), per axis:

    canvas     = max(natural, visible)          # >100%: no clipping
    canvas_tl  = clamp(visible_tl, 0, frame - canvas)
    translate  = visible_tl - canvas_tl          # 0 when visible >= natural

`widget_rect.py` publishes the new render keys (`win_*`, `translate_*`,
everything int-rounded); `start.sh` passes them and computes the panel's
edge-hug translates as plain natural−visible differences gated at 0 (an
X11 pixel probe showed eww applies transform :translate AFTER scaling, in
device pixels — the old `nat*(1/scale-1)` formulas were slightly off).
Verified numerically for corner/center/overscale/mixed-axis cases
(canvas always fits, content always lands on the visible rectangle);
live check after restart.

## Follow-up fix: dead right-click after Move/Resize

The per-monitor dismiss overlays are intentionally left open during a
Move/Resize session (click-outside-to-cancel surface), but sessions ended
via Save / Cancel / Reset / Enter / ESC only cleared the session file —
the invisible layers stayed mapped above the widget and swallowed every
further right-click until restart. Fixes:
  * `move_ctl.finish()` now runs the verified popup cleanup BEFORE removing
    the session file (close_popup needs it for the per-monitor overlay ids);
  * close_popup additionally closes tracked windows BY INSTANCE id from
    `eww active-windows`, so already-orphaned overlays (session file gone,
    e.g. after a crash or an older save) are recovered too.
Tests: finish ordering/crash-safety + orphan-id closing (5 new cases).

## Follow-up fix: panel Save refused drags + wrong-menu on overlap

Two live-tested issues, both root-caused with instrumentation:

  * **Panel move + Save did nothing.** The off-screen guard compared the
    saved POSITION OFFSETS against the frame — offsets are relative to the
    gap baseline and are legitimately negative when dragging away from the
    anchored edge, so every such drag was refused (silently: stderr is
    DEVNULL by design). The guard now validates the dragged rectangle (the
    rendered result), Save/Cancel run synchronously in the control panel
    with an inline error label, and `move_ctl.py` logs every action,
    computed numbers and refusals to `logs/move_ctl.log`. Verified E2E:
    drag to (800,200) -> offsets (-880,170) persisted, relayout reopened
    the canvas clamped to y=35 with translate_y=165 and a pixel probe put
    the content exactly at y=200.
  * **Right-click under an overlapping canvas opened the other widget's
    menu/rectangle** (panel's transparent strip over the clock). ctx.py now
    resolves ownership from the VISIBLE rectangles (`choose_widget`): the
    claimed widget wins when its rect contains the cursor; otherwise the
    smallest containing rect takes over, so the menu and its Move/Resize
    rectangle always match the widget under the pointer.

## Follow-up: single-instance process management

Repeated restarts accumulated orphaned helpers (measured after one day:
4x watch.py, 4x monitor_watch.py, 2x input_daemon pairs ≈ 95 MB wasted
RSS): stop.sh killed watchers only through their pidfile (which later
starts overwrite), and the input daemon had no stop path at all. New
shared `scripts/bin/process_sweep.sh` — ancestor-protected pattern sweep
with TERM→KILL escalation — is now used by start.sh (pre-spawn sweep per
helper), stop.sh (post-pidfile sweep incl. the input daemon) and
session.start_daemon (stray sweep + pattern-aware liveness fallback). A
double-start test keeps exactly one instance of each helper; total related
RSS dropped from ~272 MB to ~95 MB while the GUI daemon idles at ~55 MB /
0% CPU.

## Follow-up fix: instant context menu

Ownership forwarding had made right-clicks take ~3.5 s: 6 helper
processes, each re-running the slow monitor enumeration (xrandr ≈250 ms),
config/YAML parsing and PIL font loading. ctx.py now computes ownership
AND placement in ONE process on top of shared data
(`menu_pos.menu_position()` extracted for reuse; widget_rect gained
in-process merged-config + font/natural-size caches), plus a 30 s TTL
monitor cache invalidated by monitor_watch on hotplug. Measured pipeline:
~280 ms cold / ~2 ms warm (legacy subprocess path kept as fallback).
Tests: menu_position placement/clamping/monitor-pick (4 new cases).

Follow-up: on KDE/Wayland the same pipeline trusted xdotool, whose pointer
is stale above native layer-shell widgets — every panel right-click could
be forwarded to the clock. `ctx.resolve_cursor()` now picks the
compositor-correct source (xdotool on X11, KWin scripting via
workarea.kde_cursor on Wayland) and forwarding stays OFF when no reliable
cursor exists (4 new cases).

Follow-up: KDE/Wayland stack fell back to X11-compat mode when started
without WAYLAND_DISPLAY in its environment (SSH / some terminals) — KWin
ignores client-requested X11 positions, so shrunken widgets refused to sit
at screen edges even though Save persisted correct values. Shared
`scripts/core/detect.py` now detects the session via env, XDG_SESSION_TYPE,
running Wayland-compositor process names and gnome-shell's own environ
(monitors.py + workarea.py both use it — a mismatch would mix window
backends), and start.sh imports each missing session variable individually
instead of early-returning when only DISPLAY is present. Diagnosed live on
the affected KDE box: locally `compositor=wayland`, geometry math exact,
Save wrote offsets — only the XWayland placement was wrong.

## Verification (executed)

1. `pytest tests/` — **160 passed** (existing suite + the new axis-scale
   tests).
2. `python3 -m py_compile` clean on every touched script; `bash -n scripts/
   bin/start.sh` clean.
3. CLI smoke checks: `config.py --key scale_x` / `--key panel_scale_y`
   resolve (1.0 defaults); `move_ctl.py --help` lists the six new actions.
4. Live GUI smoke test (Move/Resize session with the new rows, Shift+arrows
   and edge drags) needs a running desktop session — perform after deploying
   this branch; the geometry math is covered end-to-end by the unit tests and
   mirrors the verified v2.2.0 pipeline.
