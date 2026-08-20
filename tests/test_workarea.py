import textwrap

import pytest

import workarea

SCREEN = (1920, 1080)
DEFAULT_GAPS = {"top": 16, "right": 16, "bottom": 16, "left": 16}


def write_cfg(config_dir, body):
    p = config_dir / "config.yaml"
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------- detect_taskbar


@pytest.mark.parametrize(
    "wa,expected",
    [
        ((0, 30, 1920, 1050), "top"),
        ((0, 0, 1920, 1050), "bottom"),
        ((0, 0, 1700, 1080), "right"),
        ((100, 0, 1820, 1080), "left"),
        ((0, 0, 1920, 1080), "none"),
    ],
)
def test_detect_taskbar(wa, expected):
    assert workarea.detect_taskbar(SCREEN, wa) == expected


# ---------------------------------------------------------------- load_gaps


def test_load_gaps_default(config_dir):
    write_cfg(config_dir, "panel:\n  gap: 16\n")
    assert workarea.load_gaps(str(config_dir)) == DEFAULT_GAPS


def test_load_gaps_single(config_dir):
    write_cfg(config_dir, "panel:\n  gap: 8\n")
    gaps = workarea.load_gaps(str(config_dir))
    assert gaps == {"top": 8, "right": 8, "bottom": 8, "left": 8}


def test_load_gaps_partial_map(config_dir):
    write_cfg(config_dir, "panel:\n  gap: { top: 0, left: 5 }\n")
    gaps = workarea.load_gaps(str(config_dir))
    assert gaps == {"top": 0, "right": 16, "bottom": 16, "left": 5}


def test_load_gaps_comma_form(config_dir):
    write_cfg(config_dir, "panel:\n  gap:\n    top: 5,\n    bottom: 7\n")
    gaps = workarea.load_gaps(str(config_dir))
    assert gaps["top"] == 5
    assert gaps["bottom"] == 7
    assert gaps["right"] == 16


def test_load_gaps_missing(config_dir):
    write_cfg(config_dir, "panel:\n  enabled: true\n")
    assert workarea.load_gaps(str(config_dir)) == DEFAULT_GAPS


def test_load_gaps_invalid_value(config_dir):
    write_cfg(config_dir, "panel:\n  gap: abc\n")
    assert workarea.load_gaps(str(config_dir)) == DEFAULT_GAPS


# ---------------------------------------------------------------- load_panel_offsets


def test_load_panel_offsets(config_dir):
    write_cfg(
        config_dir,
        "panel:\n  window:\n    per_monitor:\n      0:\n        position_x: 30\n"
        "        position_y: 10\n      2:\n        position_x: -40\n",
    )
    assert workarea.load_panel_offsets(str(config_dir)) == {
        0: {"position_x": 30, "position_y": 10},
        2: {"position_x": -40, "position_y": 0},
    }


def test_load_panel_offsets_empty(config_dir):
    write_cfg(config_dir, "panel:\n  window:\n    alignment: right\n")
    assert workarea.load_panel_offsets(str(config_dir)) == {}


# ---------------------------------------------------------------- compute_panel


@pytest.mark.parametrize(
    "compositor,wa,taskbar,expected",
    [
        # wayland, bottom taskbar (40 px tall)
        (
            "wayland",
            (0, 0, 1920, 1040),
            "bottom",
            {"x": 16, "y": 56, "width": 250, "height": 1008, "anchor": "bottom right"},
        ),
        # x11, bottom taskbar: y = (sh - (wy+wh)) + gb
        (
            "x11",
            (0, 0, 1920, 1040),
            "bottom",
            {"x": 16, "y": 56, "width": 250, "height": 1008, "anchor": "bottom right"},
        ),
        # wayland, top taskbar: y offset is relative to the workarea top
        (
            "wayland",
            (0, 40, 1920, 1040),
            "top",
            {"x": 16, "y": 16, "width": 250, "height": 1008, "anchor": "top right"},
        ),
        # x11, top taskbar: the absolute y includes the workarea origin
        (
            "x11",
            (0, 40, 1920, 1040),
            "top",
            {"x": 16, "y": 56, "width": 250, "height": 1008, "anchor": "top right"},
        ),
        # wayland, right taskbar: panel sits at the LEFT edge
        (
            "wayland",
            (0, 0, 1700, 1080),
            "right",
            {"x": 16, "y": 16, "width": 250, "height": 1048, "anchor": "top left"},
        ),
        # wayland, left taskbar: panel sits at the RIGHT edge
        (
            "wayland",
            (100, 0, 1820, 1080),
            "left",
            {"x": 16, "y": 16, "width": 250, "height": 1048, "anchor": "top right"},
        ),
        # no taskbar
        (
            "wayland",
            (0, 0, 1920, 1080),
            "none",
            {"x": 16, "y": 16, "width": 250, "height": 1048, "anchor": "top right"},
        ),
    ],
)
def test_compute_panel(compositor, wa, taskbar, expected):
    panel = workarea.compute_panel(SCREEN, wa, taskbar, DEFAULT_GAPS, compositor)
    assert panel == expected


