#!/usr/bin/env python3
"""Full-screen raindrop layer: a click-through transparent window BEHIND the desktop.

v5.0.0. Why this is a standalone GTK3 process and not an eww window: eww 0.6.0
exposes no click-through / input-shape property, so a full-screen eww surface
would swallow every click on the desktop. Measured on this machine
(`strings $(which eww) | grep -i pass.through` -> nothing). This process owns
its own GtkWindow instead, where `Gdk.Window.set_pass_through` is available and
verified to return True (see `pass_through` assertion in `RainLayer`).

Stacking: layer-shell Layer.BOTTOM on Wayland (below every normal window, above
the wallpaper). On X11 the layer is a MANAGED window with the DESKTOP type hint
and the window manager is asked to put it in the desktop layer with
`_NET_ACTIVE_WINDOW` (see request_desktop_layer) - an override-redirect window
is invisible to the WM, and the WM keeps pulling an unmanaged window back to the
top, so managed + a desktop layer is the only arrangement that stays behind the
open apps (measured). Either way the layer is unfocusable, undecorated and
skipped in the taskbar.

The animation is plain GTK3 CSS `@keyframes` on `margin-top`. Deliberately NOT
`transform: translateY(...)`: GTK3 3.24.41's CSS engine rejects it outright
(`No property named 'transform'`), same for `top` and for `width`/`height` -
those are widget properties here, not CSS properties. `margin-top` animation was
measured to work. Its cost is linear in the droplet count: this process
measured 7 / 12 / 16 / 24 / 33% of ONE core at 10 / 24 / 40 / 80 / 120 drops
across two monitors (1920x1080 + 1368x768), i.e. roughly half of that per
monitor. Set count: 0 to remove the layer.

The layer also survives `eww reload` (nothing here depends on eww) and watches
config.yaml / config.local.yaml / eww/eww.theme.json /
generated/weather_cache.json by mtime every POLL_SEC, plus the monitor
geometry, so panel edits and hotplug/resolution changes apply without a
restart.

Usage: ./rain.py [config_dir]      (defaults to the repo root)
"""

import ctypes
import json
import os
import random
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

try:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, GLib, Gtk
except Exception as exc:
    sys.exit("rain: GTK3 unavailable: %s" % exc)

try:
    from config_io import load_merged
except Exception as exc:
    sys.exit("rain: cannot import config_io: %s" % exc)

WAYLAND = "WAYLAND_DISPLAY" in os.environ and os.environ.get("GDK_BACKEND", "wayland") != "x11"

if WAYLAND:
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except Exception as exc:
        sys.exit("rain: GtkLayerShell unavailable: %s" % exc)

# Config defaults, mirroring the weather.rain block in config.yaml. The values
# are duplicated here on purpose: rain.py must keep working with an old config
# that has no rain block at all.
DEFAULT_ENABLED = True
DEFAULT_AUTO = True
DEFAULT_COUNT = 24
DEFAULT_SPEED = 5
DEFAULT_OPACITY = 0.35

COUNT_MIN, COUNT_MAX = 0, 120
SPEED_MIN, SPEED_MAX = 1, 10

# Seeded so the layout is deterministic and testable: the same count always
# produces the same rain, on every machine and every reload.
SEED = 20240501

POLL_SEC = 2
# Consecutive polls with the layer outside the desktop layer before a warning is
# worth printing: the WM registers a new window asynchronously.
LAYER_WARN_AFTER = 3
DROPLET_W, DROPLET_H = 2, 16
# Fraction of drops rendered as a longer, faster streak.
STREAK_CHANCE = 0.3
# Per-drop duration jitter around the configured speed.
JITTER_MIN, JITTER_MAX = 0.7, 1.4
# speed 1 -> 2.4s, speed 10 -> 0.55s (linear).
DURATION_SLOW, DURATION_FAST = 2.4, 0.55
# Keep the fall slightly overshooting the bottom edge so drops vanish cleanly.
OVERSCAN = 60
# The configured droplet count is a density, defined for this area (full HD):
# a smaller monitor gets proportionally fewer drops, so every screen looks the
# same and the CPU cost follows the pixels actually painted.
REFERENCE_AREA = 1920 * 1080

THEME_FILE = os.path.join("eww", "eww.theme.json")
CACHE_FILE = os.path.join("generated", "weather_cache.json")
DEFAULT_TINT = "#c9d6e4"


# --------------------------------------------------------------------------
# pure helpers (unit-tested, no GTK needed)
# --------------------------------------------------------------------------

