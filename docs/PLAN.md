# Restructuring Plan — executed

> **Status: DONE & verified** (2026-08-22, live on this machine).
> This document records the directory restructure carried out on the working
> tree. It replaces the previous CI-planning content — the CI setup itself
> lives in `.github/workflows/` and is described in the WIKI.

## Goal

Group the previously flat layout into logical folders without breaking the
running widget:

- separate the eww config files from the repository root,
- split the flat `scripts/` pile by role (core / widgets / move / bin),
- collect source assets under `assets/` and documentation under `docs/`,
- tidy runtime outputs (`*.log`, `*.pid`) out of the repo root.

## New layout

```
Clock-With-Weather-EWW/
├── eww/                  # THE eww config dir: eww.yuck + eww.scss (+ generated theme files)
├── scripts/
│   ├── core/             # config, config_set, monitors, monitor_watch, session,
│   │                     # system, theme, watch, weather, workarea
│   ├── widgets/          # about, about_win, close_popup, ctx, panel
│   ├── move/             # esc_listener, input_daemon, menu_pos, move, move_ctl,
│   │                     # move_keys, move_panel, move_rect, widget_rect
│   └── bin/              # start.sh, stop.sh, install.sh, setup.sh, setup-test-env.sh
├── assets/
│   ├── themes/           # appearance/<name>/appearance.yaml + weather/<name>/weather.yaml
│   ├── icons-src/        # source icon sets (<theme>/weather|elements/*.png)
│   └── fonts/            # NotoSans-Regular.ttf
├── docs/                 # WIKI.md, PLAN.md, RELEASE_NOTES.md, images/screenshots/
├── tools/                # screenshots tooling + vendored git-filter-repo.sh
├── tests/                # headless pytest suite (location unchanged)
└── logs/  run/  charts/  generated/   # git-ignored runtime outputs (.gitkeep kept in git)
```

## Executed steps

### 1. File moves (`git mv`, history preserved)

| Old | New |
|---|---|
| `eww.yuck`, `eww.scss` | `eww/` |
| `scripts/{config,config_set,monitors,monitor_watch,session,system,theme,watch,weather,workarea}.py` | `scripts/core/` |
| `scripts/{about,about_win,close_popup,ctx,panel}.py` | `scripts/widgets/` |
| `scripts/{esc_listener,input_daemon,menu_pos,move,move_ctl,move_keys,move_panel,move_rect,widget_rect}.py` | `scripts/move/` |
| `scripts/{start,stop,install,setup,setup-test-env}.sh` | `scripts/bin/` |
| `scripts/git-filter-repo.sh` | `tools/` |
| `fonts/` | `assets/fonts/` |
| `themes/{appearance,weather}/` | `assets/themes/{appearance,weather}/` |
| `images/theme/` | `assets/icons-src/` |
| `images/screenshots/` | `docs/images/screenshots/` |
| `WIKI.md`, `PLAN.md`, `RELEASE_NOTES.md` | `docs/` |

### 2. EWW config dir: repo root → `eww/`

- `start.sh` / `stop.sh` / `setup.sh` and every Python script calling eww now
  use `EWW_CONFIG_DIR = <repo root>/eww`.
- `eww.yuck`: defpoll / onclick commands became `../scripts/<group>/<name>.py`,
  image paths `../generated/icons/...` — eww resolves relative paths against
  the **config** directory.
- `scripts/core/theme.py` writes `eww.theme.json` / `eww.theme.scss` into
  `eww/`, next to `eww.yuck` (stale copies at the old root were removed).
- `scripts/core/watch.py` reloads with `--config <root>/eww`.

### 3. Python scripts: path constants & imports

- Every moved script derives its paths from `__file__` (three levels up to
  the root); a `SCRIPTS_DIR` helper was added where needed.
- Cross-group imports got an explicit `sys.path` bootstrap:
  - `widgets/{about,close_popup,ctx}.py` and `move/{move,move_ctl}.py` import
    `session` from `scripts/core/`,
  - `move/widget_rect.py` imports `workarea` from `scripts/core/`.
- Subprocess spawn targets updated to the new groups (`../core/config.py`,
  `../core/monitors.py`, `../widgets/close_popup.py`, `core/theme.py`,
  `bin/start.sh`, ...).
