"""Monitor-change detection of scripts/core/monitor_watch.py.

The watcher must notice EVERY layout change, not just the hotplug that the
/sys/class/drm connector state can see: a monitor that is only disabled or a
resolution/position change leave /sys untouched, and then the windows of the
vanished monitor are never re-laid-out.
"""

import pytest

import monitor_watch


class _FakeAtomNames:
    def __init__(self, names):
        self._names = names

    def get_atom_name(self, atom):
        return self._names[atom]


class _FakeMonitor:
    def __init__(self, atom, x, y, w, h):
        self.name = atom
        self.x = x
        self.y = y
        self.width_in_pixels = w
        self.height_in_pixels = h


class _FakeMonitorsReply:
    def __init__(self, monitors):
        self.monitors = monitors


def _install_fake_xrandr(monkeypatch, monitors):
    monkeypatch.setattr(
        monitor_watch,
        "_xrandr",
        type("FakeRandr", (), {"get_monitors": staticmethod(lambda root: _FakeMonitorsReply(monitors))}),
    )


def test_x_monitor_signature_formats_name_and_geometry(monkeypatch):
    # The live two-monitor setup: DP-1 1920x1080 at x=1368, eDP-1 1368x768.
    _install_fake_xrandr(
        monkeypatch,
        [
            _FakeMonitor(691, 1368, 0, 1920, 1080),
            _FakeMonitor(412, 0, 0, 1368, 768),
        ],
    )
    dpy = _FakeAtomNames({691: "DP-1", 412: "eDP-1"})
    sig = monitor_watch._x_monitor_signature(dpy, object())
    assert sig == "DP-1:1920x1080+1368+0|eDP-1:1368x768+0+0"


def test_x_monitor_signature_is_order_independent(monkeypatch):
    a, b = _FakeMonitor(1, 0, 0, 1368, 768), _FakeMonitor(2, 1368, 0, 1920, 1080)
    _install_fake_xrandr(monkeypatch, [a, b])
    dpy = _FakeAtomNames({1: "eDP-1", 2: "DP-1"})
    first = monitor_watch._x_monitor_signature(dpy, object())
    _install_fake_xrandr(monkeypatch, [b, a])
    assert monitor_watch._x_monitor_signature(dpy, object()) == first


def test_x11_topology_reads_the_live_monitor_list(monkeypatch):
    _install_fake_xrandr(monkeypatch, [_FakeMonitor(7, 0, 0, 1920, 1080)])
    monkeypatch.setattr(monitor_watch, "_xdisplay", type("FakeDisplay", (), {"Display": staticmethod(lambda: _FakeConn())}))
    monkeypatch.setattr(monitor_watch, "_x_conn", None)
    assert monitor_watch.x11_topology() == "DP-1:1920x1080+0+0"


def test_x11_topology_empty_without_xlib(monkeypatch):
    # Wayland host, or python-xlib not installed: the caller falls back to the
    # slow compositor enumeration check.
    monkeypatch.setattr(monitor_watch, "_xdisplay", None)
    assert monitor_watch.x11_topology() == ""


def test_x11_topology_empty_on_dead_connection(monkeypatch):
    # An X server restart must not make the watcher blind forever: the stale
    # connection is dropped so the next poll reconnects.
    class _Dead:
        def screen(self):
            raise RuntimeError("connection lost")

        def close(self):
            pass

    monkeypatch.setattr(monitor_watch, "_xdisplay", type("FakeDisplay", (), {"Display": staticmethod(lambda: _Dead())}))
    monkeypatch.setattr(monitor_watch, "_x_conn", _Dead())
    assert monitor_watch.x11_topology() == ""
    assert monitor_watch._x_conn is None


def test_topology_signature_failure_is_swallowed(monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(monitor_watch.subprocess, "check_output", _boom)
    assert monitor_watch.topology_signature() == ""
    assert monitor_watch.signature() == ""


class _FakeConn:
    def __init__(self):
        self.root = object()

    def screen(self):
        return type("FakeScreen", (), {"root": self.root})()

    def get_atom_name(self, atom):
        return {7: "DP-1"}[atom]


class _Stop(Exception):
    """Raised by the fake relayout() to end the watcher's endless loop."""


class _FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def _run_main(monkeypatch, clock, values, relayouts):
    """Drive monitor_watch.main() with everything but the real world faked."""
    monkeypatch.setattr(monitor_watch.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(monitor_watch.time, "sleep", clock.sleep)
    # No udev events (proc=None -> the loop just ticks on POLL_INTERVAL).
    monkeypatch.setattr(
        monitor_watch.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    monkeypatch.setattr(monitor_watch, "signature", lambda: "cheap")
    remaining = list(values)

    def _topology():
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    monkeypatch.setattr(monitor_watch, "topology_signature", _topology)

    def _relayout():
        relayouts.append(clock.now)
        raise _Stop()

    monkeypatch.setattr(monitor_watch, "relayout", _relayout)
    monkeypatch.setattr(monitor_watch.sys, "argv", ["monitor_watch.py", "/tmp/eww"])
    return _topology


def test_main_uses_slow_topology_check_when_x11_is_unavailable(monkeypatch):
    # Wayland (or no python-xlib): the layout is only re-read from the
    # compositor every TOPOLOGY_INTERVAL, but a change must still relayout.
    clock = _FakeClock()
    relayouts = []
    _run_main(monkeypatch, clock, ["t0", "t0", "t1", "t1"], relayouts)
    monkeypatch.setattr(monitor_watch, "x11_topology", lambda: "")
    with pytest.raises(_Stop):
        monitor_watch.main()
    assert len(relayouts) == 1
    # The first check only happens at the initial sample; the next one no
    # earlier than TOPOLOGY_INTERVAL.
    assert clock.now >= monitor_watch.TOPOLOGY_INTERVAL


def test_main_never_spawns_the_slow_check_on_x11(monkeypatch):
    # With the fast X11 poll available the subprocess enumeration must not run
    # at all: the 5 s poll already sees every layout change.
    clock = _FakeClock()
    relayouts = []
    values = _run_main(monkeypatch, clock, [], relayouts)
    layouts = iter(["x0", "x0", "x0", "x1", "x1"])
    monkeypatch.setattr(monitor_watch, "x11_topology", lambda: next(layouts))
    with pytest.raises(_Stop):
        monitor_watch.main()
    assert len(relayouts) == 1
    assert values is not None
    assert relayouts[0] < monitor_watch.TOPOLOGY_INTERVAL  # caught by the 5 s poll
