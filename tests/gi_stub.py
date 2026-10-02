"""Headless `gi` stand-in, so rain.py can be imported without PyGObject.

rain.py (like every GTK entry point here) does
`sys.exit("rain: GTK3 unavailable: ...")` when `import gi` fails. That is
exactly the case on the GitHub runners - they install requirements.txt, which
has no PyGObject - so tests/test_rain.py could not even be collected in CI and
every commit on the branch went red with "no tests ran".

Skipping the module (what tests/test_rain_panel.py does) is not an option here:
the rain tests do not need a display, they replace every GTK call themselves
(monkeypatched Gtk.Window / Gtk.Overlay / CssProvider, a fake Gdk.Window for the
input-hole and EWMH calls). All they need is for the `import gi` at the top of
rain.py to succeed. This module puts a stub in sys.modules for exactly that.

Two safety properties:

  * Only a stub call raises. Anything the tests did not fake explodes loudly
    (AssertionError) instead of silently returning a dummy, so a test cannot
    pass against a stub where it would fail against real GTK.
  * `Gdk.Display.get_default()` / `Gdk.Screen.get_default()` return None, the
    same as real GTK3 without a DISPLAY, so the display-less code paths
    (the 1920x1080 fallback geometry) are the ones under test.

install() returns the real PyGObject whenever it is importable, so on a desktop
the suite still runs against the actual GTK - only CI (and anyone without
PyGObject) sees the stub. Set EWW_TEST_GI_STUB=1 to force the stub and check
the CI path locally.
"""

import os
import sys
import types

ENV_FORCE = "EWW_TEST_GI_STUB"


class _Stub:
    """A callable that fails the test if the code under test reaches it."""

    def __init__(self, name):
        self._name = name

    def __repr__(self):
        return "<gi stub %s>" % self._name

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        return _Stub("%s.%s" % (self._name, attr))

    def __call__(self, *args, **kwargs):
        raise AssertionError(
            "the gi stub was called: %s() - fake it in the test instead of "
            "relying on the stub" % self._name)


class _Namespace(types.ModuleType):
    """A module that hands out a fresh _Stub for every attribute.

    The attribute is cached on the module, so `monkeypatch.setattr(rain.Gtk,
    "CssProvider", ...)` finds it without the name having to be declared here,
    and rain.py can grow a new GTK call without the stub needing a new entry.
    """

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = _Stub("%s.%s" % (self.__name__, name))
        setattr(self, name, value)
        return value


def _real_gi():
    """The installed PyGObject, or None when there is none."""
    if os.environ.get(ENV_FORCE):
        return None
    try:
        import gi
    except Exception:
        return None
    return gi


def _install_stub():
    """Register `gi` and `gi.repository` in sys.modules and return the stub."""
    gi = _Namespace("gi")
    gi.require_version = lambda *_args, **_kwargs: None
    gi.require_foreign = lambda *_args, **_kwargs: None

    repository = _Namespace("gi.repository")
    gi.repository = repository
    for name in ("Gdk", "GLib", "Gtk", "GtkLayerShell"):
        setattr(repository, name, _Namespace("gi.repository.%s" % name))

    repository.Gdk.Display.get_default = lambda: None
    repository.Gdk.Screen.get_default = lambda: None

    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository
    return gi


def install():
    """Make `import gi` work for the GTK module a test is about to import.

    Returns the module that will be found in sys.modules["gi"], so a caller can
    assert on it. Calling it twice is harmless.
    """
    gi = sys.modules.get("gi") or _real_gi()
    if gi is None:
        gi = _install_stub()
    return gi


def uninstall():
    """Take the stub back out of sys.modules; True if one was removed.

    Call it right after the module under test has been imported. The stub is
    process-global, and the other GTK test modules skip themselves when PyGObject
    is missing - leaving the stub behind would drag them into running against a
    double they were never written for. An already-imported module keeps the
    references it took, so rain.py is unaffected. The real PyGObject is never
    touched.
    """
    gi = sys.modules.get("gi")
    if gi is None or not isinstance(gi, _Namespace):
        return False
    for name in ("gi", "gi.repository"):
        module = sys.modules.get(name)
        if isinstance(module, _Namespace):
            del sys.modules[name]
    return True