- `panel.py` anchors CHARTS / THEME / LAYOUT paths to `__file__` (never to
  the cwd) and returns chart names as `../charts/...` (see Notes).

### 4. Shell scripts

- `start.sh`: `DIR` resolution `/..` → `/../..`; all `$DIR/scripts/*` targets
  regrouped; `LOGS_DIR=$DIR/logs` and `RUN_DIR=$DIR/run` are `mkdir -p`-ed at
  startup and used for every log/pid write.
- `stop.sh`: reads pid files from `run/`.
- `setup.sh`: `logs/start.log` (with mkdir before the nohup redirect),
  `scripts/core/` script paths, `assets/themes` paths, desktop launcher
  Exec/Icon paths, `eww --config "$DIR/eww"`.

### 5. Runtime outputs: `logs/` and `run/`

- `logs/`: `start.log`, `watch.log`, `monitor_watch.log`, `input_daemon.log`.
- `run/`: `watch.pid`, `monitor_watch.pid`, `input_daemon.pid`,
  `esc_listener.pid` (moved out of `generated/`).
- Writers/readers updated: `start.sh`, `stop.sh`, `watch.py` (relayout output
  + defensive `makedirs`), `session.py`, `input_daemon.py` (+`makedirs`),
  `esc_listener.py`.
- The pre-existing global `*.log` / `*.pid` ignore rules cover both folders.

### 6. Requirements merged

- `requirements-dev.txt` deleted; `pytest` moved into `requirements.txt`
  under a *development / testing* comment (nothing deploys via pip —
  `install.sh` uses distro packages — so one file is enough).
- `ci.yml` installs a single requirements file; WIKI references updated.

### 7. CI workflows

- `ci.yml`: syntax check compiles recursively (`find scripts -name '*.py'`),
  yaml-validate glob is `assets/themes/**/*.yaml`, ShellCheck runs on
  `scripts/bin/*.sh`.
- `release.yml`: release body read from `docs/RELEASE_NOTES.md`.

### 8. Documentation

- **README**: install/start/setup URLs (`scripts/bin/...`), screenshot paths
  (`docs/images/...`), WIKI links, new *Project Structure* section.
- **WIKI**: structure section rewritten for the new layout; manual eww
  examples use `--config .../eww`; the defpoll table shows `../scripts/...`
  commands; CI description globs fixed; the watch.py row documents
  `logs/watch.log` / `run/watch.pid`.
- **RELEASE_NOTES**: layout table refreshed (paths only, history untouched).

### 9. Runtime directories tracked via `.gitkeep`

- `logs/.gitkeep`, `run/.gitkeep`, `charts/.gitkeep`, `generated/.gitkeep`
  are version-controlled so a fresh clone already contains the folders.
- `.gitignore`: `generated/` was replaced by `generated/**` +
  `!generated/.gitkeep` — a whole-directory exclusion cannot be negated from
  inside (git does not descend into excluded directories).
- Convenience only: every folder is also auto-created at runtime
  (`start.sh` makes `logs/`+`run/`, `panel.py` makes `charts/`,
  `theme.py` makes `generated/icons/`).

## Verification

- `pytest tests/` — **92 passed**.
- `py_compile` across `scripts/{core,widgets,move}/*.py` — clean.
- `bash -n` on all shell scripts — clean; workflow YAML parses.
- Live restart via `scripts/bin/start.sh`: main + panel opened on both
  monitors with **zero errors**; logs land in `logs/`, pid files in `run/`;
  hot reload confirmed through `logs/watch.log`.
- Repo-wide grep sweeps found no leftovers of the old layout
  (`./scripts/<mod>.py`, bare `themes/` / `images/theme`, root-level
  `*.log` / `*.pid`, `requirements-dev`).

## Notes / decisions

- Eww resolves relative image/command paths against the **config**
  directory — hence the `../` prefixes in `eww.yuck` and the `../charts/`
  prefix returned by `panel.py`.
- In the Python scripts `CONFIG_DIR` still means the **repository root**
  (`config.yaml`, `.api_key`, `charts/`, `generated/`, `.layout.json` live
  there); eww invocations go through the separate `EWW_CONFIG_DIR`.
- Historical documents were path-refreshed rather than rewritten
  (RELEASE_NOTES), while this file was replaced wholesale as requested.
