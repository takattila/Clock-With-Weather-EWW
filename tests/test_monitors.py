"""Pure monitor-geometry helpers of scripts/core/monitors.py.

Covers the adaptive window height (fits the smallest usable screen, i.e.
monitor height minus the taskbar work-area inset) and the virtual-desktop
bounding box used for cross-monitor dragging.
"""

import monitors


def _mon(index, x, y, w, h):
    return {"index": index, "x": x, "y": y, "width": w, "height": h}


# The live two-monitor setup used for verification:
# eDP-1 (small) 1368x768 at x=0, DP-1 1920x1080 at x=1368, with a 30px top
# panel given by the global _NET_WORKAREA (0,30,3288,1050).
TWIN = [_mon(0, 0, 0, 1368, 768), _mon(1, 1368, 0, 1920, 1080)]
WORKAREA = (0, 30, 3288, 1050)


def test_usable_height_no_workarea_is_full_height():
    assert monitors.usable_height(_mon(0, 0, 0, 1920, 1080)) == 1080
    assert monitors.usable_height(_mon(1, 1368, 0, 1368, 768), None) == 768


def test_usable_height_subtracts_top_taskbar():
    # eDP-1 (768 tall) overlaps the 30px top panel -> 768 - 30 = 738.
    assert monitors.usable_height(TWIN[0], WORKAREA) == 738
    # DP-1 (1080 tall) also overlaps it -> 1050.
    assert monitors.usable_height(TWIN[1], WORKAREA) == 1050


def test_usable_height_ignores_monitor_outside_workarea_span():
    # The work area only reaches monitor at x<1500; a monitor at x=2000 sits
    # outside the taskbar's span and keeps its full height.
    wa = (0, 30, 1500, 600)
    outside = _mon(1, 2000, 0, 1920, 1080)
    assert monitors.usable_height(outside, wa) == 1080
    # The in-span monitor keeps its taskbar inset (top 30 + bottom 450).
    assert monitors.usable_height(_mon(0, 0, 0, 1920, 1080), wa) == 600


def test_usable_height_bottom_taskbar():
    # A bottom panel: work area starts at the top of the monitor.
    mon = _mon(0, 0, 0, 1920, 1080)
    assert monitors.usable_height(mon, (0, 0, 1920, 1040)) == 1040


def test_adaptive_window_height_fits_smallest_screen():
    # Theme editor natural 760 -> shrinks to the small screen's 738.
    assert monitors.adaptive_window_height(TWIN, 760, WORKAREA) == 738
    # Weather form 380 < smallest usable -> stays 380.
    assert monitors.adaptive_window_height(TWIN, 380, WORKAREA) == 380


def test_adaptive_window_height_no_workarea_uses_full_smallest_height():
    assert monitors.adaptive_window_height(TWIN, 760, None) == 760
    assert monitors.adaptive_window_height(TWIN, 900, None) == 768


def test_adaptive_window_height_single_monitor():
    mons = [_mon(0, 0, 0, 1920, 1080)]
    assert monitors.adaptive_window_height(mons, 760, WORKAREA) == 760
    # A very short monitor dominates.
    short = [_mon(0, 0, 0, 1024, 600)]
    assert monitors.adaptive_window_height(short, 760, (0, 0, 1024, 580)) == 580


def test_desktop_bounds_union_of_monitors():
    x0, y0, w, h = monitors.desktop_bounds(TWIN)
    assert (x0, y0) == (0, 0)
    assert w == 1368 + 1920  # 3288
    assert h == 1080  # tallest monitor's height


def test_desktop_bounds_empty():
    assert monitors.desktop_bounds([]) == (0, 0, 0, 0)
