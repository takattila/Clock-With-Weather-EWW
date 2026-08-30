#!/usr/bin/env python3
"""Draggable weather-settings form (GTK3).

Opened by scripts/weather_ctl.py CENTERED ON the monitor the menu was opened
on (same centering as the About dialog, in contrast to the Move/Resize and
Panel-gap panels). Edits the global `weather:` settings:

    city|language_code|lang -> config.local.yaml  (via config_set.py)
    units (metric/imperial) -> config.local.yaml   (weather.units)
    api_url                 -> config.local.yaml   (weather.api_url)
    api_key                 -> the git-ignored .api_key file (mode 0600);
                              empty means "leave the current key alone",
                              and an OPENWEATHER_API_KEY env var still wins
                              over the file (config.py resolution order).

Editing is DRAFT-ONLY: typing only changes the fields in this window, nothing
is written. Only the Save button commits: it validates EVERY field, writes
the changed ones in ONE go through config_set.py (+ the .api_key file), then
immediately refreshes the on-screen weather (weather.py with the NEW values +
`eww update weather_info=...`) so the change does NOT wait for the 10-minute
defpoll, and finally closes. The Reset button is the mirror image of Save: it
removes the LOCAL weather overrides (config.local.yaml) so the config.yaml /
weather-theme values take effect again, refills the form with them, refreshes
and closes. Cancel discards everything and closes.

The window is a small GTK3 toplevel with a draggable title strip, using the
same mechanics as scripts/move_panel.py / gap_panel.py / about_win.py:

  * X11     - override-redirect toplevel, dragged with GtkWindow.move
              (absolute screen coordinates).
  * Wayland - layer-shell OVERLAY surface (GtkLayerShell), dragged by updating
              the left/top margins.

The editable fields are handled exactly like gap_panel.py's value fields:
while one owns the keyboard the file generated/input_session.json is marked
"typing": true so the evdev daemon (scripts/input_daemon.py, mode "weather")
ignores every OTHER key - ESC specifically stays live and closes the session
even mid-typing; on X11 the override-redirect toplevel never gains the X
focus, so the entry takes a GDK KEYBOARD GRAB on click and all keystrokes are
routed into this window.

Closing works four ways, exactly like the other panels:

  * click outside -> hits the eww dismiss_overlay (kept open by weather_ctl.py),
                     which runs close_popup.py and clears the session file,
  * ESC            -> the evdev daemon in mode "weather" runs close_popup.py,
  * Cancel button  -> runs close_popup.py directly,
  * Save/Reset     -> runs close_popup.py after committing.

This window polls generated/input_session.json and quits once the "weather"
session disappears (ESC / click-outside / Cancel / Save / Reset).

The window HEIGHT adapts to the desktop: the controller (weather_ctl.py) sizes
it to fit the smallest connected screen's usable height (screen minus
taskbar), so it can be dragged onto any monitor. On X11 the drag is clamped to
the WHOLE virtual desktop (union of all monitors), letting the window be moved
from one monitor to another.

Usage:
  ./weather_panel.py --monitor 0 --x 300 --y 200 --frame-w 1920 --frame-h 1080 \
                     --win-h 380
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
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
THEME_FILE = os.path.join(CONFIG_DIR, "eww", "eww.theme.json")
API_KEY_FILE = os.path.join(CONFIG_DIR, ".api_key")
API_KEY_ENV = "OPENWEATHER_API_KEY"
DEFAULT_API_URL = "https://api.openweathermap.org/data/2.5/weather"
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

try:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk, GLib
except Exception as exc:
    sys.exit("weather_panel: GTK3 unavailable: %s" % exc)

WAYLAND = "WAYLAND_DISPLAY" in os.environ and os.environ.get("GDK_BACKEND", "wayland") != "x11"

if WAYLAND:
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except Exception as exc:
        sys.exit("weather_panel: GtkLayerShell unavailable: %s" % exc)

PANEL_W = 300
PANEL_H = 380
TITLE_H = 30

# label / config key pairs; "units" and "api_key" have their own controls.
FIELD_ROWS = (
    ("City", "city"),
    ("Language code", "language_code"),
    ("Language", "lang"),
    ("API URL", "api_url"),
    ("API key", "api_key"),
)


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
            return json.load(fh).get("mode") == "weather"
    except Exception:
        return False


def load_weather():
    """Effective weather settings exactly as the widget sees them."""
    try:
        import config as config_mod
        cfg = config_mod.load_config()
        return {
            "city": str(cfg.get("city") or ""),
            "language_code": str(cfg.get("language_code") or ""),
            "lang": str(cfg.get("lang") or ""),
            "units": str(cfg.get("units") or "metric"),
            "api_url": str(cfg.get("api_url") or DEFAULT_API_URL),
            "api_key": str(cfg.get("api_key") or ""),
        }
    except Exception:
        return dict.fromkeys(
            ("city", "language_code", "lang", "units", "api_url", "api_key"),
            "",
        )


def validate(key, value):
    """Return (ok, error_msg) for one weather setting (pure/testable)."""
    value = (value or "").strip()
    if key == "units":
        if value not in ("metric", "imperial"):
            return False, "units must be metric or imperial"
        return True, None
    if key == "api_url":
        if not value.startswith(("http://", "https://")):
            return False, "api_url must start with http:// or https://"
        return True, None
    if key in ("city", "language_code", "lang"):
        if not value:
            return False, "%s must not be empty" % key
        return True, None
    if key == "api_key":
        # Empty is allowed: it means "leave the current key untouched".
        return True, None
    return False, "unknown field: %s" % key


def current_api_key(path=API_KEY_FILE):
    """The .api_key file content ('' when missing) - what the env overrides."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def write_api_key(key, path=API_KEY_FILE):
    """Write the key to the git-ignored .api_key file (mode 0600)."""
    try:
        with open(path, "w", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), 0o600)
            fh.write(key.strip() + "\n")
        return True
    except Exception:
        return False


