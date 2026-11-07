#!/usr/bin/env python3
"""Draggable raindrop-settings form (GTK3), v5.0.0.

Opened by scripts/move/rain_ctl.py in the MIDDLE of the screen (the monitor the
menu was raised on, same centering as the Weather settings form and the About
dialog). Edits the global `weather.rain.*` settings:

    enabled, auto -> config.local.yaml via config_set.py (bool)
    count          -> config.local.yaml (int, 0-120)
    speed          -> config.local.yaml (int, 1-10)
    opacity        -> config.local.yaml (float, 0.0-1.0)

DRAFT-ONLY, like the Weather form: the controls are edited in memory and only
**Save** writes them, and it writes just the keys that actually changed, through
config_set.py. That is deliberate: every write to config.local.yaml re-triggers
watch.py (theme regeneration + `eww reload`), so a live-applying slider would
fire dozens of full widget reloads per drag. One write on Save is enough -
scripts/core/rain.py polls the config every 2 seconds, so the new values reach
the rain layer right after the panel closes. While the draft is unsaved the
status line shows a neutral "Save to apply"; an invalid value refuses the whole
save with a red inline error and the panel stays open. Reset drops the local
overrides so the config.yaml defaults win again; Cancel / Close discards.

The window is a small GTK3 toplevel with a draggable title strip, using the
same mechanics as weather_panel.py / gap_panel.py / about_win.py:

  * X11     - override-redirect toplevel, dragged with GtkWindow.move.
  * Wayland - layer-shell OVERLAY surface (GtkLayerShell), dragged by updating
              the left/top margins.

Closing works four ways, exactly like the other panels:

  * click outside -> hits the eww dismiss_overlay (opened per monitor by
                     ctx.py and left mapped by rain_ctl.py), which runs
                     close_popup.py and clears the session file,
  * ESC            -> the evdev daemon in mode "rain" runs close_popup.py,
  * Cancel button  -> runs close_popup.py directly,
  * Save/Reset     -> runs close_popup.py after committing.

This window polls generated/input_session.json and quits once the "rain"
session disappears.

Usage:
  ./rain_panel.py --monitor 0 --x 300 --y 200 --frame-w 1920 --frame-h 1080 \
                  --win-h 330
"""

import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CR_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/
# scripts/move/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
THEME_FILE = os.path.join(CONFIG_DIR, "eww", "eww.theme.json")
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

try:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk, GLib
except Exception as exc:
    sys.exit("rain_panel: GTK3 unavailable: %s" % exc)

WAYLAND = "WAYLAND_DISPLAY" in os.environ and os.environ.get("GDK_BACKEND", "wayland") != "x11"

if WAYLAND:
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except Exception as exc:
        sys.exit("rain_panel: GtkLayerShell unavailable: %s" % exc)

PANEL_W = 320
# Measured content height (title 30 + hint + 4 control rows + 2 seps + the
# always-allocated status line + action row + Cancel). Must match POSE_H in
# rain_ctl.py, which centers the window with it.
PANEL_H = 343
TITLE_H = 30

# The rain controls, in the order they stack. (label, config_set key, lo, hi,
# step) - count and speed are integers, opacity is a 0.0-1.0 float, and the
# two switches are plain booleans rendered as a button pair.
COUNT_MIN, COUNT_MAX = 0, 120
SPEED_MIN, SPEED_MAX = 1, 10

# Fallbacks mirror the weather.rain block in config.yaml, so an old config
# without the block still opens the panel on sane numbers.
DEFAULTS = {
    "rain_enabled": "true",
    "rain_auto": "true",
    "rain_count": "24",
    "rain_speed": "5",
    "rain_opacity": "0.35",
}


def theme_values():
    try:
        with open(THEME_FILE) as fh:
            data = json.load(fh)
        bg = data.get("bg_color", "#000000")
        light = data.get("color_light", "#ffffff")
        alpha = float(data.get("color_light_alpha", 1.0) or 1.0)
        radius = int(data.get("bg_radius", 15) or 0)
        font = data.get("font_face", "Noto Sans")
        return bg, light, alpha, radius, font
    except Exception:
        return "#000000", "#ffffff", 1.0, 15, "Noto Sans"


