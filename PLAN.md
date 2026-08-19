# PLAN: Per-monitor-only position/scale — right-click Save writes to `per_monitor`

## Goal

The right-click context menu -> Move / Resize -> **Save** writes the
`position_x` / `position_y` / `scale` values into `per_monitor[N]` for the
current monitor. The global `position_x` / `position_y` / `scale` keys are
removed from `config.yaml`; `per_monitor` becomes the single source of truth.
Monitors without an entry fall back to code defaults (position 0/0, scale 1.0).

## Root cause

`scripts/move_ctl.py:save_value()` only passed `--monitor` when the monitor was
already present in `per_monitor`. With the initial `per_monitor: {}` the first
Save wrote the **global** `position_x`/`position_y`/`scale` keys instead of a
per-monitor entry.

## Files to change

1. **`config.yaml`**
   - `weather.window`: remove `position_x` / `position_y` / `scale`; keep
     `alignment` + `per_monitor: {}`.
   - `panel.window`: remove `position_x` / `position_y` / `scale` (dead config —
     the panel position is derived from `panel.gap`); keep `alignment` +
     `per_monitor: {}`.
   - Refresh the comments (per_monitor examples; drop the stale "see PLAN.md
     section 5" reference).
   - Seed the current global `scale: 0.90` into `per_monitor[0]` so the user's
     current setup is preserved.

2. **`scripts/config.py`**
   - No functional change (`.get(key, default)` already yields 0/0/1.0).
   - Update the docstring: position/scale live only in `per_monitor`; `--key
     scale/position_x/position_y` without `--monitor` returns the default.

3. **`scripts/config_set.py`**
   - Make `--monitor` **required** for `position_x` / `position_y` / `scale`
     (the global keys no longer exist). `gap_*` handling stays global.
   - Update the docstring.

4. **`scripts/move_ctl.py`**
   - `save_value()`: always pass `--monitor` for non-gap keys (drop the
     `monitor in pm` check). Reset keeps writing 0/0/1.00 — now into
     `per_monitor[N]`.

5. **`scripts/about_win.py`**
   - `config_value()` gains a monitor parameter; the "Scale" row reads it with
     `--monitor self.monitor`.

6. **`scripts/setup.sh`**
   - `DEFAULT_POSITION_X/Y` read from `per_monitor[0]`
     (`--key position_x --monitor 0`, default 0).
   - `setupWriteConfig`: replace the `sed -i "s/^  position_x: ..."` writes
     with `config_set.py --widget clock --monitor 0 --key position_x/position_y`.

7. **`scripts/install.sh`**
   - No change needed: it sources `setup.sh` and inherits the fix.

8. **`scripts/start.sh` / `eww.yuck`**
   - Comment refresh only (`window.alignment + per_monitor`).

9. **`README.md`**
   - Config examples + field table: remove the global `position_x/y` / `scale`
     rows; state `per_monitor` is the only source (default 0/0, 1.0).

10. **`PLAN.md`**
    - This document.

## Verification

- `./scripts/config.py --key scale --monitor 0` -> `1.0` (default).
- Move / Resize -> Save -> `per_monitor: {0: {position_x, position_y, scale}}`
  in `config.yaml`.
- Reset -> `per_monitor[0] = {position_x: 0, position_y: 0, scale: 1.00}`.
- `start.sh --relayout` picks up the per-monitor values.
- `setup.sh` wizard writes the position into `per_monitor[0]`.