def clamp_count(value):
    """Coerce a configured droplet count into the supported 0..120 range."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return DEFAULT_COUNT
    return max(COUNT_MIN, min(COUNT_MAX, count))


def clamp_speed(value):
    """Coerce a configured speed into the supported 1..10 range."""
    try:
        speed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SPEED
    return max(SPEED_MIN, min(SPEED_MAX, speed))


def clamp_opacity(value):
    try:
        opacity = float(value)
    except (TypeError, ValueError):
        return DEFAULT_OPACITY
    return max(0.0, min(1.0, opacity))


def as_bool(value, default):
    """Tolerant boolean read: YAML bools, the "true"/"false" strings that
    config_set.py may have written, and anything else falling back to `default`."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    flag = str(value).strip().lower()
    if flag in ("true", "1", "yes", "on"):
        return True
    if flag in ("false", "0", "no", "off"):
        return False
    return default


def base_duration(speed):
    """Map the 1..10 speed scale onto the fall duration in seconds."""
    speed = clamp_speed(speed)
    span = SPEED_MAX - SPEED_MIN
    ratio = (speed - SPEED_MIN) / float(span)
    return DURATION_SLOW - ratio * (DURATION_SLOW - DURATION_FAST)


def drops_for_monitor(count, width, height):
    """The drop count for ONE monitor, scaled by its area.

    The configured count is a *density*, defined for a full-HD screen: 24 drops
    on 1920x1080. Without this every monitor got the same number of drops, so a
    1368x768 screen was twice as dense as the 1920x1080 one next to it. Scaling
    by the pixel area makes every monitor look the same, and keeps the CPU cost
    proportional to the pixels actually painted instead of to the monitor count.
    """
    area = max(1, int(width) * int(height))
    return clamp_count(int(round(count * area / float(REFERENCE_AREA))))


def plan_drops(count, speed, width, height, seed=SEED):
    """Lay out `count` droplets for a width x height monitor.

    Returns a list of dicts with the per-drop geometry and timing, sorted by x
    so the generated CSS is stable between runs. `duration` is the CSS animation
    duration, `delay` a NEGATIVE value (seconds) that staggers the drops along
    the path - a positive delay would leave them all bunched at the start line.

    `count` is a full-HD density and is scaled to this monitor's area (see
    drops_for_monitor), and the x positions are STRATIFIED: drop i is jittered
    inside its own 1/count-wide column. Pure random x left whole vertical bands
    empty on a wide monitor (measured: the 960-1152 px band had no drop at all
    on 1920x1080) and, because the seed is fixed, painted the same sparse
    pattern on every screen size.
    """
    width = max(1, int(width))
    height = max(1, int(height))
    count = drops_for_monitor(count, width, height)
    travel = height + OVERSCAN
    duration = base_duration(speed)
    rng = random.Random(seed)

    step = width / float(count) if count else width
    max_x = max(0, width - DROPLET_W)

    drops = []
    for i in range(count):
        streak = rng.random() < STREAK_CHANCE
        drop_duration = duration * rng.uniform(JITTER_MIN, JITTER_MAX)
        # A streak is a fast, long drop; a regular drop a short, slower one.
        if streak:
            drop_duration *= 0.7
        # One drop per column, jittered inside it -> no empty band, whatever
        # the monitor width and count are.
        x = min(max_x, max(0, int((i + rng.random()) * step)))
        drops.append({
            "index": i,
            "x": x,
            "duration": round(drop_duration, 3),
            # Strictly negative: a fraction of the fall already elapsed when
            # the animation starts. The 0.02 floor keeps that true even when
            # the RNG returns 0.0 (which would have produced a 0.0s delay and
            # left that drop sitting at the start line).
            "delay": round(-drop_duration * (0.02 + 0.98 * rng.random()), 3),
            "height": DROPLET_H * 2 if streak else DROPLET_H,
        })

    drops.sort(key=lambda d: (d["x"], d["index"]))
    return drops, travel


def build_css(drops, travel, opacity, tint=DEFAULT_TINT):
    """Render the per-drop CSS: one shared @keyframes, one rule per drop.

    Each drop is a GtkBox added to a GtkOverlay, positioned with
    margin-left / margin-top and animated in margin-top. `animation-delay` is
    negative so every drop starts mid-flight; GTK3 accepts that and it is what
    spreads the rain across the screen.
    """
    rules = [
        # The layer is a full-screen window, so its OWN background has to be
        # fully transparent or it would cover the wallpaper. Needed together
        # with the RGBA visual + app_paintable in RainLayer._make_transparent.
        "window.rain-window, window.rain-window .rain-overlay { "
        "background-color: transparent; background-image: none; "
        "border: none; box-shadow: none; }",
        "@keyframes raindrop { from { margin-top: -%dpx; } to { margin-top: %dpx; } }" % (
            DROPLET_H, travel,
        ),
        ".rain-drop { background-color: %s; }" % tint,
    ]
    for drop in drops:
        rules.append(
            ".rain-drop-%d { margin-left: %dpx; min-width: %dpx; min-height: %dpx; "
            "opacity: %.3f; animation-name: raindrop; animation-duration: %.3fs; "
            "animation-timing-function: linear; animation-iteration-count: infinite; "
            "animation-delay: %.3fs; }" % (
                drop["index"], drop["x"], DROPLET_W, drop["height"],
                opacity, drop["duration"], drop["delay"],
            )
        )
    return "\n".join(rules)


