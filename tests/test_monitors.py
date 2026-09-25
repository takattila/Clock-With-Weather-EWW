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


# --- hotplug/relayout detection signatures ---------------------------------
# The watcher polls --signature (cheap, /sys only) plus the ACTIVE layout
# signature. The latter is what catches a monitor that is only disabled and
# resolution/position changes, which leave /sys untouched.

def _named(index, name, x, y, w, h):
    m = _mon(index, x, y, w, h)
    m["name"] = name
    return m


def test_topology_signature_uses_name_and_geometry():
    sig = monitors.topology_signature(
        [_named(0, "DP-1", 1368, 0, 1920, 1080), _named(1, "eDP-1", 0, 0, 1368, 768)]
    )
    assert sig == "DP-1:1920x1080+1368+0|eDP-1:1368x768+0+0"


def test_topology_signature_is_order_independent():
    # `xrandr --primary` swapping the primary monitor reorders the enumeration
    # but leaves every index -> monitor mapping, window and config key in
    # place, so it must not look like a layout change.
    a = [_named(0, "DP-1", 1368, 0, 1920, 1080), _named(1, "eDP-1", 0, 0, 1368, 768)]
    b = list(reversed(a))
    assert monitors.topology_signature(a) == monitors.topology_signature(b)


def test_topology_signature_changes_on_the_events_sysfs_cannot_see():
    base = [_named(0, "DP-1", 1368, 0, 1920, 1080), _named(1, "eDP-1", 0, 0, 1368, 768)]
    sig = monitors.topology_signature(base)
    # A disabled output is gone from the compositor's list (the DRM connector
    # stays "connected", so --signature does not change).
    assert monitors.topology_signature(base[:1]) != sig
    # Resolution change.
    resized = [_named(0, "DP-1", 1368, 0, 1600, 900), _named(1, "eDP-1", 0, 0, 1368, 768)]
    assert monitors.topology_signature(resized) != sig
    # Position change.
    moved = [_named(0, "DP-1", 0, 0, 1920, 1080), _named(1, "eDP-1", 1920, 0, 1368, 768)]
    assert monitors.topology_signature(moved) != sig


def test_topology_signature_no_monitors():
    assert monitors.topology_signature([]) == "none"


def test_signature_includes_connector_enable_state(tmp_path, monkeypatch):
    # A monitor that is switched off (`xrandr --output X --off`) keeps its DRM
    # status/modes, so --signature must carry the `enabled` state as well.
    drm = tmp_path / "card1-DP-1"
    drm.mkdir()
    (drm / "status").write_text("connected\n")
    (drm / "modes").write_text("1920x1080\n1280x1024\n")
    (drm / "enabled").write_text("enabled\n")
    monkeypatch.setattr(monitors, "SYSFS_DRM", str(tmp_path))
    assert monitors.signature() == "card1-DP-1=connected:1920x1080:enabled"

    (drm / "enabled").write_text("disabled\n")
    assert monitors.signature() == "card1-DP-1=connected:1920x1080:disabled"


def test_signature_without_enabled_file(tmp_path, monkeypatch):
    # Older kernels have no `enabled` file: the signature still works, with an
    # empty enable state.
    drm = tmp_path / "card1-eDP-1"
    drm.mkdir()
    (drm / "status").write_text("connected\n")
    (drm / "modes").write_text("1368x768\n")
    monkeypatch.setattr(monitors, "SYSFS_DRM", str(tmp_path))
    assert monitors.signature() == "card1-eDP-1=connected:1368x768:"