def run(cmd):
    try:
        subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True, cwd=CONFIG_DIR,
        )
    except Exception:
        pass


def close_popup():
    run([sys.executable, os.path.join(CR_DIR, "widgets", "close_popup.py")])


def session_active():
    try:
        with open(SESSION_FILE) as fh:
            return json.load(fh).get("mode") == "rain"
    except Exception:
        return False


def load_settings():
    """Effective rain.* values, as the strings config_set.py would take.

    Read straight from the merged config (config_io) rather than by shelling
    out, so opening the panel costs nothing. The enabled/auto pairs are
    normalized to the "true"/"false" text the writer uses.
    """
    from config_io import load_merged

    try:
        config = load_merged(CONFIG_DIR) or {}
    except Exception:
        config = {}
    rain = (config.get("weather") or {}).get("rain") or {}
    if not isinstance(rain, dict):
        rain = {}

    def flag(name):
        value = rain.get(name, DEFAULTS["rain_%s" % name])
        if isinstance(value, bool):
            return "true" if value else "false"
        return "false" if str(value).strip().lower() == "false" else "true"

    return {
        "rain_enabled": flag("enabled"),
        "rain_auto": flag("auto"),
        "rain_count": str(rain.get("count", DEFAULTS["rain_count"])),
        "rain_speed": str(rain.get("speed", DEFAULTS["rain_speed"])),
        "rain_opacity": str(rain.get("opacity", DEFAULTS["rain_opacity"])),
    }


def validate(key, raw):
    """(ok, message) for a control value; mirrors config_set.py's ranges."""
    text = "" if raw is None else str(raw).strip()
    if key == "rain_enabled" or key == "rain_auto":
        if text.lower() in ("true", "false"):
            return True, ""
        return False, "%s must be true or false" % key
    if key == "rain_count":
        try:
            value = int(text)
        except ValueError:
            return False, "Count must be a whole number"
        if not COUNT_MIN <= value <= COUNT_MAX:
            return False, "Count must be %d-%d" % (COUNT_MIN, COUNT_MAX)
        return True, ""
    if key == "rain_speed":
        try:
            value = int(text)
        except ValueError:
            return False, "Speed must be a whole number"
        if not SPEED_MIN <= value <= SPEED_MAX:
            return False, "Speed must be %d-%d" % (SPEED_MIN, SPEED_MAX)
        return True, ""
    if key == "rain_opacity":
        try:
            value = float(text)
        except ValueError:
            return False, "Opacity must be a number"
        if not 0.0 <= value <= 1.0:
            return False, "Opacity must be 0.0-1.0"
        return True, ""
    # An unknown key must never be written: config_set.py would exit and the
    # failure would only surface as a generic "Failed to write".
    return False, "Unsupported setting: %s" % key


def reset_rain_overrides():
    """Drop every weather.rain.* key from config.local.yaml (the Reset button).

    Mirrors weather_panel.reset_weather_overrides: rewrite the local file
    without the rain subtree so the config.yaml defaults take effect again.
    """
    import yaml

    path = os.path.join(CONFIG_DIR, "config.local.yaml")
    try:
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return True
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    weather = data.get("weather")
    if isinstance(weather, dict) and "rain" in weather:
        weather.pop("rain")
        if not weather:
            data.pop("weather", None)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
    except Exception:
        return False
    return True