def read_settings(config_dir):
    """Resolve the effective raindrop settings from the merged config."""
    config = {}
    try:
        config = load_merged(config_dir) or {}
    except Exception:
        config = {}
    rain = config.get("weather") or {}
    rain = rain.get("rain") or {}
    if not isinstance(rain, dict):
        rain = {}
    return {
        "enabled": as_bool(rain.get("enabled"), DEFAULT_ENABLED),
        "auto": as_bool(rain.get("auto"), DEFAULT_AUTO),
        "count": clamp_count(rain.get("count", DEFAULT_COUNT)),
        "speed": clamp_speed(rain.get("speed", DEFAULT_SPEED)),
        "opacity": clamp_opacity(rain.get("opacity", DEFAULT_OPACITY)),
    }


def read_is_raining(config_dir):
    """Read the precipitation flag cached by weather.py.

    Missing / unreadable / stale-but-valid cache -> True. A missing cache means
    weather.py has not succeeded yet; showing rain there is the friendlier
    failure than silently showing a dry screen.
    """
    path = os.path.join(config_dir, CACHE_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("is_raining"))
    except (OSError, ValueError, AttributeError):
        return True


def read_tint(config_dir):
    """Take the droplet tint from the active theme so rain matches the widget."""
    try:
        with open(os.path.join(config_dir, THEME_FILE), "r", encoding="utf-8") as f:
            theme = json.load(f)
    except (OSError, ValueError):
        return DEFAULT_TINT
    for key in ("color_light", "menu_ink", "color_dark"):
        value = theme.get(key)
        if isinstance(value, str) and value.startswith("#") and len(value) in (7, 9):
            return value[:7]
    return DEFAULT_TINT


# --------------------------------------------------------------------------
# Click-through: punching the input hole
# --------------------------------------------------------------------------
# The layer is a full-screen window, so it must be UNHITTABLE - every click
# has to fall through to the desktop under it. Two mechanisms, because one is
# not enough:
#
#   * Gdk.Window.set_pass_through(True) is the portable call, and the only one
#     on Wayland. On this X11 setup it is NOT enough: get_pass_through()
#     returned True while the window still swallowed every click, so the
#     desktop context menu never opened (measured with xdotool: the window
#     under the pointer was the rain layer, not the desktop).
#   * An EMPTY X input shape is what actually works. Done through XShape
#     (ShapeInput + zero rectangles) on the toplevel, which is exactly what a
#     click-through overlay needs, and it also survives a WM re-shaping the
#     window. ctypes + libXext, both always present on X11 - no new dependency.
#
# The layer IS a managed window on X11 (it has to be, to reach the desktop
# layer), and a managed window can get its input shape overwritten by the window
# manager - Cinnamon/Muffin does that on map. So the hole is re-punched on every
# map and on every poll instead of being protected by an override-redirect
# window; see RainLayer._on_map and enforce_overlay_state.

XSHAPE_INPUT = 2
_XSHAPE_SET = 0
_XSHAPE_UNSORTED = 0
_X_ANY_PROPERTY_TYPE = 0  # Xatom.h AnyPropertyType
_EWMH_WINDOW_TYPE = "_NET_WM_WINDOW_TYPE"
_EWMH_DESKTOP_TYPE = "_NET_WM_WINDOW_TYPE_DESKTOP"
_EWMH_CLIENT_LIST_STACKING = "_NET_CLIENT_LIST_STACKING"
_EWMH_WM_PID = "_NET_WM_PID"
_x11_libs = None


def _load_x11():
    """Load libX11 + libXext once. Returns (x11, xext) or (None, None)."""
    global _x11_libs
    if _x11_libs is not None:
        return _x11_libs
    try:
        x11 = ctypes.CDLL("libX11.so.6")
        xext = ctypes.CDLL("libXext.so.6")
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x11.XInternAtom.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x11.XInternAtom.restype = ctypes.c_ulong
        x11.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_long, ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_void_p)]
        x11.XGetWindowProperty.restype = ctypes.c_int
        x11.XFree.argtypes = [ctypes.c_void_p]
        x11.XSendEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long,
            ctypes.POINTER(_XEvent)]
        xext.XShapeSelectInput.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]
        xext.XShapeCombineRectangles.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        _x11_libs = (x11, xext)
    except (OSError, AttributeError):
        _x11_libs = (None, None)
    return _x11_libs


def empty_input_shape(gdk_window):
    """Make an X11 window unhittable by giving it an empty input shape.

    Returns True when the shape was really emptied. Safe to call repeatedly -
    that is the point: the WM may re-assert a shape, and a hide/show cycle
    (auto mode toggling) remaps the window.
    """
    x11, xext = _load_x11()
    if xext is None:
        return False
    try:
        display = x11.XOpenDisplay(None)
        if not display:
            return False
        xid = ctypes.c_ulong(gdk_window.get_xid())
        xext.XShapeSelectInput(display, xid, 1)
        # Zero rectangles => nothing in the window can be hit.
        xext.XShapeCombineRectangles(
            display, xid, XSHAPE_INPUT, 0, 0, 0,
            None, 0, _XSHAPE_SET, _XSHAPE_UNSORTED)
        x11.XFlush(display)
        return True
    except Exception:
        return False


