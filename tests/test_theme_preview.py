"""Pure logic of scripts/move/theme_preview.py (the live-preview worker).

The worker is spawned detached by the theme editor; these tests exercise its
apply/restore pipeline against a throwaway directory (module paths are
monkeypatched), covering: the generated theme files, the preview marker
snapshot, and the idempotent restore. The real `eww reload` is stubbed out.
"""

import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO_ROOT / "scripts" / "move"))
# theme_preview imports `theme` from scripts/core at runtime
sys.path.insert(0, str(REPO_ROOT / "scripts" / "core"))

import theme_preview as wp  # noqa: E402
import theme  # noqa: E402


APPEARANCE = {
    "theme": "dark",
    "icon": {"set": "dovora", "transparency": {"light": 1.0, "dark": 1.0}},
    "font": {
        "face": "Noto Sans",
        "color": {"light": "#ff0000", "dark": "#9e9e9e"},
        "transparency": {"light": 1.0, "dark": 1.0},
    },
    "background": {"transparency": 0.5, "color": "#0000ff"},
    "chart": {
        "colors": {"cpu": "#ff0000", "memory": "#ff0000",
                   "net_down": "#ff0000", "net_up": "#ff0000"},
        "glow": False,
    },
}


@pytest.fixture
def worker_dir(monkeypatch, tmp_path):
    """Point the worker at a scratch config root and stub the eww reload."""
    d = tmp_path / "config"
    eww = d / "eww"
    gen = d / "generated"
    eww.mkdir(parents=True)
    gen.mkdir(parents=True)
    monkeypatch.setattr(wp, "CONFIG_DIR", str(d))
    monkeypatch.setattr(wp, "EWW_DIR", str(eww))
    monkeypatch.setattr(wp, "GEN_DIR", str(gen))
    monkeypatch.setattr(wp, "PREVIEW_FILE", str(gen / "preview.json"))
    monkeypatch.setattr(wp, "reload_eww", lambda: True)
    return d


def test_apply_preview_writes_theme_files_and_marker(worker_dir):
    rc = wp.apply_preview(APPEARANCE, 20)
    assert rc == 0

    theme_json = json.loads((worker_dir / "eww" / "eww.theme.json").read_text())
    assert theme_json["bg_radius"] == 20
    # parse_appearance flips the painted bg for contrast; match its real output.
    assert theme_json["bg_color"] == theme.parse_appearance(APPEARANCE)["bg_color"]
    assert theme_json["color_light"] == "#ff0000"

    scss = (worker_dir / "eww" / "eww.theme.scss").read_text()
    assert "$color-light: #ff0000;" in scss
    assert "$bg-radius: 20px;" in scss

    marker_path = worker_dir / "generated" / "preview.json"
    assert marker_path.is_file()
    marker = json.loads(marker_path.read_text())
    assert marker["active"] is True


def test_apply_preview_snapshots_previous_theme_files(worker_dir):
    # Pre-existing theme files -> the preview keeps an undo snapshot.
    eww = worker_dir / "eww"
    (eww / "eww.theme.json").write_text('{"color_light":"#ffffff"}', encoding="utf-8")
    (eww / "eww.theme.scss").write_text("$color-light: #ffffff;\n", encoding="utf-8")

    wp.apply_preview(APPEARANCE, 15)
    marker = json.loads((worker_dir / "generated" / "preview.json").read_text())
    snap = marker["snapshot"]
    assert snap and (Path(snap) / "eww.theme.json").is_file()


def test_apply_preview_invalid_input_is_rejected(worker_dir):
    assert wp.apply_preview(None, 20) == 1
    assert wp.apply_preview({"theme": "light"}, "not-a-number") == 1
    assert not (worker_dir / "generated" / "preview.json").exists()


def _ok_run(args, **kwargs):
    class R:
        returncode = 0
        stderr = ""

    return R()


def test_restore_clears_marker_and_regenerates(worker_dir, monkeypatch):
    wp.apply_preview(APPEARANCE, 20)
    assert (worker_dir / "generated" / "preview.json").exists()

    # Stub the real theme.py subprocess so restore only proves it clears the
    # marker and requests a reload (the payload regeneration is theme.py's).
    monkeypatch.setattr(wp.subprocess, "run", _ok_run)
    rc = wp.restore()
    assert rc == 0
    assert not (worker_dir / "generated" / "preview.json").exists()


def test_restore_is_idempotent_noop_without_marker(worker_dir, monkeypatch):
    assert not (worker_dir / "generated" / "preview.json").exists()
    monkeypatch.setattr(wp.subprocess, "run", _ok_run)
    # Restoring with no active preview still regenerates from real config (rc 0).
    assert wp.restore() == 0
    assert not (worker_dir / "generated" / "preview.json").exists()
