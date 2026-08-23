"""transform :translate must compensate for scale-before-translate ordering.

The targeted eww build applies cr.scale() BEFORE cr.translate() inside its
transform widget, so the effective on-screen offset is scale x translate.
widget_rect.py therefore emits translate = (visible_tl - canvas_tl) / scale
per axis. These tests pin that invariant: after the division, multiplying
the emitted translate back by the axis scale must reproduce the desired
device-pixel delta (visible_tl - canvas_tl) within 1 px rounding.
"""

import importlib.util
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "widget_rect", os.path.join(REPO_ROOT, "scripts", "move", "widget_rect.py")
)
wr = importlib.util.module_from_spec(_spec)
sys.modules["widget_rect"] = wr
_spec.loader.exec_module(wr)

MONITOR = {"x": 0, "y": 0, "width": 1920, "height": 1080}
WORKAREA = (0, 30, 1920, 1050)

CFG = {
    "scale_x": "1.0",
    "scale_y": "1.0",
    "alignment": "middle_middle",
    "position_x": "753",
    "position_y": "392",
    "city": "Budapest",
}


@pytest.fixture(autouse=True)
def patched_config(monkeypatch):
    monkeypatch.setattr(wr, "config_value", lambda k, m=None: CFG.get(k, ""))
    monkeypatch.setattr(wr, "clock_natural_size", lambda m: (628, 247))


def _check(sx, sy, px, py, align):
    CFG.update(scale_x=str(sx), scale_y=str(sy),
               position_x=str(px), position_y=str(py), alignment=align)
    r = wr.clock_rect(MONITOR, "wayland", WORKAREA, 0)
    dx = r["x"] - r["win_x"]
    dy = r["y"] - r["win_y"]
    ex = float(CFG["scale_x"]) * r["translate_x"]
    ey = float(CFG["scale_y"]) * r["translate_y"]
    assert abs(ex - dx) <= 1, f"x: {ex} != {dx}"
    assert abs(ey - dy) <= 1, f"y: {ey} != {dy}"
    assert 0 <= r["win_x"] and r["win_x"] + r["win_w"] <= MONITOR["width"]
    assert 0 <= r["win_y"] and r["win_y"] + r["win_h"] <= WORKAREA[3]
    return r


def test_current_session_scales():
    _check(0.56, 0.96, 753, 392, "middle_middle")


def test_user_resized_single_axis():
    _check(0.37, 1.00, 753, 392, "middle_middle")


def test_corner_clamp_bottom_right():
    r = _check(0.25, 0.25, 5000, 5000, "bottom_right")
    assert r["translate_x"] > 0 and r["translate_y"] > 0


def test_oversize_no_translate():
    r = _check(1.5, 1.5, 0, 0, "top_left")
    assert r["translate_x"] == 0 and r["translate_y"] == 0
    assert r["win_w"] == 942 and r["win_h"] == 370


def test_full_scale_no_translate():
    r = _check(1.0, 1.0, 0, 0, "top_left")
    assert r["translate_x"] == 0 and r["translate_y"] == 0
