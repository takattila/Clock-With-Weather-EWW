"""transform :translate must match the running eww build's matrix order.

Two eww builds are in the wild:
  - v0.6.0 tag (hash d87c2fdb..., prints "eww 0.5.0"): cr.scale() runs BEFORE
    cr.translate(), cairo composes S*R*T and the on-screen offset is
    scale * translate -> widget_rect.py must emit delta / scale,
  - newer builds (e.g. 48f5aa8b...): fixed translate-after-scale order ->
    plain delta is correct.
widget_rect.py detects the order from the `eww --version` hash
(_divide_translate_by_scale); the per-monitor config key
`translate_divide_scale` ("yes"|"no"|"auto") overrides it.

The invariant tests pin that, whatever the order, the emitted translate
places the scaled content exactly on the visible rectangle; the detector
tests pin the version-string parsing and the fallbacks.
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
# Scenario tests mutate CFG (scales AND the translate_divide_scale
# override); the autouse fixture must restore this pristine baseline,
# otherwise a leftover "no"/"yes" override short-circuits the version
# detection in later tests (measured: all True-expectation detector cases
# failed when run after the scenarios).
BASE_CFG = dict(CFG)


@pytest.fixture(autouse=True)
def patched(monkeypatch):
    """Fresh config + cleared order cache for every test."""
    monkeypatch.setattr(wr, "config_value", lambda k, m=None: CFG.get(k, ""))
    CFG.clear()
    CFG.update(BASE_CFG)
    wr._EWW_TRANSLATE_ORDER_CACHE.clear()
    yield


def _clock_rect(sx, sy, px, py, align):
    CFG.update(scale_x=str(sx), scale_y=str(sy),
               position_x=str(px), position_y=str(py), alignment=align)
    return wr.clock_rect(MONITOR, "wayland", WORKAREA, 0)


def _assert_content_lands(r):
    """Emitted translate must reproduce the desired device-pixel delta."""
    divide = wr._divide_translate_by_scale("wayland")
    sx, sy = float(CFG["scale_x"]), float(CFG["scale_y"])
    dx = r["x"] - r["win_x"]
    dy = r["y"] - r["win_y"]
    if divide:
        assert abs(sx * r["translate_x"] - dx) <= 1, f"x: {sx}*{r['translate_x']} != {dx}"
        assert abs(sy * r["translate_y"] - dy) <= 1, f"y: {sy}*{r['translate_y']} != {dy}"
    else:
        assert r["translate_x"] == dx, f"x: {r['translate_x']} != {dx}"
        assert r["translate_y"] == dy, f"y: {r['translate_y']} != {dy}"
    assert 0 <= r["win_x"] and r["win_x"] + r["win_w"] <= MONITOR["width"]
    assert 0 <= r["win_y"] and r["win_y"] + r["win_h"] <= WORKAREA[3]


SCENARIOS = [
    # (sx, sy, px, py, alignment, label)
    (0.56, 0.96, 753, 392, "middle_middle", "current session scales"),
    (0.37, 1.00, 753, 392, "middle_middle", "single-axis resize"),
    (0.25, 0.25, 5000, 5000, "bottom_right", "corner clamp"),
    (1.50, 1.50, 0, 0, "top_left", "oversize"),
]


@pytest.mark.parametrize("sx,sy,px,py,align,label", SCENARIOS)
def test_old_build_divides_by_scale(sx, sy, px, py, align, label):
    CFG["translate_divide_scale"] = "yes"
    r = _clock_rect(sx, sy, px, py, align)
    _assert_content_lands(r)


@pytest.mark.parametrize("sx,sy,px,py,align,label", SCENARIOS)
def test_new_build_uses_plain_delta(sx, sy, px, py, align, label):
    CFG["translate_divide_scale"] = "no"
    r = _clock_rect(sx, sy, px, py, align)
    _assert_content_lands(r)


def test_zero_delta_is_zero_in_both_orders():
    for override in ("yes", "no"):
        CFG["translate_divide_scale"] = override
        wr._EWW_TRANSLATE_ORDER_CACHE.clear()
        r = _clock_rect(1.0, 1.0, 0, 0, "top_left")
        assert r["translate_x"] == 0 and r["translate_y"] == 0


DETECT_CASES = [
    # (eww --version output, compositor, expected divide?)
    ("eww 0.5.0 d87c2fdbfdc012e76d229e4e9ea3325bc0f23e89", "wayland", True),
    ("eww 0.6.0 d87c2fdbfdc012e76d229e4e9ea3325bc0f23e89", "x11", True),
    ("eww 0.6.0 48f5aa8b379adf29da0b0bb9ca04164f65d8bdaa", "wayland", False),
    ("eww 0.6.0 48f5aa8b379adf29da0b0bb9ca04164f65d8bdaa", "x11", False),
    ("some future release text", "wayland", True),   # unknown probe -> fleet heuristic
    ("some future release text", "x11", False),
    ("", "wayland", True),                            # probe failure
    ("", "x11", False),
]


@pytest.mark.parametrize("version_out,compositor,expected", DETECT_CASES)
def test_detector_parses_version_hash(version_out, compositor, expected, monkeypatch):
    monkeypatch.setattr(wr, "_run", lambda cmd: version_out)
    assert wr._divide_translate_by_scale(compositor) is expected


@pytest.mark.parametrize(
    "override,version_out",
    [
        # probe identifies a modern build (would NOT divide)...
        ("yes", "eww 0.6.0 48f5aa8b379adf29da0b0bb9ca04164f65d8bdaa"),
        # probe identifies the v0.6.0 tag build (would divide)
        ("no", "eww 0.5.0 d87c2fdbfdc012e76d229e4e9ea3325bc0f23e89"),
    ],
)
def test_override_beats_detection(override, version_out, monkeypatch):
    CFG["translate_divide_scale"] = override
    monkeypatch.setattr(wr, "_run", lambda cmd: version_out)
    assert wr._divide_translate_by_scale("x11") is (override == "yes")


def test_result_cached_per_compositor(monkeypatch):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return ""

    monkeypatch.setattr(wr, "_run", fake_run)
    first = wr._divide_translate_by_scale("wayland")
    second = wr._divide_translate_by_scale("wayland")
    assert first == second and len(calls) == 1
