# Local Config Override Plan — `config.local.yaml`

> **Status: PLANNED** (2026-08-22).
> This replaces the previous (executed) restructuring plan — see git history
> for that record.

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

### 7. Verification

1. `pytest tests/` green.
2. Smoke test: put an override into `config.local.yaml`
   (e.g. `weather.window.per_monitor.0.scale`), check
   `./scripts/core/config.py --key scale --monitor 0` returns it.
3. Run `theme.py`; edit `config.local.yaml` while `watch.py` runs and confirm
   hot reload + relayout fire (see `logs/watch.log`).
4. `git status` stays clean across Move/Resize Save actions.

## Decisions (defaults)

- `setup.sh` keeps writing installation defaults into the committed
  `config.yaml` — install-time defaults belong there.
- No separate `config.local.yaml.example` shipped; the `config.yaml` header
  + README cover discoverability.