def reset_weather_overrides(config_dir=CONFIG_DIR):
    """Remove the LOCAL weather overrides so the config.yaml defaults win.

    Drops only the five editable leaves from config.local.yaml (city,
    language_code, lang, units, api_url); the `weather.window` subtree
    (per-monitor placement etc.) is left alone and the .api_key file is NEVER
    touched. A missing local file is a no-op success; a missing/empty weather
    subtree likewise. Pure + testable via the config_dir parameter.
    """
    try:
        import config_io

        path = config_io.local_path(config_dir)
        if not os.path.isfile(path):
            return True
        data = config_io.load_file(config_dir, config_io.LOCAL_CONFIG_FILE)
        weather = data.get("weather") if isinstance(data, dict) else None
        if isinstance(weather, dict):
            for key in ("city", "language_code", "lang", "units", "api_url"):
                weather.pop(key, None)
            if not weather:
                data.pop("weather", None)
        config_io.save_local(config_dir, data)
        return True
    except Exception:
        return False


def set_position(win, x, y):
    if WAYLAND:
        try:
            GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, x)
            GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, y)
        except Exception:
            pass
    else:
        win.move(x, y)


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
    entry.value-entry {
      font-size: 14px;
      color: %s;
      background-color: %s;
      border-radius: 8px;
      padding: 2px 6px;
    }
    entry.value-entry:focus { background-color: %s; }
    .sep {
      min-height: 1px;
      margin: 8px 2px;
      background-color: %s;
    }
    button {
      min-height: 30px;
      margin: 2px;
      border: none;
      border-radius: 8px;
      background-color: %s;
      color: %s;
      font-size: 15px;
      font-weight: normal;
      padding: 0;
    }
    button:hover { background-color: %s; }
    button:active { background-color: %s; }
    button.unit-btn { min-width: 52px; }
    button.unit-btn.on { background-color: %s; }
    .status {
      font-size: 11px;
      color: %s;
      margin: 2px;
    }
    button.close { background-color: rgba(204, 0, 0, 0.25); }
    button.close:hover { background-color: rgba(204, 0, 0, 0.4); }
    button.save { background-color: rgba(78, 154, 6, 0.25); }
    button.save:hover { background-color: rgba(78, 154, 6, 0.4); }
    """ % (
        font,
        rgba(bg, 0.97),
        rgba(light, 0.15),
        radius,
        rgba(light, 0.6 * alpha),
        rgba(light, alpha),        # field label
        rgba(light, alpha),        # entry color
        rgba(light, 0.08),         # entry background
        rgba(light, 0.16),         # entry:focus
        rgba(light, 0.1),          # separator
        rgba(light, 0.08),         # button background
        rgba(light, alpha),        # button color
        rgba(light, 0.16),         # button:hover
        rgba(light, 0.28),         # button:active
        rgba(light, 0.28),         # unit-btn:checked
        "rgba(255, 100, 100, 0.9)",  # .status error color
    )


class WeatherPanel:
    def __init__(self, monitor, x, y, frame_w, frame_h, win_h=PANEL_H):
        self.monitor = monitor
        self.frame_w = frame_w
        self.frame_h = frame_h
        # Resolved window size: the controller adapts win_h so the window also
        # fits the smallest connected screen (screen height minus taskbar).
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
        self.committed = load_weather()
        self.draft = dict(self.committed)  # working values (Save applies)
        self.entries = {}       # config key -> Gtk.Entry
        self.unit_btns = {}     # "metric"/"imperial" -> Gtk.Button (active = .on class)
        self.editing = None     # config key whose entry owns the keyboard
        self.status_label = None

        # Absolute screen origin of the target monitor: on X11 the drag clamps
        # the panel to this rectangle (win.move uses absolute coordinates).
        self.mon_ox = 0
        self.mon_oy = 0
        try:
            display = Gdk.Display.get_default()
            if display is not None and monitor < display.get_n_monitors():
                geo = display.get_monitor(monitor).get_geometry()
                self.mon_ox, self.mon_oy = geo.x, geo.y
        except Exception:
            pass

        # Bounding box of the WHOLE virtual desktop, so the window can be
        # dragged from one monitor to another instead of being pinned to the
        # monitor it opened on (X11; absolute coordinate space).
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
        # The launcher (weather_ctl.py) CENTERS this window on the monitor
        # using the resolved size: the size request + hard geometry hints
        # (min == max) pin it deterministically, so the centering is
        # pixel-exact even if a field's natural request wants more room.
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
                GtkLayerShell.set_keyboard_mode(self.win, GtkLayerShell.KeyboardMode.ON_DEMAND)
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
        self.win.connect("destroy", lambda *_: (self._release_keyboard(), Gtk.main_quit()))
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
        label = Gtk.Label.new("Weather settings")
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

        # The field section is wrapped in a ScrolledWindow so the window can
        # be shrunk below its natural height (smallest-screen adaptation in
        # __init__) without clipping the footer: when there is room the rows
        # stretch to absorb the leftover vertical space (no dead gap above
        # the separator) and when the window is short they scroll instead.
        scrolled = Gtk.ScrolledWindow.new(None, None)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.NONE)
        fields = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        fields.get_style_context().add_class("fields")

        # The rows stretch to absorb the leftover vertical space (the window
        # is a fixed win_h tall, see __init__), so the buttons sit directly
        # under the separator with NO dead gap between the fields and them.
        for field_label, key in FIELD_ROWS:
            fields.pack_start(self.field_row(field_label, key), True, True, 0)
        fields.pack_start(self.units_row(), True, True, 0)

        scrolled.add(fields)
        root.pack_start(scrolled, True, True, 0)

        root.pack_start(self.sep(), False, False, 0)

        # Inline error surface for an invalid/refused Save (move_panel.py /
        # gap_panel.py pattern): hidden until a field fails to validate/write.
        self.status_label = Gtk.Label.new("")
        self.status_label.set_visible(False)
        self.status_label.set_halign(Gtk.Align.CENTER)
        self.status_label.get_style_context().add_class("status")
        root.pack_start(self.status_label, False, False, 0)

        action_row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        reset = Gtk.Button.new_with_label("Reset")
        reset.get_style_context().add_class("reset")
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

    def field_row(self, field_label, key):
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        row.get_style_context().add_class("row")
        lab = Gtk.Label.new(field_label)
        lab.get_style_context().add_class("field-label")
        lab.set_size_request(96, -1)
        lab.set_xalign(0.0)
        field = Gtk.Entry.new()
        field.get_style_context().add_class("value-entry")
        field.set_alignment(0.0)
        # 20 chars keeps the row minimum (label 96 + entry) under PANEL_W, so
        # the exact-size window never has to grow; longer URLs scroll.
        field.set_width_chars(20 if key == "api_url" else 12)
        # NO set_max_width_chars: GTK3 derives the entry's NATURAL width from
        # max_width_chars (not width_chars), so 64 would balloon the natural
        # size to ~526 px and force the window far beyond the designed
        # PANEL_W - the exact-size window would then be impossible to center.
        # width_chars alone keeps the natural request at the visible field.
        field.connect("button-press-event", lambda w, e, k=key: self.on_entry_press(w, e, k))
        field.connect("focus-in-event", lambda w, e, k=key: self.on_entry_focus_in(w, e, k))
        field.connect("focus-out-event", lambda w, e, k=key: self.on_entry_focus_out(w, e, k))
        field.connect("activate", lambda w, k=key: self.on_entry_activate(w, k))
        row.pack_start(lab, False, False, 0)
        row.pack_start(field, True, True, 0)
        self.entries[key] = field
        self.render(key)
        return row

    def units_row(self):
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        row.get_style_context().add_class("row")
        lab = Gtk.Label.new("Units")
        lab.get_style_context().add_class("field-label")
        lab.set_size_request(96, -1)
        lab.set_xalign(0.0)
        cbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        for units, glyph in (("metric", "°C"), ("imperial", "°F")):
            # Plain buttons, NOT Gtk.ToggleButton: a toggle's own active-state
            # flip fights any programmatic set_active done in its clicked
            # handler, which made the pair impossible to switch back. The
            # active one is marked with an explicit ".on" style class instead.
            btn = Gtk.Button.new_with_label(glyph)
            btn.get_style_context().add_class("unit-btn")
            btn.connect("clicked", lambda w, u=units: self.on_unit(u))
            cbox.pack_start(btn, True, True, 0)
            self.unit_btns[units] = btn
        row.pack_start(lab, False, False, 0)
        row.pack_start(cbox, True, True, 0)
        self._update_unit_buttons()
        return row

    def sep(self):
        s = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        s.get_style_context().add_class("sep")
        return s

    def render(self, key):
        value = self.draft.get(key, "")
        entry = self.entries.get(key)
        if entry is not None and self.editing != key:
            entry.set_text(value)

    # ---- config writes (only ever called from Save) -------------------------
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

    def refresh_weather(self, city, lang, units, api_url, api_key):
        """Re-fetch with the NEW settings and push weather_info into eww now.

        Best-effort: the config watcher already reloads the widget and the
        10-minute defpoll would pick the values up anyway; a failure here only
        warns on stderr.
        """
        try:
            payload = subprocess.check_output(
                [
                    sys.executable,
                    os.path.join(CONFIG_DIR, "scripts", "core", "weather.py"),
                    api_key, city, lang, units, api_url,
                ],
                stderr=subprocess.DEVNULL, text=True, timeout=20, cwd=CONFIG_DIR,
            )
            lines = payload.strip().splitlines()
            run([
                "eww", "--config", EWW_CONFIG_DIR,
                "update", "weather_info=%s" % lines[-1],
            ])
        except Exception as exc:
            print("WARN: instant weather refresh failed (%s); the widget picks "
                  "the new settings up at the next poll" % exc, file=sys.stderr)

    # ---- editable value fields (gap_panel.py pattern) -----------------------
    def set_typing(self, flag):
        """(Re)write the session file with/without the "typing" marker.

        While an entry owns the keyboard the evdev daemon must ignore every
        non-ESC key; ESC always closes the session, even mid-typing.
        """
        try:
            with open(SESSION_FILE) as fh:
                data = json.load(fh)
            if data.get("mode") != "weather":
                return
            if flag:
                data["typing"] = True
            else:
                data.pop("typing", None)
            with open(SESSION_FILE, "w") as fh:
                json.dump(data, fh)
        except Exception:
            pass

    def _begin_editing(self, key):
        self.editing = key
        self.set_typing(True)

    def _end_editing(self, key):
        if self.editing != key:
            return
        self.editing = None
        self.set_typing(False)
        if not WAYLAND:
            try:
                Gdk.keyboard_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass
        # Keep the typed text as-is: clicking away from a field (e.g. onto
        # Save) must NOT discard the entry, or Save could never apply a
        # hand-typed value - the field stays the source of truth until the
        # Save button parses it.

    def _release_keyboard(self, *_):
        self.editing = None
        if not WAYLAND:
            try:
                Gdk.keyboard_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass

    def on_entry_press(self, entry, event, key):
        self._begin_editing(key)
        if not WAYLAND:
            try:
                Gdk.keyboard_grab(self.win.get_window(), True, Gdk.CURRENT_TIME)
            except Exception:
                pass
        # Select the whole current value AFTER GTK's own press handling ran
        # (otherwise it clears our selection and typed digits would land
        # inside the old number). idle = post-default-handler.
        GLib.idle_add(entry.select_region, 0, -1)
        return False

    def on_entry_focus_in(self, entry, event, key):
        self._begin_editing(key)
        return False

    def on_entry_focus_out(self, entry, event, key):
        self._end_editing(key)
        return False

    def on_entry_activate(self, entry, key):
        """Enter on a single field: validate + store into the DRAFT only.

        Records the (stripped, normalized) value - the Save button applies
        every field in one go.
        """
        ok, msg = validate(key, entry.get_text())
        if not ok:
            self.show_error(msg)
            entry.select_region(0, -1)
            return False
        value = (entry.get_text() or "").strip()
        entry.set_text(value)
        if key == "api_key" and not value:
            return False
        self.draft[key] = value
        return False

    def on_unit(self, units):
        """Unit-pair click: update the DRAFT units + the active button style."""
        self.draft["units"] = units
        self._update_unit_buttons()

    def _update_unit_buttons(self):
        active = self.draft.get("units")
        for units, btn in self.unit_btns.items():
            ctx = btn.get_style_context()
            if units == active:
                ctx.add_class("on")
            else:
                ctx.remove_class("on")

    def show_error(self, msg):
        if self.status_label is None:
            return
        self.status_label.set_text(msg if len(msg) <= 56 else msg[:53] + "...")
        self.status_label.set_visible(True)

    def on_save(self):
        """Validate EVERY field and commit the changed ones, then close.

        This is the ONLY action that writes the config (config_set.py for
        city/language_code/lang/units/api_url + the .api_key file), so the
        config watcher and the weather refresh kick in exactly once instead
        of on every keystroke. Invalid input refuses the whole save with an
        inline error; empty api_key leaves the current key untouched. On
        success the weather is refreshed instantly (no 10-minute defpoll
        wait), the session is cleared and this window closes.
        """
        self._end_editing(self.editing)

        new_draft = dict(self.draft)
        new_draft.update(units=self.draft.get("units", "metric"))
        for key in ("city", "language_code", "lang", "api_url", "api_key"):
            entry = self.entries.get(key)
            if entry is None:
                continue
            ok, msg = validate(key, entry.get_text())
            if not ok:
                self.show_error(msg)
                return False
            new_draft[key] = (entry.get_text() or "").strip()

        for key in ("city", "language_code", "lang", "units", "api_url"):
            if new_draft.get(key, "") != self.committed.get(key, ""):
                if not self.config_set(key, new_draft[key]):
                    self.show_error("Failed to write %s" % key)
                    return False

        # api_key lives in the .api_key file (not yaml): write it only when a
        # non-empty new value differs from the current file content.
        new_key = new_draft.get("api_key", "").strip()
        if new_key and new_key != current_api_key():
            if not write_api_key(new_key):
                self.show_error("Failed to write api_key")
                return False

        self.refresh_weather(
            new_draft["city"], new_draft["lang"], new_draft["units"],
            new_draft["api_url"], new_key or self.committed.get("api_key", ""),
        )
        self.draft = new_draft
        self.committed = dict(self.draft)
        close_popup()
        Gtk.main_quit()
        return True

    def on_close(self, *_):
        close_popup()
        Gtk.main_quit()

    def on_reset(self, *_):
        """Remove the LOCAL weather overrides and reapply the defaults.

        Mirror image of on_save(): drops the five editable weather.* leaves
        from config.local.yaml so the config.yaml / weather-theme values win
        again, refills the form with those effective values, refreshes the
        on-screen weather instantly and closes. The .api_key file (a secret,
        not part of config.yaml) is never touched.
        """
        self._end_editing(self.editing)

        if not reset_weather_overrides():
            self.show_error("Failed to reset weather")
            return False

        values = load_weather()
        self.draft = dict(values)
        self.committed = dict(values)
        for key in ("city", "language_code", "lang", "api_url", "api_key"):
            entry = self.entries.get(key)
            if entry is not None:
                entry.set_text(values.get(key, ""))
        self._update_unit_buttons()

        self.refresh_weather(
            values["city"], values["lang"], values["units"],
            values["api_url"], values.get("api_key") or current_api_key(),
        )
        close_popup()
        Gtk.main_quit()
        return True

    @staticmethod
    def _grab_cursor(widget):
        try:
            window = widget.get_window()
            if window is not None:
                window.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "grab"))
        except Exception:
            pass

    def tick(self):
        if not session_active():
            Gtk.main_quit()
            return False
        self.raise_above()
        return True

    # -- dragging (same mechanics as gap_panel.py / move_panel.py) ------------
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
            # Clamp to the WHOLE virtual desktop so the window can be dragged
            # from one monitor to another (win_w/win_h = resolved size).
            nx = max(self.desk_x0, min(nx, self.desk_x0
                                       + max(0, self.desk_w - self.win_w)))
            ny = max(self.desk_y0, min(ny, self.desk_y0
                                       + max(0, self.desk_h - self.win_h)))
        if nx != self.win_x or ny != self.win_y:
            self.win_x, self.win_y = nx, ny
            set_position(self.win, nx, ny)
        return False

    def on_release(self, widget, event):
        if event.button != 1:
            return False
        self.drag = False
        if not WAYLAND:
            try:
                Gdk.pointer_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass
        return False


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

    panel = WeatherPanel(args.monitor, args.x, args.y,
                         args.frame_w, args.frame_h, args.win_h)
    panel.win.show_all()
    panel.win.present()
    GLib.timeout_add(250, panel.tick)
    Gtk.main()


if __name__ == "__main__":
    main()