# PLAN: GitHub Actions CI + Release workflow

## Goal

Add a lightweight GitHub Actions setup to the repository:

1. **CI** — headless checks on every push (master) and pull request:
   - Python unit tests (`pytest`) for the headless-testable logic
     (`config.py`, `config_set.py`, `workarea.py`, `theme.py`, `weather.py`,
     `system.py`, `panel.py`),
   - Python syntax check (`python -m py_compile scripts/*.py`),
   - YAML validation (`config.yaml` + all `themes/**/*.yaml`),
   - ShellCheck for the bash scripts (`scripts/*.sh`).
2. **Release** — a `v*` tag push creates a GitHub Release (with a changelog
   from `git log`); the README version badge already reads
   `releases/latest`.

Explicitly **NOT** included: EWW rendering / screenshot jobs (they need a real
display + GTK + an `eww` source build — too heavy/flaky for this project). The
`tools/screenshots` capture tool also stays manual.

## Scope

- This is a single-maintainer personal project, so the CI stays minimal: a few
  focused jobs, no nightly builds, no complex matrix beyond Python versions.

## Design decisions

- **pytest** is used as the test runner (stdlib `unittest` would be too
  verbose); the runtime dependencies come from the existing
  `requirements.txt`, pytest goes into a new `requirements-dev.txt`.
- Tests **never touch the real `config.yaml`**: `config.py` and
  `config_set.py` read/write module-level globals (`CONFIG_DIR`,
  `CONFIG_FILE`), so tests monkeypatch those onto a `tmp_path` copy. The
  line-aware writer (`config_set.py`) is verified with a round-trip test that
  asserts only the target line changes and the comments survive.
- The scripts are all importable (`__main__` guards present), so pytest imports
  the modules from `scripts/` directly (`pythonpath = scripts`).
- `weather.py` / `system.py` / `panel.py` are tested with mocked
  `requests` / `psutil` — no real API or network access in CI.
- No `.api_key` in CI (it is git-ignored); the API-key resolution order is
  tested with the env-var branch.

## Files to change

1. **`PLAN.md`** — this document.

2. **`tests/conftest.py`** — shared fixtures:
   - a `tmp_path` config copy that monkeypatches `config.CONFIG_DIR` and
     `config_set.CONFIG_FILE`,
   - a minimal `config.yaml` builder (defaults + overridable sections).

3. **`tests/test_config.py`** — `load_config()`:
   - defaults (appearance, hour_format, alignment, scale, positions...),
   - inline vs. theme (`name`) weather mode,
   - `--monitor` per-monitor resolution (weather + panel, fallback to defaults),
   - `resolve_api_key()` ordering (env var -> `.api_key` file -> `""`).

4. **`tests/test_config_set.py`** — line-aware YAML writer:
   - write a per-monitor key on a temp copy, re-read, assert value changed,
   - assert the surrounding comment lines are byte-identical,
   - `--monitor` is required for position/scale keys, gap keys stay global,
   - unknown widget / key errors.

5. **`tests/test_workarea.py`** — geometry logic:
   - taskbar position variants (top/bottom/left/right/none),
   - gap baseline + per-monitor offset combination (X11 vs. Wayland sign),
   - `--base-rect` mode (gap-derived rect for an arbitrary size),
   - `--per-monitor` output contains `base_x`/`base_y` + offset-included `x`/`y`.

6. **`tests/test_theme.py`** — appearance resolution:
   - string name -> `themes/appearance/<name>/appearance.yaml`,
   - inline dict used directly,
   - icon tinting produces a valid PNG (PIL, in `tmp_path`).

7. **`tests/test_weather.py`** — mocked `requests`:
   - 200 -> formatted fields (`temp_fmt`, `unit_symbol`, `icon_path`...),
   - non-200 -> `{"error": ...}`,
   - exception -> `{"error": ...}`.

8. **`tests/test_system.py`** + **`tests/test_panel.py`** — mocked `psutil`:
   - `system.py` / `panel.py` return valid JSON-ish structures.

9. **`pytest.ini`** — `testpaths = tests`, `pythonpath = scripts`.

10. **`requirements-dev.txt`** — `pytest`.

11. **`.github/workflows/ci.yml`**:
    - `on`: push (master) + pull_request,
    - job `test` (matrix: 3.11 / 3.12 / 3.13 / 3.14):
      `pip install -r requirements.txt -r requirements-dev.txt`,
      `python -m py_compile scripts/*.py`, `pytest tests/ -v`,
    - job `yaml-validate`: `yaml.safe_load` on `config.yaml` + all
      `themes/**/*.yaml`,
    - job `shellcheck`: `koalaman/shellcheck@stable` on `scripts/*.sh`.

12. **`.github/workflows/release.yml`**:
    - `on`: push tags `v*`,
    - create a Release with `softprops/action-gh-release` using `GITHUB_TOKEN`
      and a changelog generated from `git log`.

13. **`README.md`** — add a `![CI]` shield to the badge row.

14. **`WIKI.md`** — extend the "For testing / development" section with a short
    CI paragraph (`pytest tests/`, GitHub Actions).

## Verification

- `python -m pytest tests/ -v` passes locally (all green).
- `python -m py_compile scripts/*.py` passes.
- All `config.yaml` + `themes/**/*.yaml` parse with `yaml.safe_load`.
- ShellCheck passes on every `scripts/*.sh` (no new errors/warnings).
- A `v*` tag push triggers the release workflow and creates a Release.
- Push / PR to master triggers the CI workflow with all jobs green.