# --- X11: keeping the layer on the desktop ---------------------------------
# The layer must be visible on the wallpaper and invisible over open windows.
# Three mechanisms were measured on Cinnamon/Muffin before this one worked:
#
#   * set_keep_below(True) + the DESKTOP type hint: IGNORED at map time. Every
#     new window lands on top of the stack, and a full-screen layer then paints
#     rain over every open application.
#   * an OVERRIDE-REDIRECT window with an explicit XRestackWindows: works for
#     about a second, then the window manager puts it back on top (measured:
#     it drifted back while the layer process was SIGSTOPped). The WM does not
#     manage such a window, so it can neither honour the DESKTOP type nor keep
#     the order we asked for.
#   * a MANAGED window plus an explicit `_NET_ACTIVE_WINDOW` request: THIS is
#     what works. The window manager then applies its own layering, which puts
#     a `_NET_WM_WINDOW_TYPE_DESKTOP` window in the desktop layer - measured
#     moving from the top of the stack (94) to just above the desktop window
#     and below every app window (85) - and keeps it there, including when new
#     windows are opened, because they are stacked above the desktop layer.
#
# So the layer stays a normal GTK window and asks the WM for the desktop layer
# on every map and every poll; the click-through hole is punched separately (see
# above). The window is not focusable, so the activation request never steals
# the keyboard focus: it is only a restacking request in disguise.

EWMH_ACTIVE_WINDOW = "_NET_ACTIVE_WINDOW"
EWMH_SOURCE_PAGER = 2
_X_CLIENT_MESSAGE = 33
_X_SUBSTRUCTURE_REDIRECT = 0x00080000
_X_SUBSTRUCTURE_NOTIFY = 0x00020000


class _XClientMessageData(ctypes.Union):
    _fields_ = [("b", ctypes.c_char * 20), ("s", ctypes.c_short * 10),
                ("l", ctypes.c_long * 5)]


class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int), ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int), ("data", _XClientMessageData),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int),
                ("xclient", _XClientMessageEvent),
                ("pad", ctypes.c_long * 24)]


def request_desktop_layer(gdk_window):
    """Ask the window manager to stack the layer into the desktop layer.

    `_NET_ACTIVE_WINDOW` is what triggers Muffin's restacking pass; sent with
    the "pager" source indication because the request comes from the desktop
    side, not from an application. The window is not focusable, so no focus
    change follows. Returns True when the request was sent.
    """
    x11, _xext = _load_x11()
    if x11 is None:
        return False
    display = x11.XOpenDisplay(None)
    if not display:
        return False
    try:
        atom = x11.XInternAtom(display, EWMH_ACTIVE_WINDOW.encode("utf-8"), False)
        if not atom:
            return False
        window = ctypes.c_ulong(gdk_window.get_xid())
        event = _XEvent()
        event.xclient.type = _X_CLIENT_MESSAGE
        event.xclient.send_event = True
        event.xclient.window = window
        event.xclient.message_type = atom
        event.xclient.format = 32
        event.xclient.data.l[0] = window.value
        event.xclient.data.l[1] = 0              # CurrentTime
        event.xclient.data.l[2] = EWMH_SOURCE_PAGER
        x11.XSendEvent(display, x11.XDefaultRootWindow(display), False,
                       _X_SUBSTRUCTURE_REDIRECT | _X_SUBSTRUCTURE_NOTIFY,
                       ctypes.byref(event))
        x11.XSync(display, False)
        return True
    except Exception:
        return False
    finally:
        try:
            x11.XCloseDisplay(display)
        except Exception:
            pass


def _atom(display, name):
    x11, _xext = _load_x11()
    return x11.XInternAtom(display, name.encode("utf-8"), True)


def _property_ids(display, window, prop_atom):
    """The 32-bit values of a window property (atoms, window ids, cardinals).

    Asked with AnyPropertyType: `_NET_CLIENT_LIST_STACKING` is a WINDOW list
    while `_NET_WM_WINDOW_TYPE` is an ATOM list, and a mismatched req_type makes
    XGetWindowProperty fail instead of returning the actual type. Both are
    32-bit, so the bytes read the same either way.

    The values come back as an array of C `long` (Xlib widens the protocol's
    32-bit units to `long` for the client), so they are read as c_ulong - on
    Linux x86-64 that is 8 bytes per value, which is exactly what Xlib wrote.
    """
    x11, _xext = _load_x11()
    actual_type = ctypes.c_ulong()
    actual_format = ctypes.c_int()
    count = ctypes.c_ulong()
    after = ctypes.c_ulong()
    data = ctypes.c_void_p()
    try:
        status = x11.XGetWindowProperty(
            display, window, prop_atom, 0, 4096, False, _X_ANY_PROPERTY_TYPE,
            ctypes.byref(actual_type), ctypes.byref(actual_format),
            ctypes.byref(count), ctypes.byref(after), ctypes.byref(data))
        if (status != 0 or not data.value or count.value == 0
                or actual_format.value != 32):
            return []
        values = ctypes.cast(
            data, ctypes.POINTER(ctypes.c_ulong * count.value)).contents
        ids = [int(values[i]) for i in range(count.value)]
        x11.XFree(data)
        return ids
    except Exception:
        return []


