"""Ownership forwarding: clicks landing in the OTHER widget's transparent
canvas must open the menu of the widget visibly under the cursor."""

from ctx import choose_widget

RECTS = [
    # clock visible rect (bottom-right quadrant of monitor 0)
    {"widget": "clock", "monitor": 0, "x": 1692, "y": 880, "w": 220, "h": 131},
    # panel column incl. its transparent canvas strip
    {"widget": "panel", "monitor": 0, "x": 800, "y": 200, "w": 250, "h": 1045},
]


def test_claimed_rect_contains_cursor_keeps_claimed():
    assert choose_widget("clock", 0, (1700, 900), RECTS) == ("clock", 0)
    assert choose_widget("panel", 0, (810, 210), RECTS) == ("panel", 0)


def test_click_in_other_widgets_canvas_is_forwarded():
    # Cursor over the clock's visible part, click delivered by the panel's
    # overlapping transparent strip -> menu must go to the CLOCK.
    assert choose_widget("panel", 0, (1700, 900), RECTS) == ("clock", 0)


def test_click_outside_claimed_and_others_keeps_claimed():
    assert choose_widget("clock", 0, (100, 100), RECTS) == ("clock", 0)


def test_no_cursor_or_missing_rects_keep_claimed():
    assert choose_widget("panel", 0, None, RECTS) == ("panel", 0)
    assert choose_widget("panel", 0, (1700, 900), []) == ("panel", 0)


def test_ambiguity_prefers_claimed():
    both = RECTS + [
        # a second widget whose visible rect ALSO covers the point
        {"widget": "clock", "monitor": 1, "x": 1692, "y": 880, "w": 220, "h": 131},
    ]
    # claimed clock@0 contains the point -> it wins even though another
    # candidate contains it too.
    assert choose_widget("clock", 0, (1700, 900), both) == ("clock", 0)


def test_smallest_containing_rect_wins():
    rects = [
        {"widget": "panel", "monitor": 2, "x": 5000, "y": 5000, "w": 250, "h": 1045},
        {"widget": "clock", "monitor": 0, "x": 800, "y": 200, "w": 240, "h": 836},
        {"widget": "clock", "monitor": 1, "x": 800, "y": 200, "w": 300, "h": 900},
    ]
    # claimed panel@2 misses the point; two other rects contain it -> the
    # most specific (smallest) hit wins.
    assert choose_widget("panel", 2, (900, 300), rects) == ("clock", 0)
