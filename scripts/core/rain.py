#!/usr/bin/env python3
"""Full-screen raindrop layer: a click-through transparent window BEHIND the desktop.

v5.0.0. Why this is a standalone GTK3 process and not an eww window: eww 0.6.0
exposes no click-through / input-shape property, so a full-screen eww surface
would swallow every click on the desktop. Measured on this machine
(`strings $(which eww) | grep -i pass.through` -> nothing). This process owns
its own GtkWindow instead, where `Gdk.Window.set_pass_through` is available and
verified to return True (see `pass_through` assertion in `RainLayer`).

Stacking: layer-shell Layer.BOTTOM on Wayland (below every normal window, above
the wallpaper), override-redirect + keep_below on X11. Either way the layer is
unfocusable, undecorated and skipped in the taskbar.

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
DROPLET_W, DROPLET_H = 2, 16
# Fraction of drops rendered as a longer, faster streak.
STREAK_CHANCE = 0.3
# Per-drop duration jitter around the configured speed.
JITTER_MIN, JITTER_MAX = 0.7, 1.4
# speed 1 -> 2.4s, speed 10 -> 0.55s (linear).
DURATION_SLOW, DURATION_FAST = 2.4, 0.55
# Keep the fall slightly overshooting the bottom edge so drops vanish cleanly.
OVERSCAN = 60

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


def plan_drops(count, speed, width, height, seed=SEED):
    """Lay out `count` droplets for a width x height monitor.

    Returns a list of dicts with the per-drop geometry and timing, sorted by x
    so the generated CSS is stable between runs. `duration` is the CSS animation
    duration, `delay` a NEGATIVE value (seconds) that staggers the drops along
    the path - a positive delay would leave them all bunched at the start line.
    """
    count = clamp_count(count)
    width = max(1, int(width))
    height = max(1, int(height))
    travel = height + OVERSCAN
    duration = base_duration(speed)
    rng = random.Random(seed)

    drops = []
    for i in range(count):
        streak = rng.random() < STREAK_CHANCE
        drop_duration = duration * rng.uniform(JITTER_MIN, JITTER_MAX)
        # A streak is a fast, long drop; a regular drop a short, slower one.
        if streak:
            drop_duration *= 0.7
        drops.append({
            "index": i,
            "x": rng.randrange(0, max(1, width - DROPLET_W)),
            "duration": round(drop_duration, 3),
            "delay": round(-drop_duration * rng.random(), 3),
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
            # override-redirect so no WM tries to decorate or place us.
            self.win.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
            self.win.move(self.geometry[0], self.geometry[1])

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

    def realize_click_through(self):
        """Punch the input hole. Must run after the window is realized."""
        gdk_window = self.win.get_window()
        if gdk_window is None:
            return False
        gdk_window.set_pass_through(True)
        return bool(gdk_window.get_pass_through())

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
    app.tick()    # Realize (and therefore the pass-through flag) only settles once the
    # window is on screen, so give X/Wayland a few frames before checking.
    GLib.timeout_add(400, lambda: (Gtk.main_quit(), False)[1])
    Gtk.main()

    ok = True
    for layer in app.layers:
        # set_pass_through lives on the Gdk.Window, not on Gtk.Window.
        gdk_window = layer.win.get_window()
        click_through = bool(gdk_window.get_pass_through()) if gdk_window else False
        drops = len(layer.drops)
        expected = app.active_now(read_settings(config_dir))
        visible = layer.win.get_visible()
        print("monitor %d: size=%dx%d click_through=%s drops=%d visible=%s expected_visible=%s" % (
            layer.monitor, layer.geometry[2], layer.geometry[3], click_through,
            drops, visible, expected,
        ))
        # A hidden layer is never on screen, so it cannot swallow a click: only
        # assert click-through on the layers that are actually shown.
        if visible and not click_through:
            print("  FAIL: clicks would be swallowed")
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