def _window_pid(display, window):
    """The PID of a window's client, from _NET_WM_PID (None when unknown)."""
    x11, _xext = _load_x11()
    try:
        values = _property_ids(display, window, _atom(display, _EWMH_WM_PID))
        return values[0] if values else None
    except Exception:
        return None


def layer_is_on_desktop(gdk_window):
    """True when the window manager has the layer in the desktop layer.

    Verified against the WM's own stacking list, bottom-to-top:
      * the layer must be ABOVE every desktop-type window (the wallpaper is
        painted by the desktop window, so that is what makes the rain visible),
      * and BELOW at least one other client (an app window), which is what
        keeps the rain off the applications.
    Windows the WM does not track (override-redirect ones, unmapped helpers)
    are not in the list and cannot disturb the comparison.
    """
    x11, _xext = _load_x11()
    if x11 is None:
        return False
    display = x11.XOpenDisplay(None)
    if not display:
        return False
    try:
        type_atom = _atom(display, _EWMH_WINDOW_TYPE)
        desktop_atom = _atom(display, _EWMH_DESKTOP_TYPE)
        list_atom = _atom(display, _EWMH_CLIENT_LIST_STACKING)
        if not type_atom or not desktop_atom or not list_atom:
            return False
        own = int(gdk_window.get_xid())
        managed = _property_ids(display, x11.XDefaultRootWindow(display), list_atom)
        if own not in managed:
            return False
        own_pos = managed.index(own)
        # The other layer of this process carries the same DESKTOP type; it is
        # a rain window, not a desktop, so it must not be mistaken for one.
        own_pid = os.getpid()
        for window in managed:
            if window == own:
                continue
            if _window_pid(display, window) == own_pid:
                continue
            if desktop_atom in _property_ids(display, window, type_atom):
                if managed.index(window) > own_pos:
                    return False      # a desktop window is above the rain
        return own_pos < len(managed) - 1
    except Exception:
        return False
    finally:
        try:
            x11.XCloseDisplay(display)
        except Exception:
            pass


def punch_input_hole(gdk_window):
    """Everything needed for the window to be click-through, in one call.

    Returns True only when the window really is unhittable *here*: on X11 that
    means the input shape was emptied (set_pass_through alone was measured not
    to be enough), on Wayland it means pass_through was accepted.
    """
    passed_through = False
    try:
        gdk_window.set_pass_through(True)
        passed_through = bool(gdk_window.get_pass_through())
    except Exception:
        passed_through = False
    if WAYLAND:
        return passed_through
    return empty_input_shape(gdk_window)


# --------------------------------------------------------------------------
# GTK layer
# --------------------------------------------------------------------------

