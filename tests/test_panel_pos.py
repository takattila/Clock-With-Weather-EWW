"""Shared widget-adjacent panel placement (scripts/move/panel_pos.py)."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(REPO_ROOT / "scripts" / "move"))

from panel_pos import panel_position  # noqa: E402


def rect(left=0, top=0, w=300, h=200, frame_w=1920, frame_h=1080):
    return {
        "left": left, "top": top,
        "width": w, "height": h,
        "frame_w": frame_w, "frame_h": frame_h,
    }


def test_opens_on_the_right_when_there_is_more_space():
    px, py = panel_position(rect(left=100), 200, 320, 10)
    assert px == 100 + 300 + 10
    assert py == 0  # (200 - 320) // 2 is negative -> clamped to 0


def test_opens_on_the_left_when_the_right_side_is_tighter():
    px, py = panel_position(rect(left=1700, w=200), 200, 320, 10)
    assert px == 1700 - 10 - 200


def test_vertical_center_falls_inside_the_frame():
    px, py = panel_position(rect(left=100, top=50, h=600), 200, 320, 10)
    assert px == 100 + 300 + 10
    assert py == 50 + (600 - 320) // 2


def test_clamps_when_the_panel_is_taller_than_the_frame():
    px, py = panel_position(rect(frame_h=200), 200, 320, 10)
    assert py == 0


def test_clamps_next_to_the_widget_when_the_chosen_side_is_too_small():
    # Widget fills the whole frame: the right side (0 free px) cannot host the
    # panel, so it clamps against the right frame edge.
    px, py = panel_position(rect(left=0, w=1920, h=200), 200, 320, 10)
    assert px == max(0, 1920 - 200)


def test_tie_breaks_to_the_right():
    px, py = panel_position(rect(left=810, w=300), 200, 320, 10)
    assert px == 810 + 300 + 10