def test_compute_panel_kde_frame_top():
    gaps = {"top": 16, "right": 16, "bottom": 16, "left": 16}
    panel = workarea.compute_panel(
        SCREEN, (0, 40, 1920, 1040), "top", gaps, "wayland", kde_frame=(0, 30, 1920, 60)
    )
    # frame_edge = fy + fh = 90 -> y = (90 - 40) + 16, height = 1080 - 90 - 32
    assert panel["y"] == 66
    assert panel["height"] == 958


def test_compute_panel_min_height():
    gaps = {"top": 16, "right": 16, "bottom": 16, "left": 16}
    panel = workarea.compute_panel(
        SCREEN, (0, 40, 1920, 60), "top", gaps, "wayland", kde_frame=None
    )
    assert panel["height"] == 100


# ---------------------------------------------------------------- offsets & rects


@pytest.mark.parametrize(
    "compositor,anchor,x,y,px,py,expected",
    [
        ("wayland", "top right", 10, 20, 30, 40, (-20, 60)),
        ("wayland", "bottom right", 10, 20, 30, 40, (-20, 60)),
        ("wayland", "top left", 10, 20, 30, 40, (40, 60)),
        ("x11", "top right", 10, 20, 30, 40, (40, 60)),
        ("x11", "top left", 10, 20, 30, 40, (40, 60)),
        ("wayland", "top right", 10, 20, 0, 0, (10, 20)),
    ],
)
def test_apply_panel_offset(compositor, anchor, x, y, px, py, expected):
    assert workarea.apply_panel_offset(compositor, anchor, x, y, px, py) == expected


@pytest.mark.parametrize(
    "compositor,anchor,frame_w,w,off_x,off_y,expected",
    [
        ("x11", "top left", 1920, 250, 16, 20, (16, 20)),
        ("wayland", "top left", 1920, 250, 16, 20, (16, 20)),
        ("wayland", "top right", 1920, 250, 16, 20, (1654, 20)),
        ("x11", "top right", 1920, 250, 16, 20, (1686, 20)),
    ],
)
def test_rect_from_offsets(compositor, anchor, frame_w, w, off_x, off_y, expected):
    assert workarea.rect_from_offsets(compositor, anchor, frame_w, w, off_x, off_y) == expected


def test_align_panel_side():
    gaps = {"top": 16, "right": 16, "bottom": 16, "left": 5}
    panel = {"x": 16, "y": 16, "width": 250, "height": 1008, "anchor": "bottom right"}
    out = workarea.align_panel_side(dict(panel), gaps, "left")
    assert out["anchor"] == "bottom left"
    assert out["x"] == 5

    panel = {"x": 16, "y": 16, "width": 250, "height": 1008, "anchor": "top right"}
    out = workarea.align_panel_side(panel, gaps, "left")
    assert out["anchor"] == "top left"
    assert out["x"] == 5

    panel = {"x": 16, "y": 16, "width": 250, "height": 1008, "anchor": "top right"}
    out = workarea.align_panel_side(panel, gaps, "right")
    assert out == panel


def test_global_bounds():
    monitors = [
        {"index": 0, "x": 0, "y": 0, "width": 1920, "height": 1080},
        {"index": 1, "x": 1920, "y": 0, "width": 1280, "height": 720},
    ]
    assert workarea.global_bounds(monitors) == (3200, 1080)


# ---------------------------------------------------------------- base geometry


def _monitor(index=0, x=0, y=0, w=1920, h=1080):
    return {"index": index, "name": "m%d" % index, "width": w, "height": h, "x": x, "y": y, "scale": 1}


def test_base_geometry_wayland_top():
    panel, frame_w, frame_h = workarea._base_geometry_for(
        _monitor(),
        (0, 40, 1920, 1040),
        "top",
        None,
        DEFAULT_GAPS,
        "wayland",
        "right",
    )
    assert panel == {"x": 16, "y": 16, "width": 250, "height": 1008, "anchor": "top right"}
    assert (frame_w, frame_h) == (1920, 1040)


