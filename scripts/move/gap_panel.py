#!/usr/bin/env python3
"""Draggable panel-gap control panel (GTK3).

Opened by scripts/gap_ctl.py NEXT TO the system-monitor panel, at the same
10 px distance the Move/Resize panel keeps from it (both launchers use
panel_pos.py with gap = 10). Shows the four sides of the global `panel.gap`
(top / right / bottom / left -- the spacing between the system-monitor panel
and the screen/taskbar edges). Each row is a minus / VALUE / plus triplet
like the Move/Resize "%" rows; the center field is an EDITABLE entry - click
it and type a value with the keyboard (Enter validates just that one).

Edits are DRAFT-ONLY: -/+ stepping and typing only change the numbers in this
window, nothing is written and the system panel does NOT relayout. Only the
Save button commits: it validates EVERY row, clamps to [GAP_MIN, GAP_MAX],
writes the changed sides through scripts/config_set.py in ONE go - so the
config watcher relays out the panel exactly once - and then closes.

The window is a small GTK3 toplevel with a draggable title strip, using the
same mechanics as scripts/move_panel.py / about_win.py:

  * X11     - override-redirect toplevel, dragged with GtkWindow.move
              (absolute screen coordinates).
  * Wayland - layer-shell OVERLAY surface (GtkLayerShell), dragged by updating
              the left/top margins.

The editable fields are handled exactly like move_panel.py's percentage
fields: while one owns the keyboard the file generated/input_session.json is
marked "typing": true so the evdev daemon (scripts/input_daemon.py) ignores
every key (ESC would otherwise close the session while typing); on X11 the
override-redirect toplevel never gains the X focus, so the entry takes a GDK
KEYBOARD GRAB on click and all keystrokes are routed into this window.

Closing works three ways, exactly like the About window:

  * click outside -> hits the eww dismiss_overlay (kept open by gap_ctl.py),
                     which runs close_popup.py and clears the session file,
  * ESC            -> the evdev daemon (scripts/input_daemon.py, mode "gap")
                     runs close_popup.py, also clearing the session file,
  * Cancel button  -> runs close_popup.py directly.

This window polls generated/input_session.json and quits once the "gap"
session disappears (ESC / click-outside / Close / Save).

Usage:
  ./gap_panel.py --monitor 0 --x 300 --y 200 --frame-w 1920 --frame-h 1080
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
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

try:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk, GLib
except Exception as exc:
    sys.exit("gap_panel: GTK3 unavailable: %s" % exc)

WAYLAND = "WAYLAND_DISPLAY" in os.environ and os.environ.get("GDK_BACKEND", "wayland") != "x11"

if WAYLAND:
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except Exception as exc:
        sys.exit("gap_panel: GtkLayerShell unavailable: %s" % exc)

PANEL_W = 200
PANEL_H = 320
TITLE_H = 30
GAP_STEP = 4
GAP_MIN = 0
GAP_MAX = 120
SIDES = ("left", "right", "top", "bottom")


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
            return json.load(fh).get("mode") == "gap"
    except Exception:
        return False


def load_gaps():
    """Per-side panel gaps from the MERGED config (defaults: 16 px)."""
    try:
        import workarea

        return workarea.load_gaps(CONFIG_DIR)
    except Exception:
        return dict.fromkeys(SIDES, 16)


def clamp(value, lo, hi):
    return max(lo, min(value, hi))


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
    .axis-label {
      font-size: 12px;
      font-weight: bold;
      color: %s;
    }
    .gap-value {
      font-size: 13px;
      color: %s;
      min-width: 40px;
    }
    entry.value-entry {
      font-size: 14px;
      min-width: 44px;
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
      min-width: 36px;
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
        rgba(light, alpha),
        rgba(light, alpha),
        rgba(light, alpha),        # entry color
        rgba(light, 0.08),         # entry background
        rgba(light, 0.16),         # entry:focus
        rgba(light, 0.1),          # separator
        rgba(light, 0.08),         # button background
        rgba(light, alpha),        # button color
        rgba(light, 0.16),         # button:hover
        rgba(light, 0.28),         # button:active
        "rgba(255, 100, 100, 0.9)",  # .status error color
    )


class GapPanel:
    def __init__(self, monitor, x, y, frame_w, frame_h):
        self.monitor = monitor
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.win_x = x
        self.win_y = y
        self.drag = False
        self.grab_root_x = 0.0
        self.grab_root_y = 0.0
        self.grab_x = 0.0
        self.grab_y = 0.0
        self.start_x = x
        self.start_y = y
        self.gap = load_gaps()
        self.draft = dict(self.gap)  # committed + working values (Save applies)
        self.value_entries = {}
        self.editing = None      # side whose value entry owns the keyboard
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
        # The launcher (gap_ctl.py) places this window 10 px from the system
        # panel assuming it is EXACTLY PANEL_W x PANEL_H. The content below is
        # sized to fit inside that box (label 48 + 2x button 36 + value 40 +
        # padding 20 = 180 < PANEL_W), so the real window size equals the
        # positioned size and the control panel never bites INTO the system
        # panel; the size request pins it deterministically.
        self.win.set_size_request(PANEL_W, PANEL_H)
        self.win.set_default_size(PANEL_W, PANEL_H)

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
        # On X11 the eww popups are override-redirect, which always floats above
        # managed windows - so this window must be override-redirect too to stay
        # on top of the dismiss_overlay and be draggable.
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
        label = Gtk.Label.new("Panel gap")
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

        # The four gap rows stretch to absorb the leftover vertical space (the
        # window is a fixed 320 px tall, see __init__), so the Cancel button
        # sits directly under the separator with NO dead gap between the
        # controls and itself; the extra space becomes a taller row each
        # instead of one hole above the button.
        for side in SIDES:
            root.pack_start(self.gap_row(side), True, True, 0)

        root.pack_start(self.sep(), False, False, 0)

        # Inline error surface for an invalid/refused Save (move_panel.py
        # pattern): hidden until a typed value fails to validate or write.
        self.status_label = Gtk.Label.new("")
        self.status_label.set_visible(False)
        self.status_label.set_halign(Gtk.Align.CENTER)
        self.status_label.get_style_context().add_class("status")
        root.pack_start(self.status_label, False, False, 0)

        save = Gtk.Button.new_with_label("Save")
        save.get_style_context().add_class("save")
        save.connect("clicked", lambda *_: self.on_save())
        root.pack_start(save, False, False, 0)

        close = Gtk.Button.new_with_label("Cancel")
        close.get_style_context().add_class("close")
        close.connect("clicked", lambda *_: self.on_close())
        root.pack_start(close, False, False, 0)

        self.win.add(root)

    def gap_row(self, side):
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        row.get_style_context().add_class("row")
        lab = Gtk.Label.new(side.capitalize())
        lab.get_style_context().add_class("axis-label")
        lab.set_size_request(48, -1)
        lab.set_xalign(0.0)
        minus = Gtk.Button.new_with_label("−")
        minus.connect("clicked", lambda *_: self.adjust(side, -GAP_STEP))
        field = Gtk.Entry.new()
        field.get_style_context().add_class("value-entry")
        field.set_alignment(0.5)
        field.set_width_chars(3)
        field.set_max_width_chars(4)
        field.connect("button-press-event", lambda w, e, s=side: self.on_entry_press(w, e, s))
        field.connect("focus-in-event", lambda w, e, s=side: self.on_entry_focus_in(w, e, s))
        field.connect("focus-out-event", lambda w, e, s=side: self.on_entry_focus_out(w, e, s))
        field.connect("activate", lambda w, s=side: self.on_entry_activate(w, s))
        plus = Gtk.Button.new_with_label("+")
        plus.connect("clicked", lambda *_: self.adjust(side, +GAP_STEP))
        row.pack_start(lab, False, False, 0)
        row.pack_start(minus, True, True, 0)
        row.pack_start(field, False, False, 0)
        row.pack_start(plus, True, True, 0)
        self.value_entries[side] = field
        self.render(side)
        return row

    def sep(self):
        s = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        s.get_style_context().add_class("sep")
        return s

    def render(self, side):
        value = int(round(self.draft.get(side, 16)))
        entry = self.value_entries.get(side)
        if entry is not None and self.editing != side:
            entry.set_text(str(value))

    def write_gap(self, side, value):
        """Persist one side via config_set.py (only ever called on Save)."""
        cmd = [
            sys.executable,
            os.path.join(CONFIG_DIR, "scripts", "core", "config_set.py"),
            "--widget", "panel", "--key", "gap_%s" % side, "--value", str(value),
        ]
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15, cwd=CONFIG_DIR,
            )
            return res.returncode == 0
        except Exception:
            return False

    def adjust(self, side, delta):
        # DRAFT only: steps the value shown in the field (the hand-typed text
        # wins when it parses, else the last committed/stored value). NO
        # config write, so the system panel does NOT relayout on every click -
        # everything is committed in one go by the Save button (see on_save).
        entry = self.value_entries.get(side)
        base = int(round(self.draft.get(side, 16)))
        if entry is not None:
            typed, ok = self.parse_entry(entry)
            if ok:
                base = typed
        new = clamp(base + delta, GAP_MIN, GAP_MAX)
        if new == base:
            return
        self.draft[side] = new
        if entry is not None and self.editing != side:
            entry.set_text(str(new))

    # ---- editable value fields (move_panel.py PctField pattern) -------------
    def set_typing(self, flag):
        """(Re)write the session file with/without the "typing" marker.

        While a value entry owns the keyboard the evdev daemon must ignore
        every key (ESC would otherwise close the session and Enter would
        arrive as a stray press); it skips all handling while set, including
        ESC - click outside the entry first, then ESC closes.
        """
        try:
            with open(SESSION_FILE) as fh:
                data = json.load(fh)
            if data.get("mode") != "gap":
                return
            if flag:
                data["typing"] = True
            else:
                data.pop("typing", None)
            with open(SESSION_FILE, "w") as fh:
                json.dump(data, fh)
        except Exception:
            pass

    def _begin_editing(self, side):
        self.editing = side
        self.set_typing(True)

    def _end_editing(self, side):
        if self.editing != side:
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

    def on_entry_press(self, entry, event, side):
        self._begin_editing(side)
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

    def on_entry_focus_in(self, entry, event, side):
        self._begin_editing(side)
        return False

    def on_entry_focus_out(self, entry, event, side):
        self._end_editing(side)
        return False

    def on_entry_activate(self, entry, side):
        """Enter on a single row: validate + clamp into the DRAFT only.

        Refreshes the field text and records the value in self.draft, but does
        NOT touch the config (and so does not relayout the system panel) - the
        Save button commits every row in one go.
        """
        value, ok = self.parse_entry(entry)
        if not ok:
            entry.select_region(0, -1)
            return False
        value = clamp(value, GAP_MIN, GAP_MAX)
        self.draft[side] = value
        entry.set_text(str(value))
        return False

    @staticmethod
    def parse_entry(entry):
        raw = entry.get_text().strip().rstrip(",").strip()
        try:
            return int(raw), True
        except ValueError:
            return 0, False

    def on_save(self):
        """Validate EVERY row and commit the changed ones, then close.

        This is the ONLY action that writes the config (via config_set.py,
        synchronously so a write failure stays visible instead of silently
        vanishing): +/- and typing only moved the draft values, so the system
        panel relayouts exactly once - here - instead of on every click.
        Invalid input refuses the whole save with an inline error; valid
        values are clamped to [GAP_MIN, GAP_MAX] and only the sides that
        actually changed are persisted. On success the session is cleared and
        this window closes.
        """
        self._end_editing(self.editing)
        new_draft = {}
        for side in SIDES:
            entry = self.value_entries.get(side)
            if entry is None:
                continue
            value, ok = self.parse_entry(entry)
            if not ok:
                self.show_error("Invalid value for %s" % side.capitalize())
                return False
            new_draft[side] = clamp(value, GAP_MIN, GAP_MAX)
        for side, value in new_draft.items():
            if value != int(round(self.gap.get(side, 16))):
                if not self.write_gap(side, value):
                    self.show_error("Failed to write %s" % side.capitalize())
                    return False
        self.draft.update(new_draft)
        self.gap.update(new_draft)
        close_popup()
        Gtk.main_quit()
        return True

    def show_error(self, msg):
        if self.status_label is None:
            return
        self.status_label.set_text(msg if len(msg) <= 56 else msg[:53] + "...")
        self.status_label.set_visible(True)

    def on_close(self, *_):
        close_popup()
        Gtk.main_quit()

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

    # -- dragging (same mechanics as move_panel.py / about_win.py) ------------
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
            nx = max(0, min(self.win_x + dx, max(0, self.frame_w - PANEL_W)))
            ny = max(0, min(self.win_y + dy, max(0, self.frame_h - PANEL_H)))
        else:
            nx = self.start_x + int(event.x_root - self.grab_root_x)
            ny = self.start_y + int(event.y_root - self.grab_root_y)
            nx = max(self.mon_ox, min(nx, self.mon_ox + max(0, self.frame_w - PANEL_W)))
            ny = max(self.mon_oy, min(ny, self.mon_oy + max(0, self.frame_h - PANEL_H)))
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
    args = ap.parse_args()

    if not session_active():
        sys.exit(0)

    panel = GapPanel(args.monitor, args.x, args.y, args.frame_w, args.frame_h)
    panel.win.show_all()
    panel.win.present()
    GLib.timeout_add(250, panel.tick)
    Gtk.main()


if __name__ == "__main__":
    main()