# PLAN: Per-monitor panel position_x/position_y (Move/Resize/Reset like the clock)

## Goal

The system-monitor panel gets per-monitor `position_x` / `position_y` settings,
just like the weather/clock widget: the right-click context menu -> Move /
Resize -> **Save** writes them into `panel.window.per_monitor[N]`, **Reset**
clears them to 0 (and resets the scale to 1.0).

The panel keeps its existing taskbar-aware geometry: the global `panel.gap`
remains the shared baseline (height + default inset); the per-monitor
`position_x` / `position_y` are pixel OFFSETS added to that baseline
(positive = right/down), so every monitor can be positioned independently.

## Design decisions

- **Gap stays global** (the user's chosen "gap + offset" combination). The
  per-monitor offsets already allow different positions per monitor; making the
  gaps per-monitor as well was considered but rejected as unnecessary (offsets
  cover the per-monitor variability, and gaps also drive the height).
- The offset is defined in the **Move/Resize rectangle's frame coordinates**
  (workarea-local on Wayland, monitor-local on X11), i.e. the same space the
  clock's `position_x`/`position_y` use. `workarea.py` converts the frame delta
  back into the eww `:x`/`:y` offset with the anchor-dependent sign (on
  Wayland the margin of a right-anchored window grows when the panel moves
  LEFT, so the offset is subtracted there).
- The scale still scales the panel from its anchored corner/edge; zoom keeps
  the effective offset (base margin + offset) constant, exactly as it kept the
  right gap before.

## Files to change

1. **`config.yaml`**
   - `panel.window.per_monitor`: add `position_x` / `position_y` (per monitor,
     same syntax as `weather.window.per_monitor`), keep `scale`.
   - Comment refresh: position offsets + gap baseline; Reset = 0/0 + scale 1.0.

2. **`scripts/config.py`**
   - New keys `panel_position_x` / `panel_position_y` (global default 0),
     resolved per monitor from `panel.window.per_monitor[N]` with `--monitor`
     (mirrors `panel_scale`).
   - Docstring update.

3. **`scripts/config_set.py`**
   - No functional change: `--widget panel --key position_x/position_y --monitor N`
     already writes `panel.window.per_monitor[N]`.
   - Docstring update.

4. **`scripts/workarea.py`**
   - `load_panel_offsets()`: read per-monitor panel position offsets from
     config.yaml.
   - `_base_geometry_for()`: extract the gap-only (offset-free) panel geometry +
     Move/Resize frame size for one monitor.
   - `apply_panel_offset()`: add the offset to the gap-derived eww offsets with
     the correct (compositor, anchor) sign.
   - `rect_from_offsets()`: convert eww offsets + size into rectangle frame
     coordinates (same formulas as `widget_rect.py panel_rect`).
   - `compute_per_monitor()`: uses the above; each monitor entry keeps
     `base_x`/`base_y` (the gap-only offsets) for debugging/inspection.
   - New `--base-rect` mode: gap-derived rectangle top-left for an arbitrary
     size (used by `move_ctl.py` Save).
   - `--gaps-for-rect` kept as-is (now unused by `move_ctl.py`; harmless).
   - Docstring update.

5. **`scripts/widget_rect.py`**
   - No functional change: it reads `.layout.json`, which now carries the
     effective (offset-included) `x`/`y`, so the Move/Resize rectangle and the
     context menu already see the real position.

6. **`scripts/move_ctl.py`**
   - `base_rect()`: replace `panel_gaps()` — calls `workarea.py --base-rect`
     for the dragged size.
   - `save` (panel): write the offset = dragged rect − base rect as
     `position_x` / `position_y` (per monitor), keep scale.
   - `reset`: write `position_x: 0`, `position_y: 0`, `scale: 1.00` for both
     widgets (the panel gaps stay untouched).
   - Docstring update.

7. **`scripts/start.sh`**
   - No functional change: `px`/`py` already come from `workarea.py
     --per-monitor` (now offset-included).

8. **`eww.yuck`**
   - Comment refresh only (Reset row + `panel_window` geometry comment).

9. **`README.md`**
   - Reset table row, config example, config table (`panel.window.per_monitor`,
     `panel.gap`), "Panel alignment" section, script table rows
     (`workarea.py`, `move_ctl.py`).

10. **`PLAN.md`**
    - This document.

## Verification

- `./scripts/config.py --key panel_position_x --monitor 0` -> `0` (default).
- Panel -> right-click -> Move -> drag -> Save ->
  `panel.window.per_monitor[N]` gains `position_x` / `position_y` / `scale`.
- Reset -> `per_monitor[N] = {position_x: 0, position_y: 0, scale: 1.00}`
  while `panel.gap` stays unchanged.
- `workarea.py --per-monitor` shows the offset-included `x`/`y` plus
  `base_x`/`base_y`; `workarea.py --base-rect` matches the pre-offset position.
- `start.sh --relayout` picks up the per-monitor offsets (tested: drag 30/10 on
  monitor 0 -> config 30/10 -> panel at base + 30/10).
- X11 sign verified (positive offset shifts right/down); Wayland sign is
  handled in `apply_panel_offset` (flip for right-anchored margins).