def _as_text(value):
    """Comparable form of a config value: "24", "0.35", "true".

    config_set.py always writes trimmed text, but a hand-edited
    config.local.yaml can hold YAML bools / ints / floats, and a control must
    not look "changed" just because of the YAML type.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        text = ("%f" % value).rstrip("0").rstrip(".")
        return text or "0"
    return str(value).strip()


def build_css(bg, light, alpha, radius, font):
    def rgba(c, a):
        return "rgba(%d, %d, %d, %s)" % (
            int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), a,
        )

    return """
    * {
      font-family: "%s";
      outline: none;
    }
    .panel {
      background-color: %s;
      border: 1px solid %s;
      border-radius: %dpx;
      padding: 10px;
    }
    .title {
      font-size: 12px;
      font-weight: bold;
      color: %s;
      padding: 4px 4px 8px 4px;
    }
    .row {
      margin: 2px 0;
    }
    .field-label {
      font-size: 12px;
      font-weight: bold;
      color: %s;
    }
    .hint {
      font-size: 10px;
      color: %s;
      margin: 0 0 4px 0;
    }
    spinbutton {
      font-size: 13px;
      color: %s;
      background-color: %s;
      border-radius: 8px;
      padding: 2px 6px;
    }
    scale {
      min-height: 22px;
    }
    scale trough {
      min-height: 6px;
      background-color: %s;
      border-radius: 3px;
    }
    scale slider {
      min-width: 14px;
      min-height: 14px;
      border-radius: 7px;
      background-color: %s;
    }
    scale value {
      font-size: 11px;
      color: %s;
    }
    .sep {
      min-height: 1px;
      margin: 6px 2px;
      background-color: %s;
    }
    button {
      min-height: 28px;
      margin: 2px;
      border: none;
      border-radius: 8px;
      background-color: %s;
      color: %s;
      font-size: 14px;
      font-weight: normal;
      padding: 0;
    }
    button:hover { background-color: %s; }
    button:active { background-color: %s; }
    button.toggle-btn { min-width: 56px; }
    button.toggle-btn.on { background-color: %s; }
    .status {
      font-size: 11px;
      color: %s;
      margin: 2px;
    }
    /* "Save to apply" - the calm colour, not the red error colour. */
    .status.hint { color: %s; }
    button.close { background-color: rgba(204, 0, 0, 0.25); }
    button.close:hover { background-color: rgba(204, 0, 0, 0.4); }
    button.save { background-color: rgba(78, 154, 6, 0.25); }
    button.save:hover { background-color: rgba(78, 154, 6, 0.4); }
    """ % (
        font,                    # font-family
        rgba(bg, 0.97),          # .panel background
        rgba(light, 0.28),       # .panel border
        radius,                  # .panel border-radius
        rgba(light, alpha),      # .title color
        rgba(light, alpha),      # .field-label color
        rgba(light, 0.6),        # .hint color
        rgba(light, alpha),      # spinbutton color
        rgba(bg, 0.55),          # spinbutton background
        rgba(light, 0.16),       # scale trough
        rgba(light, alpha),      # scale slider
        rgba(light, alpha),      # scale value
        rgba(light, 0.16),       # .sep
        rgba(light, 0.16),       # button background
        rgba(light, alpha),      # button color
        rgba(light, 0.16),       # button:hover
        rgba(light, 0.28),       # button:active
        rgba(light, 0.28),       # button.toggle-btn.on
        "rgba(255, 100, 100, 0.9)",  # .status error color
        rgba(light, 0.6),        # .status.hint "Save to apply"
    )


class RainPanel:
    def __init__(self, monitor, x, y, frame_w, frame_h, win_h=PANEL_H):
        self.monitor = monitor
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.win_w = PANEL_W
        self.win_h = max(0, int(win_h or PANEL_H))
        self.win_x = x
        self.win_y = y
        self.drag = False
        self.grab_root_x = 0.0
        self.grab_root_y = 0.0
        self.grab_x = 0.0
        self.grab_y = 0.0
        self.start_x = x
        self.start_y = y
        self.committed = load_settings()
        self.toggle_btns = {}   # (key, "true"/"false") -> Gtk.Button
        self.spins = {}         # key -> Gtk.SpinButton
        self.scales = {}        # key -> Gtk.Scale
        self.status_label = None
        # Set while apply() writes the config, so the value-change handlers do
        # not fire a second (redundant) write while the widget is being set.
        self.syncing = False

        self.mon_ox, self.mon_oy = 0, 0
        try:
            display = Gdk.Display.get_default()
            if display is not None and monitor < display.get_n_monitors():
                geo = display.get_monitor(monitor).get_geometry()
                self.mon_ox, self.mon_oy = geo.x, geo.y
        except Exception:
            pass

        self.desk_x0, self.desk_y0, self.desk_w, self.desk_h = (
            self.mon_ox, self.mon_oy, frame_w, frame_h)
        try:
            display = Gdk.Display.get_default()
            if display is not None:
                x0 = y0 = None
                x1 = y1 = 0
                for i in range(display.get_n_monitors()):
                    g = display.get_monitor(i).get_geometry()
                    x1 = max(x1, g.x + g.width)
                    y1 = max(y1, g.y + g.height)
                    x0 = g.x if x0 is None else min(x0, g.x)
                    y0 = g.y if y0 is None else min(y0, g.y)
                if x0 is not None:
                    self.desk_x0, self.desk_y0 = x0, y0
                    self.desk_w, self.desk_h = x1 - x0, y1 - y0
        except Exception:
            pass

        bg, light, alpha, radius, font = theme_values()
        self.win = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
        self.win.set_title("")
        self.win.set_decorated(False)
        self.win.set_skip_taskbar_hint(True)
        self.win.set_skip_pager_hint(True)
        self.win.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.win.set_keep_above(True)
        self.win.set_resizable(False)
        self.win.set_accept_focus(True)
        self.win.set_size_request(self.win_w, self.win_h)
        self.win.set_default_size(self.win_w, self.win_h)
        geometry = Gdk.Geometry()
        geometry.min_width = geometry.max_width = self.win_w
        geometry.min_height = geometry.max_height = self.win_h
        self.win.set_geometry_hints(
            None, geometry,
            Gdk.WindowHints.MIN_SIZE | Gdk.WindowHints.MAX_SIZE,
        )

        if WAYLAND:
            try:
                GtkLayerShell.init_for_window(self.win)
                GtkLayerShell.set_layer(self.win, GtkLayerShell.Layer.OVERLAY)
                GtkLayerShell.set_anchor(self.win, GtkLayerShell.Edge.TOP, True)
                GtkLayerShell.set_anchor(self.win, GtkLayerShell.Edge.LEFT, True)
                GtkLayerShell.set_keyboard_mode(
                    self.win, GtkLayerShell.KeyboardMode.ON_DEMAND)
                display = Gdk.Display.get_default()
                if display is not None and monitor < display.get_n_monitors():
                    GtkLayerShell.set_monitor(self.win, display.get_monitor(monitor))
                GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.LEFT, x)
                GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.TOP, y)
            except Exception:
                pass
        else:
            self.win.move(x, y)

        self.build_ui(bg, light, alpha, radius, font)
        # Fill the controls from the config. Without this every widget would
        # open at its adjustment's minimum (0 droplets, speed 1, opacity 0)
        # and Save would immediately write those minimums over the user's
        # settings. sync_from_config() also updates the .on classes, and
        # self.syncing keeps the value-changed handlers from marking the panel
        # dirty on the way in.
        self.sync_from_config()
        self.win.connect("destroy", lambda *_: Gtk.main_quit())
        self.win.connect("realize", self.on_realize)

    def on_realize(self, widget):
        if not WAYLAND:
            try:
                widget.get_window().set_override_redirect(True)
            except Exception:
                pass

    def raise_above(self):
        if not WAYLAND:
            try:
                window = self.win.get_window()
                if window is not None:
                    window.raise_()
            except Exception:
                pass

    # ---- UI -----------------------------------------------------------------
    def build_ui(self, bg, light, alpha, radius, font):
        css = build_css(bg, light, alpha, radius, font)
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        root = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        root.get_style_context().add_class("panel")

        title = Gtk.EventBox.new()
        title.get_style_context().add_class("title")
        box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        label = Gtk.Label.new("Raindrops")
        label.set_halign(Gtk.Align.CENTER)
        box.pack_start(label, True, True, 0)
        title.add(box)
        title.set_events(Gdk.EventMask.BUTTON_PRESS_MASK
                         | Gdk.EventMask.BUTTON_RELEASE_MASK
                         | Gdk.EventMask.POINTER_MOTION_MASK)
        title.connect("realize", lambda w: self._grab_cursor(w))
        self.win.connect("button-press-event", self.on_press)
        self.win.connect("button-release-event", self.on_release)
        self.win.connect("motion-notify-event", self.on_motion)
        root.pack_start(title, False, False, 0)

        hint = Gtk.Label.new(
            "Behind the desktop windows. Save applies the changes.")
        hint.get_style_context().add_class("hint")
        hint.set_halign(Gtk.Align.CENTER)
        root.pack_start(hint, False, False, 0)

        root.pack_start(self.toggle_row("Enabled", "rain_enabled"), False, False, 0)
        root.pack_start(self.toggle_row("Auto (only when raining)", "rain_auto"),
                        False, False, 0)
        root.pack_start(self.sep(), False, False, 0)
        root.pack_start(self.spin_row("Droplets", "rain_count",
                                      COUNT_MIN, COUNT_MAX, 1, 0), False, False, 0)
        root.pack_start(self.scale_row("Speed", "rain_speed",
                                       SPEED_MIN, SPEED_MAX, 1, 0), False, False, 0)
        # digits=2 so a 0.05 step round-trips: with 1 digit the scale would
        # display 0.35 as "0.3" and Save would write 0.3.
        root.pack_start(self.scale_row("Opacity", "rain_opacity", 0.0, 1.0, 0.05, 2),
                        False, False, 0)

        root.pack_start(self.sep(), False, False, 0)

        self.status_label = Gtk.Label.new("")
        self.status_label.set_visible(False)
        self.status_label.set_halign(Gtk.Align.CENTER)
        self.status_label.get_style_context().add_class("status")
        root.pack_start(self.status_label, False, False, 0)

        action_row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        reset = Gtk.Button.new_with_label("Reset")
        reset.connect("clicked", lambda *_: self.on_reset())
        action_row.pack_start(reset, True, True, 0)
        save = Gtk.Button.new_with_label("Save")
        save.get_style_context().add_class("save")
        save.connect("clicked", lambda *_: self.on_save())
        action_row.pack_start(save, True, True, 0)
        root.pack_start(action_row, False, False, 0)

        close = Gtk.Button.new_with_label("Cancel")
        close.get_style_context().add_class("close")
        close.connect("clicked", lambda *_: self.on_close())
        root.pack_start(close, False, False, 0)

        self.win.add(root)

    def toggle_row(self, label, key):
        """A true/false button pair (weather_panel.units_row pattern).

        Plain buttons, NOT Gtk.ToggleButton: a toggle fights programmatic
        set_active, so the active value is marked with an ".on" class instead.
        """
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        row.get_style_context().add_class("row")
        lab = Gtk.Label.new(label)
        lab.get_style_context().add_class("field-label")
        lab.set_xalign(0.0)
        cbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        for value in ("true", "false"):
            btn = Gtk.Button.new_with_label("On" if value == "true" else "Off")
            btn.get_style_context().add_class("toggle-btn")
            btn.connect("clicked", lambda w, k=key, v=value: self.on_toggle(k, v))
            cbox.pack_start(btn, True, True, 0)
            self.toggle_btns[(key, value)] = btn
        row.pack_start(lab, False, False, 0)
        row.pack_start(cbox, True, True, 0)
        self._update_toggle_buttons()
        return row

    def spin_row(self, label, key, lo, hi, step, digits):
        """Label + Gtk.SpinButton. Only Save commits the value."""
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        row.get_style_context().add_class("row")
        lab = Gtk.Label.new(label)
        lab.get_style_context().add_class("field-label")
        lab.set_size_request(96, -1)
        lab.set_xalign(0.0)
        adj = Gtk.Adjustment.new(lo, lo, hi, step, step * 10, 0)
        spin = Gtk.SpinButton.new(adj, 1, digits)
        spin.set_numeric(True)
        spin.connect("value-changed", lambda w, k=key: self.on_value(k, w))
        row.pack_start(lab, False, False, 0)
        row.pack_start(spin, True, True, 0)
        self.spins[key] = spin
        return row

    def scale_row(self, label, key, lo, hi, step, digits):
        """Label + Gtk.Scale for the float opacity control (theme_panel pattern)."""
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        row.get_style_context().add_class("row")
        lab = Gtk.Label.new(label)
        lab.get_style_context().add_class("field-label")
        lab.set_size_request(96, -1)
        lab.set_xalign(0.0)
        adj = Gtk.Adjustment.new(lo, lo, hi, step, step * 5, 0)
        scale = Gtk.Scale.new(Gtk.Orientation.HORIZONTAL, adj)
        scale.set_draw_value(True)
        scale.set_digits(digits)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.connect("value-changed", lambda w, k=key: self.on_value(k, w))
        row.pack_start(lab, False, False, 0)
        row.pack_start(scale, True, True, 0)
        self.scales[key] = scale
        return row

    def sep(self):
        s = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        s.get_style_context().add_class("sep")
        return s

    # ---- live apply ---------------------------------------------------------
    def _current(self, key):
        """The value a control currently shows, as config_set.py wants it."""
        if key in self.spins:
            return str(int(self.spins[key].get_value()))
        if key in self.scales:
            scale = self.scales[key]
            text = ("%.*f" % (scale.get_digits(), scale.get_value()))
            return text.rstrip("0").rstrip(".") or "0"
        for (k, value), btn in self.toggle_btns.items():
            if k == key and "on" in btn.get_style_context().list_classes():
                return value
        return self.committed.get(key, DEFAULTS.get(key, ""))

    def apply(self, key, value):
        """Validate and write ONE key; show the error inline when it fails.

        Only on_save() calls this. Writing config.local.yaml re-triggers
        watch.py (theme regen + `eww reload`), so committing on every slider
        tick would fire dozens of reloads per drag - and a reload rebuilds the
        widget on top of the rain layer. Save writes once; rain.py then picks
        the new values up within its 2 s poll, so the effect still updates
        right after the panel closes.
        """
        ok, msg = validate(key, value)
        if not ok:
            self.show_error(msg)
            return False
        if not self.config_set(key, value):
            self.show_error("Failed to write %s" % key)
            return False
        self.committed[key] = value
        return True

    def on_toggle(self, key, value):
        if self.syncing:
            return
        self._update_toggle_buttons(key, value)
        self._mark_dirty()

    def on_value(self, key, widget):
        if self.syncing:
            return
        self._mark_dirty()

    def dirty_keys(self):
        """The keys whose control differs from the last written value.

        Both sides are normalized first: the controls always yield trimmed
        TEXT, while a hand-edited config.local.yaml can hold real YAML
        bools / ints / floats. Without this an untouched panel would look
        dirty for every key and Save would rewrite the whole rain block.
        """
        return [
            key for key in ("rain_enabled", "rain_auto", "rain_count",
                            "rain_speed", "rain_opacity")
            if _as_text(self._current(key)) != _as_text(self.committed.get(key))
        ]

    def _mark_dirty(self):
        if self.status_label is None:
            return
        if self.dirty_keys():
            self.status_label.set_text("Save to apply")
            self.status_label.get_style_context().add_class("hint")
            self.status_label.set_visible(True)
        else:
            self.status_label.get_style_context().remove_class("hint")

    def config_set(self, key, value):
        cmd = [
            sys.executable,
            os.path.join(CONFIG_DIR, "scripts", "core", "config_set.py"),
            "--key", key, "--value", str(value),
        ]
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15, cwd=CONFIG_DIR,
            )
            return res.returncode == 0
        except Exception:
            return False

    def _update_toggle_buttons(self, key=None, active=None):
        """Mark the active button of each pair with the ".on" class."""
        for (k, value), btn in self.toggle_btns.items():
            if key is not None and k != key:
                continue
            want = active if key is not None else self.committed.get(k)
            ctx = btn.get_style_context()
            if value == want:
                ctx.add_class("on")
            else:
                ctx.remove_class("on")

    def sync_from_config(self):
        """Fill every control from the committed (config) values.

        Called once at construction - otherwise a fresh panel would open at the
        adjustment minimums - and again after Reset. `self.syncing` keeps the
        value-changed handlers from marking the untouched panel dirty.
        """
        self.syncing = True
        try:
            values = load_settings()
            self.committed = dict(values)
            for key, spin in self.spins.items():
                try:
                    spin.set_value(float(values.get(key, 0)))
                except (TypeError, ValueError):
                    pass
            for key, scale in self.scales.items():
                try:
                    scale.set_value(float(values.get(key, 0)))
                except (TypeError, ValueError):
                    pass
            self._update_toggle_buttons()
        finally:
            self.syncing = False

    def show_error(self, msg):
        if self.status_label is None:
            return
        # An error always wins over the "Save to apply" hint (red > grey).
        self.status_label.get_style_context().remove_class("hint")
        self.status_label.set_text(msg if len(msg) <= 56 else msg[:53] + "...")
        self.status_label.set_visible(True)

    def on_save(self):
        """Validate EVERY control and commit only the changed keys, then close.

        This is the only action that writes the config, so the config watcher
        and the rain layer both see exactly ONE change per save. An invalid
        value refuses the whole save with an inline error and the panel stays
        open so nothing is lost.
        """
        for key in ("rain_enabled", "rain_auto", "rain_count", "rain_speed",
                    "rain_opacity"):
            value = self._current(key)
            ok, msg = validate(key, value)
            if not ok:
                self.show_error(msg)
                return False

        for key in self.dirty_keys():
            if not self.apply(key, self._current(key)):
                return False

        close_popup()
        Gtk.main_quit()
        return True

    def on_close(self, *_):
        """Cancel: leave the config untouched, like the weather panel."""
        close_popup()
        Gtk.main_quit()

    def on_reset(self, *_):
        """Drop the local rain overrides and refill from the defaults."""
        if not reset_rain_overrides():
            self.show_error("Failed to reset raindrops")
            return False
        self.sync_from_config()
        close_popup()
        Gtk.main_quit()
        return True

    @staticmethod
    def _grab_cursor(widget):
        try:
            window = widget.get_window()
            if window is not None:
                window.set_cursor(Gdk.Cursor.new_from_name(
                    Gdk.Display.get_default(), "grab"))
        except Exception:
            pass

    def tick(self):
        if not session_active():
            Gtk.main_quit()
            return False
        self.raise_above()
        return True

    # -- dragging (same mechanics as weather_panel.py / gap_panel.py) ---------
    def on_press(self, widget, event):
        if event.button != 1 or event.y > TITLE_H:
            return False
        self.drag = True
        self.grab_root_x = event.x_root
        self.grab_root_y = event.y_root
        self.grab_x = event.x
        self.grab_y = event.y
        self.start_x = self.win_x
        self.start_y = self.win_y
        if not WAYLAND:
            try:
                if self.win.get_window() is not None:
                    Gdk.pointer_grab(
                        self.win.get_window(), False,
                        Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK,
                        None, None, Gdk.CURRENT_TIME,
                    )
            except Exception:
                pass
        return False

    def on_motion(self, widget, event):
        if not self.drag:
            return False
        if WAYLAND:
            dx = event.x - self.grab_x
            dy = event.y - self.grab_y
            nx = max(0, min(self.win_x + dx, max(0, self.frame_w - self.win_w)))
            ny = max(0, min(self.win_y + dy, max(0, self.frame_h - self.win_h)))
        else:
            nx = self.start_x + int(event.x_root - self.grab_root_x)
            ny = self.start_y + int(event.y_root - self.grab_root_y)
        self._move_to(nx, ny)
        return False

    def on_release(self, widget, event):
        if not self.drag:
            return False
        self.drag = False
        if not WAYLAND:
            try:
                Gdk.pointer_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass
        return False

    def _move_to(self, nx, ny):
        nx = max(self.desk_x0, min(nx, self.desk_x0 + self.desk_w - self.win_w))
        ny = max(self.desk_y0, min(ny, self.desk_y0 + self.desk_h - self.win_h))
        self.win_x, self.win_y = nx, ny
        if WAYLAND:
            try:
                GtkLayerShell.set_margin(
                    self.win, GtkLayerShell.Edge.LEFT,
                    max(0, nx - self.mon_ox))
                GtkLayerShell.set_margin(
                    self.win, GtkLayerShell.Edge.TOP,
                    max(0, ny - self.mon_oy))
            except Exception:
                pass
        else:
            try:
                self.win.move(nx, ny)
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--monitor", type=int, default=0)
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--frame-w", type=int, default=0)
    ap.add_argument("--frame-h", type=int, default=0)
    ap.add_argument("--win-h", type=int, default=PANEL_H)
    args = ap.parse_args()

    if not session_active():
        sys.exit(0)

    panel = RainPanel(args.monitor, args.x, args.y,
                      args.frame_w, args.frame_h, args.win_h)
    panel.win.show_all()
    panel.win.present()
    GLib.timeout_add(250, panel.tick)
    Gtk.main()


if __name__ == "__main__":
    main()