def test_base_geometry_secondary_monitor_no_taskbar():
    panel, frame_w, frame_h = workarea._base_geometry_for(
        _monitor(index=1, x=1920, y=0, w=1280, h=720),
        (0, 40, 1920, 1040),
        "top",
        None,
        DEFAULT_GAPS,
        "wayland",
        "right",
    )
    # The taskbar workarea does not overlap this monitor -> full height, no taskbar.
    assert panel == {"x": 16, "y": 16, "width": 250, "height": 688, "anchor": "top right"}
    assert (frame_w, frame_h) == (1280, 720)


# ---------------------------------------------------------------- compute_per_monitor


def test_compute_per_monitor(monkeypatch, config_dir):
    write_cfg(
        config_dir,
        "panel:\n  window:\n    per_monitor:\n      0:\n        position_x: 30\n"
        "        position_y: 10\n",
    )
    monkeypatch.setattr(workarea, "get_net_workarea", lambda: (0, 40, 1920, 1040))
    monkeypatch.setattr(workarea, "kde_panel_frame", lambda screen: None)
    monitors = [_monitor(0, 0, 0, 1920, 1080), _monitor(1, 1920, 0, 1280, 720)]

    result = workarea.compute_per_monitor(monitors, DEFAULT_GAPS, "wayland", "right", str(config_dir))

    assert result["compositor"] == "wayland"
    assert result["heights"] == [1008, 688]

    m0 = result["monitors"][0]
    # base (16, 16) + offset (30, 10); wayland right anchor flips the x sign.
    assert m0["panel"]["x"] == -14
    assert m0["panel"]["y"] == 26
    assert m0["panel"]["base_x"] == 16
    assert m0["panel"]["base_y"] == 16

    m1 = result["monitors"][1]
    assert m1["panel"]["x"] == 16
    assert m1["panel"]["y"] == 16
    assert m1["panel"]["base_x"] == 16
    assert m1["panel"]["base_y"] == 16


def test_compute_per_monitor_x11(monkeypatch, config_dir):
    write_cfg(config_dir, "panel:\n  window:\n    alignment: right\n")
    monkeypatch.setattr(workarea, "get_net_workarea", lambda: (0, 40, 1920, 1040))
    monkeypatch.setattr(workarea, "kde_panel_frame", lambda screen: None)

    result = workarea.compute_per_monitor(
        [_monitor(0)], DEFAULT_GAPS, "x11", "right", str(config_dir)
    )
    m0 = result["monitors"][0]
    # x11 top taskbar: y = wy + gt
    assert m0["panel"]["y"] == 56
    assert m0["panel"]["anchor"] == "top right"


# ---------------------------------------------------------------- gaps_for_rect round trip


@pytest.mark.parametrize(
    "taskbar,wa,compositor,frame_w",
    [
        ("none", (0, 0, 1920, 1080), "wayland", 1920),
        ("top", (0, 40, 1920, 1040), "wayland", 1920),
    ],
)
def test_gaps_for_rect_round_trip(monkeypatch, taskbar, wa, compositor, frame_w):
    monkeypatch.setattr(workarea, "get_net_workarea", lambda: wa)
    monkeypatch.setattr(workarea, "kde_panel_frame", lambda screen: None)
    monitor = _monitor()
    monitors = [monitor]

    panel = workarea.compute_panel(SCREEN, wa, taskbar, DEFAULT_GAPS, compositor)
    left, top = workarea.rect_from_offsets(
        compositor, panel["anchor"], frame_w, panel["width"], panel["x"], panel["y"]
    )
    rect = {"x": left, "y": top, "w": panel["width"], "h": panel["height"]}

    gaps = workarea.gaps_for_rect(
        monitors, 0, rect["x"], rect["y"], rect["w"], rect["h"], compositor
    )["gap"]

    # Feeding the derived gaps back reproduces the same panel geometry.
    panel2 = workarea.compute_panel(SCREEN, wa, taskbar, gaps, compositor)
    left2, top2 = workarea.rect_from_offsets(
        compositor, panel2["anchor"], frame_w, panel2["width"], panel2["x"], panel2["y"]
    )
    assert (left2, top2, panel2["width"], panel2["height"]) == (
        rect["x"],
        rect["y"],
        rect["w"],
        rect["h"],
    )


def test_gaps_for_rect_values(monkeypatch):
    monkeypatch.setattr(workarea, "get_net_workarea", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(workarea, "kde_panel_frame", lambda screen: None)
    out = workarea.gaps_for_rect(
        [_monitor()], 0, 1654, 16, 250, 1048, "wayland"
    )
    assert out["taskbar"] == "none"
    assert out["frame_w"] == 1920
    assert out["gap"] == {"top": 16, "right": 16, "bottom": 16, "left": 1654}