"""menu_pos.menu_position: placement from pre-fetched geometry."""

import menu_pos

DATA = {
    "compositor": "x11",
    "monitors": [
        {"index": 0, "name": "a", "x": 0, "y": 0, "width": 1920, "height": 1080},
        {"index": 1, "name": "b", "x": 1920, "y": 0, "width": 1368, "height": 768},
    ],
}


def test_x11_opens_at_cursor_on_cursor_monitor():
    pos = menu_pos.menu_position("clock", 0, DATA, None, cursor=(2000, 300))
    assert pos["screen"] == 1
    # clamped so the whole menu fits INSIDE the cursor's monitor
    assert pos["x"] == 2000 - 1920
    assert pos["y"] == min(300, 768 - menu_pos.MENU_H)


def test_x11_clamps_to_monitor_bounds():
    pos = menu_pos.menu_position("clock", 1, DATA, None, cursor=(3287, 767))
    assert pos["screen"] == 1
    assert pos["x"] == 1368 - menu_pos.MENU_W
    assert pos["y"] == 768 - menu_pos.MENU_H


def test_x11_falls_back_to_widget_monitor_corner_without_cursor(monkeypatch):
    # keep the real xdotool out of the unit test
    monkeypatch.setattr(menu_pos, "get_cursor", lambda: None)
    pos = menu_pos.menu_position("clock", 0, DATA, None, cursor=None)
    assert pos["screen"] == 0
    assert (pos["x"], pos["y"]) == (8, 8)


def test_unknown_monitor_exits():
    import pytest

    with pytest.raises(ValueError):
        menu_pos.menu_position("clock", 9, DATA, None, cursor=(0, 0))