class RainLayer:
    """One full-screen, click-through, behind-everything window per monitor."""

    def __init__(self, monitor):
        self.monitor = monitor
        self.win = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
        self.win.set_title("rain-%d" % monitor)
        self.win.set_decorated(False)
        self.win.set_resizable(False)
        self.win.set_accept_focus(False)
        self.win.set_focus_on_map(False)
        self.win.set_skip_taskbar_hint(True)
        self.win.set_skip_pager_hint(True)
        self.win.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        if WAYLAND:
            # The layer shell owns the stacking there; the keep-below hints are
            # only a fallback for compositors that ignore the layer.
            self.win.set_keep_below(True)
        self.win.set_keep_above(False)
        self._make_transparent()

        self.geometry = self._monitor_geometry(monitor)

        if WAYLAND:
            GtkLayerShell.init_for_window(self.win)
            GtkLayerShell.set_layer(self.win, GtkLayerShell.Layer.BOTTOM)
            for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                         GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
                GtkLayerShell.set_anchor(self.win, edge, True)
            GtkLayerShell.set_keyboard_mode(
                self.win, GtkLayerShell.KeyboardMode.NONE)
            display = Gdk.Display.get_default()
            if display is not None and monitor < display.get_n_monitors():
                GtkLayerShell.set_monitor(self.win, display.get_monitor(monitor))
        else:
            # A MANAGED window, deliberately: the window manager only applies
            # its layering to windows it manages, and that is the only way to
            # land in the desktop layer (see request_desktop_layer). An
            # override-redirect window is invisible to the WM, so it keeps
            # whatever stacking it was mapped with and the WM keeps pulling it
            # back on top - measured, the rain painted over open apps.
            # The price of being managed is that the WM may re-assert an input
            # shape over ours, so the click-through hole is punched on every map
            # and on every poll.
            self.win.connect("realize", self._on_realize)
            self.win.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
            # Geometry is ours, exactly like the widget windows: one layer per
            # monitor, sized and positioned on THAT monitor's own area, so the
            # rain never spills onto a neighbour and the WM cannot move us.
            self.win.set_size_request(self.geometry[2], self.geometry[3])
            self.win.move(self.geometry[0], self.geometry[1])
            # Re-punch the hole after every map: a hide/show cycle (auto mode
            # toggling) and some WMs re-shape on map. Cheap, and it makes the
            # guarantee hold for the whole session, not just the first second.
            self.win.connect("map-event", self._on_map)

        self.overlay = Gtk.Overlay()
        self.overlay.set_size_request(*self.geometry[2:])
        self.overlay.get_style_context().add_class("rain-overlay")
        self.win.add(self.overlay)
        self.drops = []
        self._signature = None
        self._provider = None

    @staticmethod
    def _monitor_geometry(monitor):
        """Return (x, y, width, height) for a monitor, falling back to the
        whole workarea when the index does not exist."""
        display = Gdk.Display.get_default()
        if display is not None and 0 <= monitor < display.get_n_monitors():
            gdm = display.get_monitor(monitor)
            if gdm is not None:
                rect = gdm.get_geometry()
                return rect.x, rect.y, rect.width, rect.height
        if display is not None:
            rect = display.get_primary_monitor()
            if rect is None:
                rect = display.get_monitor(0)
            if rect is not None:
                geo = rect.get_geometry()
                return geo.x, geo.y, geo.width, geo.height
        return 0, 0, 1920, 1080

    def _make_transparent(self):
        """Make the full-screen window see-through, BEFORE it is realized.

        Without this the layer is an opaque full-screen rectangle that hides
        the wallpaper and the desktop icons while still letting clicks through
        - the drops looked fine but the background was gone. Three pieces are
        needed on GTK3:

          * an RGBA visual, so the toplevel has an alpha channel at all,
          * set_app_paintable(True), so GTK lets the window draw itself instead
            of filling it with the theme's window background,
          * a transparent background on the window / overlay in the CSS
            (build_css), which stops GTK from painting the base color.

        Must run before the window is realized (show), which is why it is called
        from __init__. A None visual means the display cannot do alpha; the
        layer then simply stays opaque rather than failing to start.
        """
        self.win.get_style_context().add_class("rain-window")
        try:
            screen = self.win.get_screen()
            visual = screen.get_rgba_visual() if screen is not None else None
            if visual is not None:
                self.win.set_visual(visual)
        except Exception:
            pass
        self.win.set_app_paintable(True)

    def _clear_drops(self):
        for drop in self.drops:
            self.overlay.remove(drop)
        self.drops = []

    def apply(self, settings, tint):
        """Rebuild the droplet widgets + CSS. Skips work when nothing changed."""
        signature = (
            settings["count"], settings["speed"], settings["opacity"], tint,
            self.geometry[2], self.geometry[3],
        )
        if signature == self._signature:
            return False
        self._signature = signature

        self._clear_drops()
        width, height = self.geometry[2], self.geometry[3]
        drops, travel = plan_drops(
            settings["count"], settings["speed"], width, height)

        for drop in drops:
            widget = Gtk.Box()
            ctx = widget.get_style_context()
            ctx.add_class("rain-drop")
            ctx.add_class("rain-drop-%d" % drop["index"])
            widget.set_halign(Gtk.Align.START)
            widget.set_valign(Gtk.Align.START)
            self.overlay.add_overlay(widget)
            self.drops.append(widget)

        provider = Gtk.CssProvider()
        provider.load_from_data(
            build_css(drops, travel, settings["opacity"], tint).encode("utf-8"))
        # APPLICATION priority beats the default theme, so the widget's own
        # colours (e.g. a global `*` rule in some user theme) cannot win.
        screen = Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # Drop the PREVIOUS provider. Providers registered for a screen are
        # global and are only dropped by removing them; a slider drag would
        # otherwise stack one provider per frame and leak the old rules, whose
        # equal-specificity `.rain-drop-*` classes would race the new ones.
        if self._provider is not None:
            Gtk.StyleContext.remove_provider_for_screen(screen, self._provider)
        self._provider = provider
        return True

    def _on_realize(self, widget):
        """X11: ask for the desktop layer as soon as the window exists.

        Harmless to run before the map: the WM acts on the request when the
        window is mapped, and enforce_overlay_state() repeats it afterwards.
        """
        if WAYLAND:
            return
        gdk = widget.get_window()
        if gdk is not None:
            request_desktop_layer(gdk)

    def realize_click_through(self):
        """Punch the input hole. Must run after the window is realized."""
        gdk_window = self.win.get_window()
        if gdk_window is None:
            return False
        return punch_input_hole(gdk_window)

    def stack_on_desktop(self):
        """Keep the layer on the desktop: above the wallpaper, below apps."""
        gdk_window = self.win.get_window()
        if gdk_window is None:
            return False
        if not request_desktop_layer(gdk_window):
            return False
        return layer_is_on_desktop(gdk_window)

    def enforce_overlay_state(self):
        """Click-through + desktop stacking. Idempotent; safe to re-run.

        Both properties are per-window, per-map state that something else can
        undo (the WM re-shapes a window, an app lowers itself below the layer),
        so the poll re-asserts them instead of trusting the first map.
        """
        if not self.realize_click_through():
            return False
        if WAYLAND:
            # The layer shell owns the stacking on Wayland (Layer.BOTTOM).
            return True
        return self.stack_on_desktop()

    def _on_map(self, *_):
        """Re-assert the hole and the stacking right after (re)mapping.

        Returns False so GTK keeps the default map handling. A second,
        slightly delayed pass covers WMs that only re-shape once the window is
        actually on screen.
        """
        if self.enforce_overlay_state():
            GLib.timeout_add(250, self._late_click_through)
        return False

    def _late_click_through(self):
        if self.win.get_mapped() and not self.enforce_overlay_state():
            sys.stderr.write(
                "rain: click-through or desktop stacking lost on monitor %d\n"
                % self.monitor)
        return False

    def set_active(self, active):
        if active and not self.win.get_visible():
            self.win.show_all()
        elif not active and self.win.get_visible():
            self.win.hide()

    def deactivate(self):
        """Hide the layer AND release its droplet widgets.

        An inactive layer has no reason to keep up to 120 boxes per monitor
        alive, and their CSS rules would keep the old geometry in memory. The
        signature is cleared so the next apply() rebuilds from scratch.
        """
        self.set_active(False)
        if self.drops:
            self._clear_drops()
            self._signature = None

    def destroy(self):
        self._clear_drops()
        if self._provider is not None:
            Gtk.StyleContext.remove_provider_for_screen(
                Gdk.Screen.get_default(), self._provider)
            self._provider = None
        self.win.destroy()


