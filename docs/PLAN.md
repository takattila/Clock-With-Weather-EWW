# Local Config Override Plan — `config.local.yaml`

> **Status: DONE & verified** (2026-08-22, live on this machine):
> 105 tests pass, end-to-end smoke tests confirmed that script writes land in
> `config.local.yaml` while `config.yaml` stays byte-identical.
> This replaces the restructuring record — see git history for that document.
>
> Deviation from the plan below: `setup.sh` was ALSO switched to write its
> wizard choices into `config.local.yaml` (originally it would have kept
> editing `config.yaml`).
>
> Follow-up fixes folded into the same release (v2.1.0):
> - **Layered weather resolution**: with `weather.name` set, the theme now
>   provides only the baseline and inline fields patch on top of it —
>   previously the base's `name: default` silently ignored local inline city
>   settings, so not EVERY value could be overridden via `config.local.yaml`.
> - **Right-click context menu fixed**: `ctx.py` still looked for
>   `menu_pos.py` at its pre-restructure location (`scripts/widgets/`
>   instead of `scripts/move/`), so every right click died before opening
>   the menu.

## Problem

`config.yaml` is tracked in git, yet it changes constantly on a live machine:
local preference edits AND machine-generated data (the right-click
Move/Resize -> Save writes `per_monitor` positions/scales through
`scripts/core/config_set.py`). Every such change shows up as a git
modification and pollutes diffs / risks accidental commits.

## Solution

Add a **local override layer**:

```
config.yaml         committed defaults   (only intentional edits land here)
        +
config.local.yaml   git-ignored overrides (machine-specific values,
                                         everything the scripts write)
        =
                    merged view used by every reader
```

Merge semantics: **deep merge down to the leaves** — dict values merge
recursively, scalars/lists are replaced by the local value. So e.g.
`per_monitor: 0: { scale: 0.8 }` in the local file keeps `position_x/y`
from the base entry for monitor 0.

## Implementation steps

### 1. New shared loader: `scripts/core/config_io.py`

- `deep_merge(base, override)`: recursive dict merge (leaf-level; the local
  value wins; lists/scalars replace).
- `load_merged(config_dir)`: reads `config.yaml`, then `config.local.yaml`
  if it exists (missing/empty file = no-op) and returns the merged dict.
- Broken local YAML: warning on stderr, fall back to base (the widget must
  not die from a typo'd local edit).

### 2. Switch the readers to the merged loader

Import via `sys.path.insert(0, <scripts>/core)` — same bootstrap pattern as
`move_ctl.py`.

| File | Function | Notes |
|---|---|---|
| `scripts/core/config.py` | `load_config()` (~line 74) | main JSON/key reader |
| `scripts/core/theme.py` | `load_config()` (~line 27) | makes `appearance` + `system.corner_radius` locally overridable too |
| `scripts/core/workarea.py` | `load_gaps()` (~line 309), `load_panel_offsets()` (~line 634) | panel gaps + per-monitor offsets |

### 3. Rewrite the writer: `scripts/core/config_set.py`

- CLI stays identical (`--widget/--key/--value/--monitor`) so callers
  (`move_ctl.py`, context menus) need no changes — only docstrings update.
- New behavior: load base + existing local, apply the change into the
  **local** tree, write `config.local.yaml` with `yaml.safe_dump(sort_keys=False)`.
  The file is machine-generated, so the line-aware comment-preserving editor
  (KEY_RE, block_region, ...) can be dropped.
- After this change no script ever writes `config.yaml` -> its diffs come
  only from deliberate hand edits.

### 4. Hot reload: `scripts/core/watch.py`

- `_scan()`: interesting names of the root dir become
  `{"config.yaml", "config.local.yaml"}`.
- `_handle_events()`: a `config.local.yaml` change also sets
  `config_changed = True` (triggers `start.sh --relayout`, needed because
  per_monitor positions change window geometry).

### 5. Git + documentation

- `.gitignore`: add `config.local.yaml` (like `.api_key`).
- `config.yaml` header comment: short explanation + override example.
- README: new section about the override layer.
- Docstrings of all touched scripts updated (`config.local.yaml` instead of
  `config.yaml` where writes/reads are concerned).

### 6. Tests (pytest)

- `tests/conftest.py`: new `write_local_config` fixture.
- `test_config.py`: override cases (appearance / per_monitor / gap from the
  local file; missing local file = pure base).
- `test_theme.py`, `test_workarea.py`: same merge coverage for their readers.
- `test_config_set.py`: rewritten — asserts values land in
  `config.local.yaml` and **the base `config.yaml` stays byte-identical**
  (the key property of the whole feature).

### 7. Verification (executed)

1. `pytest tests/` — **104 passed** (12 new merge/writer tests).
2. `config_set.py` runs wrote `config.local.yaml`; `config.py --key scale
   --monitor 0` returned the override while untouched keys kept base values.
3. `theme.py` regenerated the theme files through the merged loader; watcher
   changes verified by unit-level parse + the existing inotify flow.
4. `git status` stays clean across Move/Resize Save actions — the writer and
   the setup wizard only ever touch the git-ignored file.

## Decisions (defaults)

- `setup.sh` originally would have kept writing the committed `config.yaml`;
  per user request it now writes into `config.local.yaml` (see the deviation
  note above).
- No separate `config.local.yaml.example` shipped; the `config.yaml` header
  + README cover discoverability.
