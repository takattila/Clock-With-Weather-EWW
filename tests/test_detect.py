"""Shared compositor detection (scripts/core/detect.py)."""

import detect
import monitors
import workarea


def test_env_wayland_display():
    assert detect.compositor({"WAYLAND_DISPLAY": "wayland-0"}) == "wayland"


def test_env_swaysock():
    assert detect.compositor({"SWAYSOCK": "/run/sway-ipc"}) == "wayland"


def test_session_type_wayland_case_insensitive():
    assert detect.compositor({"XDG_SESSION_TYPE": "Wayland"}) == "wayland"


def test_kwin_wayland_process_suffices_without_env():
    # The SSH/autostart case: empty env, but the session compositor runs.
    assert detect.compositor({}, procs=[("kwin_wayland", False)]) == "wayland"
    assert detect.compositor({}, procs=[("sway", True)]) == "wayland"


def test_gnome_shell_needs_wayland_in_its_env():
    # GNOME also runs on X11, so the binary name alone is not enough.
    assert detect.compositor({}, procs=[("gnome-shell", True)]) == "wayland"
    assert detect.compositor({}, procs=[("gnome-shell", False)]) == "x11"


def test_plain_x11_session():
    procs = [("Xorg", True), ("kwin_x11", True), ("plasmashell", False)]
    assert detect.compositor({"DISPLAY": ":0"}, procs=procs) == "x11"
    assert detect.compositor({}, procs=procs) == "x11"


def test_real_scan_hook(monkeypatch):
    monkeypatch.setattr(detect, "_real_session_procs", lambda: [("sway", False)])
    assert detect.compositor({}) == "wayland"


def test_monitors_and_workarea_share_the_detector():
    # A mismatch would open native layer-shell windows while geometry math
    # assumes X11 (or vice versa) -- silently breaking placement on KWin.
    assert monitors.detect_compositor is detect.compositor
    assert workarea.detect_compositor is detect.compositor