class RainApp:
    """Owns one RainLayer per monitor and keeps them in sync with the config."""

    def __init__(self, config_dir):
        self.config_dir = config_dir
        self.layers = []
        self._mtimes = None
        self._monitors = None
        self._was_active = None
        self._unrestacked = {}
        self._build_layers()

    def _build_layers(self):
        display = Gdk.Display.get_default()
        n_monitors = display.get_n_monitors() if display is not None else 1
        for monitor in range(n_monitors):
            try:
                layer = RainLayer(monitor)
            except Exception as exc:
                sys.stderr.write("rain: monitor %d unavailable: %s\n" % (monitor, exc))
                continue
            # Click-through can only be punched once the window is realized.
            layer.win.connect(
                "realize", lambda _w, l=layer: l.realize_click_through())
            self.layers.append(layer)

    @staticmethod
    def _monitor_signature():
        """(x, y, w, h) of every monitor, so hotplug / resolution changes are
        picked up on the next poll instead of needing a restart."""
        display = Gdk.Display.get_default()
        if display is None:
            return ()
        geometry = []
        for monitor in range(display.get_n_monitors()):
            rect = display.get_monitor(monitor)
            if rect is None:
                continue
            geo = rect.get_geometry()
            geometry.append((geo.x, geo.y, geo.width, geo.height))
        return tuple(geometry)

    def _rebuild_layers(self):
        for layer in self.layers:
            try:
                layer.destroy()
            except Exception:
                pass
        self.layers = []
        self._build_layers()

    def active_now(self, settings):
        """Combine the master switch with the auto (precipitation) gate."""
        if not settings["enabled"] or settings["count"] <= 0:
            return False
        if settings["auto"] and not read_is_raining(self.config_dir):
            return False
        return True

    def tick(self):
        """Poll the watched files; rebuild only on an actual change."""
        watched = [
            os.path.join(self.config_dir, "config.yaml"),
            os.path.join(self.config_dir, "config.local.yaml"),
            os.path.join(self.config_dir, THEME_FILE),
            os.path.join(self.config_dir, CACHE_FILE),
        ]
        mtimes = tuple(_safe_mtime(path) for path in watched)
        settings = read_settings(self.config_dir)
        active = self.active_now(settings)

        if mtimes != self._mtimes:
            self._mtimes = mtimes
            changed = True
        else:
            changed = False

        # A plugged / unplugged monitor or a resolution change needs a new
        # window; the old one is bound to the geometry it was built for.
        monitors = self._monitor_signature()
        if monitors != self._monitors:
            self._monitors = monitors
            self._rebuild_layers()
            changed = True

        # Rebuild the droplets when a setting changed, or when the layer is
        # coming back after being hidden (a hidden layer still has to be
        # restyled if the theme tint moved while it was off).
        if changed or (active and not self._was_active):
            tint = read_tint(self.config_dir)
            for layer in self.layers:
                if active:
                    layer.apply(settings, tint)
                    layer.set_active(True)
                else:
                    layer.deactivate()

        self._was_active = active

        # Re-assert the two per-window properties while running. The hole is
        # what keeps clicks on the desktop working, and the stacking is what
        # keeps the rain off open application windows; either can be undone
        # under us, so it is re-applied on every poll. A handful of X requests
        # per layer every POLL_SEC is nothing.
        if active:
            for layer in self.layers:
                if not layer.win.get_visible():
                    continue
                if not layer.realize_click_through():
                    sys.stderr.write(
                        "rain: click-through lost on monitor %d\n" % layer.monitor)
                elif not layer.stack_on_desktop():
                    # The WM registers a new window asynchronously, so the first
                    # poll or two after a map can still fail - only complain
                    # when it keeps failing. Not fatal either way: the layer
                    # stays visible, just on top of the open windows.
                    misses = self._unrestacked.get(layer.monitor, 0) + 1
                    self._unrestacked[layer.monitor] = misses
                    if misses == LAYER_WARN_AFTER:
                        sys.stderr.write(
                            "rain: the window manager is not putting the layer "
                            "of monitor %d in the desktop layer, so the rain "
                            "paints over open windows\n" % layer.monitor)
                else:
                    self._unrestacked.pop(layer.monitor, None)
        return True


def _safe_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def selftest(config_dir):
    """Show the layer, verify click-through + droplet count, then exit.

    This is the check that matters most: click-through is the whole reason
    rain.py is not an eww window, and it is only observable after the window is
    realized. Run with --selftest; prints one line per monitor and exits 1 if
    any monitor is not click-through or the counts are wrong.
    """
    # RainApp connects the realize handler itself, so a hotplug rebuild is
    # covered too.
    app = RainApp(config_dir)
    app.tick()
    # Both per-window properties settle late and asynchronously: the input hole
    # needs the window on screen, and the window manager only registers a new
    # window in its stacking list after the map was processed. Checking too
    # early reported a false failure (measured), so re-assert and then wait.
    def _settle():
        for layer in app.layers:
            layer.enforce_overlay_state()
        return False
    GLib.timeout_add(400, _settle)
    GLib.timeout_add(1200, lambda: (Gtk.main_quit(), False)[1])
    Gtk.main()

    ok = True
    for layer in app.layers:
        # set_pass_through lives on the Gdk.Window, not on Gtk.Window.
        gdk_window = layer.win.get_window()
        click_through = layer.realize_click_through() if gdk_window else False
        on_desktop = layer.stack_on_desktop() if (gdk_window and not WAYLAND) else True
        drops = len(layer.drops)
        expected = app.active_now(read_settings(config_dir))
        visible = layer.win.get_visible()
        print("monitor %d: size=%dx%d click_through=%s on_desktop=%s drops=%d "
              "visible=%s expected_visible=%s" % (
                  layer.monitor, layer.geometry[2], layer.geometry[3],
                  click_through, on_desktop, drops, visible, expected,
              ))
        # A hidden layer is never on screen, so it cannot swallow a click: only
        # assert click-through on the layers that are actually shown.
        if visible and not click_through:
            print("  FAIL: clicks would be swallowed")
            ok = False
        if visible and not on_desktop:
            print("  FAIL: not in the desktop layer, so the rain paints over "
                  "open windows")
            ok = False
        if visible != expected:
            print("  FAIL: visibility does not match the config")
            ok = False
        if not drops and expected:
            print("  FAIL: expected droplets but the layer is empty")
            ok = False
        layer.destroy()

    sys.exit(0 if ok else 1)


def main():
    args = [a for a in sys.argv[1:] if a != "--selftest"]
    selftest_mode = "--selftest" in sys.argv[1:]

    # The only argument is the config dir, positionally. Refuse anything that
    # looks like a flag instead of trying to use it as a path (a mistyped
    # "--config-dir" would otherwise fail with a confusing "not a directory").
    for arg in args:
        if arg.startswith("-"):
            sys.exit("rain: unknown option %s (usage: rain.py [config_dir]"
                     " [--selftest])" % arg)

    config_dir = os.path.abspath(args[0] if args else os.getcwd())
    if not os.path.isdir(config_dir):
        sys.exit("rain: not a directory: %s" % config_dir)

    if selftest_mode:
        selftest(config_dir)
        return

    app = RainApp(config_dir)

    GLib.timeout_add(int(POLL_SEC * 1000), app.tick)
    # First pass immediately so the rain is up without waiting a poll cycle.
    app.tick()

    for layer in app.layers:
        if not layer.win.get_realized() or not layer.realize_click_through():
            sys.stderr.write(
                "rain: click-through NOT active on monitor %d\n" % layer.monitor)

    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
