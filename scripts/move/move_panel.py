#!/usr/bin/env python3
"""Draggable Move / Resize control panel.

The old move_controls window was an eww window, so eww 0.5.0 could never move
it (window geometry is fixed at open time) and the keyboard daemon handled the
arrow/+/-/ENTER/ESC keys. This panel is a small GTK3 window instead, which makes
mouse-dragging possible on both compositors:

  * X11        - the window is an override-redirect toplevel, so it stacks
                 ABOVE the (also override-redirect) full-screen eww move
                 overlay; otherwise that surface would swallow every click and
                 the panel could never be dragged. Dragging moves the window
                 directly (GtkWindow.move, absolute screen coordinates).
  * Wayland    - a plain toplevel cannot position itself, so the window is a
                 layer-shell surface (GtkLayerShell, already a system
                 dependency via eww): anchored top-left on the monitor and
                 positioned with set_margin().

Dragging the title bar moves the panel live (on Wayland the grab point stays
under the pointer via margin updates; on X11 via gtk_window_move); releasing
keeps it there. On X11 the drag delta comes from root coordinates, on Wayland
from window-relative coordinates (the GDK layer-shell root coords are "fake"
there). The buttons run scripts/move_ctl.py exactly like the old eww buttons
did (arrows move the overlay rectangle, +/- zoom, Reset returns to the
defaults, Save writes config.yaml and closes, Cancel discards). The Resize
section has THREE rows of − / % / +:

  * row 1 (no label)   -> PROPORTIONAL zoom (zoom_in/out + set_scale): both
                          axes scale together, aspect ratio preserved;
  * row 2 ("W")        -> WIDTH ONLY (zoom_in/out_x + set_scale_x);
  * row 3 ("H")        -> HEIGHT ONLY (zoom_in/out_y + set_scale_y).

Every percentage between −/+ is an EDITABLE entry: each field polls its eww
variable (the main and W rows read move_pct = width %, the H row reads
move_pct_h = height %; both are set by move_ctl.py together with
move_w/move_h) for display, and typed values are applied on Enter /
focus-out via move_ctl.py --action set_scale / set_scale_x / set_scale_y
(30..150%). While an entry owns the keyboard, the panel marks the session
file with "typing": true so the evdev daemon ignores every key (Enter would
otherwise save, -/+ would zoom); the shared plumbing lives in PctField.

Keyboard control (arrows, +/-/Shift+3, Shift+arrows = single-axis resize,
ENTER=save, ESC=cancel) is deliberately left to the invisible evdev daemon
(scripts/input_daemon.py) so no key is handled twice; this panel only watches
generated/input_session.json and quits whenever move_ctl.py clears it
(Save / Cancel / overlay click).

Usage:
  ./move_panel.py --widget clock --monitor 0 --x 100 --y 200 --frame-w 1920 --frame-h 1080
"""

import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
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
    sys.exit("move_panel: GTK3 unavailable: %s" % exc)

WAYLAND = "WAYLAND_DISPLAY" in os.environ and os.environ.get("GDK_BACKEND", "wayland") != "x11"

if WAYLAND:
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except Exception as exc:
        sys.exit("move_panel: GtkLayerShell unavailable: %s" % exc)

MC_W = 200
MC_H = 320
TITLE_H = 30


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


def eww(*args):
    run(["eww", "--config", EWW_CONFIG_DIR] + list(args))


def eww_get(name):
    try:
        out = subprocess.check_output(
            ["eww", "--config", EWW_CONFIG_DIR, "get", name],
            stderr=subprocess.DEVNULL, text=True,
        )
        return out.strip()
    except Exception:
        return None


def session_active():
    try:
        with open(SESSION_FILE) as fh:
            data = json.load(fh)
        return data.get("mode") == "move"
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
    .axis-label {
      font-size: 12px;
      font-weight: bold;
      color: %s;
    }
    .sep {
      min-height: 1px;
      margin: 8px 2px;
      background-color: %s;
    }
    button {
      min-width: 48px;
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
    button.size-btn { min-width: 48px; }
    button.save { background-color: rgba(78, 154, 6, 0.25); }
    button.save:hover { background-color: rgba(78, 154, 6, 0.4); }
    button.cancel { background-color: rgba(204, 0, 0, 0.25); }
    button.cancel:hover { background-color: rgba(204, 0, 0, 0.4); }
    entry.size-entry {
      font-size: 14px;
      min-width: 48px;
      color: %s;
      background-color: %s;
      border-radius: 8px;
      padding: 2px 6px;
    }
    entry.size-entry:focus { background-color: %s; }
    """ % (
        font,
        rgba(bg, 0.97),
        rgba(light, 0.15),
        radius,
        rgba(light, 0.6 * alpha),
        rgba(light, alpha),      # .axis-label
        rgba(light, 0.1),
        rgba(light, 0.08),
        rgba(light, alpha),
        rgba(light, 0.16),
        rgba(light, 0.28),
        rgba(light, alpha),
        rgba(light, 0.08),
        rgba(light, 0.16),
    )


def action(widget, monitor, act, value=None):
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "move_ctl.py"),
           "--widget", widget, "--monitor", str(monitor), "--action", act]
    if value is not None:
        cmd += ["--value", str(value)]
    run(cmd)


def set_session_typing(flag):
    """(Re)write the session file with/without the 'typing' marker.

    While the resize entry owns the keyboard the evdev daemon must ignore
    every key (Enter would otherwise SAVE and -/+ would zoom); it skips all
    handling while session["typing"] is set. ESC is ignored too: click
    outside the entry first, then ESC cancels the session as usual.
    """
    try:
        with open(SESSION_FILE) as fh:
            data = json.load(fh)
        if data.get("mode") != "move":
            return
        if flag:
            data["typing"] = True
        else:
            data.pop("typing", None)
        with open(SESSION_FILE, "w") as fh:
            json.dump(data, fh)
    except Exception:
        pass


class PctField:
    """Editable percentage field bound to ONE eww variable + move_ctl action.

    One instance per Resize row of the control panel: the proportional row
    polls move_pct and applies set_scale (BOTH axes, aspect ratio kept), the
    W row polls move_pct and applies set_scale_x (width only), the H row
    polls move_pct_h and applies set_scale_y (height only).

    This class owns the typing-flag plumbing shared by all rows:

      * while a field owns the keyboard the evdev daemon must ignore every
        key (session["typing"] is set; Enter would otherwise SAVE and -/+
        would zoom),
      * the 250 ms variable poll must not overwrite the entry text mid-edit,
      * X11: the panel is an override-redirect toplevel, so clicking the
        entry NEVER moves the server-side input focus - keystrokes would
        keep going to whatever application was focused before. While the
        field owns the pointer we therefore take a GDK KEYBOARD GRAB: every
        key event is routed into this GTK app and delivered normally
        (MovePanel.on_win_key forwards into handle_key). Typing selects-all
        first, so digits REPLACE the old value. The grab is released when
        editing ends. On Wayland the layer-shell ON_DEMAND keyboard mode
        already delivers keys after a click, no grab needed.
    """

    def __init__(self, panel, varname, act):
        self.panel = panel          # owning MovePanel (widget / monitor)
        self.varname = varname      # polled eww variable (display source)
        self.act = act              # move_ctl.py action applied on Enter
        self.editing = False
        self.last_value = 100       # fallback for invalid input / drafts
        self.entry = Gtk.Entry.new()
        self.entry.get_style_context().add_class("size-entry")
        self.entry.set_alignment(0.5)
        self.entry.set_width_chars(4)
        self.entry.set_max_width_chars(5)
        self.entry.set_text("%d%%" % self.last_value)
        self.entry.connect("button-press-event", self.on_button_press)
        self.entry.connect("activate", self.on_activate)
        self.entry.connect("focus-in-event", self.on_focus_in)
        self.entry.connect("focus-out-event", self.on_focus_out)

    # ---- poll refresh -------------------------------------------------------
    def refresh(self):
        value = eww_get(self.varname)
        if not value:
            return
        try:
            self.last_value = int(round(float(value)))
            if not self.editing:
                self.entry.set_text("%d%%" % self.last_value)
        except ValueError:
            pass

    # ---- editing lifecycle --------------------------------------------------
    def _begin_editing(self):
        self.editing = True
        set_session_typing(True)

    def end_editing(self):
        if not self.editing:
            return
        self.editing = False
        set_session_typing(False)
        if not WAYLAND:
            try:
                Gdk.keyboard_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass
        # Discard an uncommitted draft; the poll restores the real value.
        self.entry.set_text("%d%%" % self.last_value)

    def on_button_press(self, entry, event):
        self._begin_editing()
        if not WAYLAND:
            try:
                Gdk.keyboard_grab(self.panel.win.get_window(), True, Gdk.CURRENT_TIME)
            except Exception:
                pass
        # Select the whole current value AFTER GTK's own press handling ran
        # (otherwise it clears our selection and typed digits would land
        # inside the old number). idle = post-default-handler.
        GLib.idle_add(entry.select_region, 0, -1)
        return False

    def on_focus_in(self, entry, event):
        self._begin_editing()
        return False

    def on_focus_out(self, entry, event):
        self.end_editing()
        return False

    def on_activate(self, entry):
        raw = entry.get_text().strip().rstrip("%").strip()
        try:
            value = float(raw)
        except ValueError:
            entry.set_text("%d%%" % self.last_value)
            return
        # move_ctl clamps to MIN/MAX_SCALE and refreshes the polled eww
        # variable, which the next tick reflects in the entry text.
        action(self.panel.widget, self.panel.monitor, self.act, value)
        entry.set_text("%d%%" % max(30, min(150, int(round(value)))))

    def handle_key(self, ev):
        """Window-level key routing while THIS field owns the keyboard."""
        name = Gdk.keyval_name(ev.keyval) or ""
        if name in ("Return", "KP_Enter"):
            self.on_activate(self.entry)
            return True
        if name == "BackSpace":
            txt = self.entry.get_text()
            self.entry.set_text(txt[:-1])
            return True
        if name and len(name) == 1 and (name.isdigit() or name in "+-."):
            self.entry.insert_text(name, self.entry.get_position())
            return True
        if name == "Escape":
            self.end_editing()
            return True
        return False


class MovePanel:
    def __init__(self, widget, monitor, x, y, frame_w, frame_h):
        self.widget = widget
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
        # The percentage fields of the three resize rows (created in
        # build_ui). They share ONE keyboard at a time; each keeps its own
        # editing state and last known value (see PctField). A LIST, not a
        # dict: two rows may poll the SAME variable (main + W both read
        # move_pct) and both must still be refreshed / routed keys.
        self.fields = []

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
        # The resize entry needs the keyboard (hand-typed percentage), so the
        # panel must be focusable; on X11 the entry additionally grabs the X
        # input focus when clicked (override-redirect windows get no WM help).
        self.win.set_accept_focus(True)
        self.win.set_default_size(MC_W, MC_H)

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
        # On X11 the full-screen eww move overlay is override-redirect, which
        # always floats above managed windows - so the panel must be
        # override-redirect too to receive clicks and be draggable at all.
        self.win.connect("realize", self.on_realize)

    def _release_keyboard(self, *_):
        """Safety net: never leave a keyboard grab behind."""
        if not WAYLAND:
            try:
                Gdk.keyboard_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass

    def on_realize(self, widget):
        if not WAYLAND:
            try:
                widget.get_window().set_override_redirect(True)
            except Exception:
                pass

    def raise_above(self):
        # Both the rectangle window and the panel are override-redirect
        # toplevels on X11, so their stacking follows the X server's map order
        # and the slower-starting rectangle window can map on top of the panel
        # and swallow its clicks. Raising every tick keeps the panel
        # deterministically above it for the whole session.
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

        # Draggable title bar: the whole top strip is the grab surface.
        title = Gtk.EventBox.new()
        title.get_style_context().add_class("title")
        box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        label = Gtk.Label.new("Move")
        box.pack_start(label, True, True, 0)
        title.add(box)
        title.set_events(Gdk.EventMask.BUTTON_PRESS_MASK
                         | Gdk.EventMask.BUTTON_RELEASE_MASK
                         | Gdk.EventMask.POINTER_MOTION_MASK)
        title.connect("realize", lambda w: self._grab_cursor(w))
        # Drag events are handled on the toplevel window, not the title
        # eventbox: during a pointer grab GDK delivers button/motion events to
        # the grabbed (toplevel) window, so an eventbox-only handler would
        # never see them. The press is gated to the title strip below.
        self.win.connect("button-press-event", self.on_press)
        self.win.connect("button-release-event", self.on_release)
        self.win.connect("motion-notify-event", self.on_motion)
        root.pack_start(title, False, False, 0)

        root.pack_start(self.btn("↑", "up"), False, False, 0)
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        row.get_style_context().add_class("row")
        row.pack_start(self.btn("←", "left"), True, True, 0)
        row.pack_start(self.btn("↓", "down"), True, True, 0)
        row.pack_start(self.btn("→", "right"), True, True, 0)
        root.pack_start(row, False, False, 0)

        root.pack_start(self.sep(), False, False, 0)

        resize_label = Gtk.Label.new("Resize")
        resize_label.get_style_context().add_class("title")
        root.pack_start(resize_label, False, False, 0)

        # Three resize rows: proportional (no label), width-only (W),
        # height-only (H). Every % is an editable entry (PctField); the
        # fields list itself is created in __init__.
        root.pack_start(self.pct_row(None, "zoom_out", "zoom_in",
                                     PctField(self, "move_pct", "set_scale")),
                        False, False, 0)
        root.pack_start(self.pct_row("W", "zoom_out_x", "zoom_in_x",
                                     PctField(self, "move_pct", "set_scale_x")),
                        False, False, 0)
        root.pack_start(self.pct_row("H", "zoom_out_y", "zoom_in_y",
                                     PctField(self, "move_pct_h", "set_scale_y")),
                        False, False, 0)

        root.pack_start(self.sep(), False, False, 0)

        root.pack_start(self.sep(), False, False, 0)

        # Inline error surface for a failed Save/Cancel (details in
        # logs/move_ctl.log): the old detached spawn made refusals invisible.
        self.status_label = Gtk.Label.new("")
        self.status_label.set_visible(False)
        self.status_label.set_halign(Gtk.Align.CENTER)
        self.status_label.get_style_context().add_class("axis-label")
        root.pack_start(self.status_label, False, False, 0)

        srow = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        srow.get_style_context().add_class("row")
        srow.pack_start(self.btn("Reset", "reset"), True, True, 0)
        srow.pack_start(self.btn("Save", "save", "save"), True, True, 0)
        srow.pack_start(self.btn("Cancel", "cancel", "cancel"), True, True, 0)
        root.pack_start(srow, False, False, 0)

        self.win.add(root)

    def pct_row(self, axis_label, out_act, in_act, field):
        """One − / % / + row of the Resize section.

        axis_label is None for the proportional row or "W"/"H"; the field's
        polled variable and applied action decide which axes the row
        resizes (see the module docstring).
        """
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        row.get_style_context().add_class("row")
        if axis_label:
            lab = Gtk.Label.new(axis_label)
            lab.get_style_context().add_class("axis-label")
            lab.set_size_request(16, -1)
            row.pack_start(lab, False, False, 2)
        self.fields.append(field)
        row.pack_start(self.btn("−", out_act, "size-btn"), True, True, 0)
        row.pack_start(field.entry, True, True, 0)
        row.pack_start(self.btn("+", in_act, "size-btn"), True, True, 0)
        return row

    def sep(self):
        sep = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        sep.get_style_context().add_class("sep")
        return sep

    @staticmethod
    def _grab_cursor(widget):
        try:
            window = widget.get_window()
            if window is not None:
                window.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "grab"))
        except Exception:
            pass

    def btn(self, text, act, extra=None):
        b = Gtk.Button.new_with_label(text)
        ctx = b.get_style_context()
        if extra:
            ctx.add_class(extra)
        b.connect("clicked", lambda *_: self.on_btn(act))
        return b

    def on_btn(self, act):
        if act in ("save", "cancel"):
            # SYNCHRONOUS on purpose: the old detached spawn (Popen + DEVNULL
            # stderr) made every failure invisible while the panel vanished --
            # e.g. an off-screen refusal looked exactly like "nothing
            # happened". The return code is now checked and errors surface
            # inline; details land in logs/move_ctl.log.
            try:
                res = subprocess.run(
                    [sys.executable, os.path.join(SCRIPT_DIR, "move_ctl.py"),
                     "--widget", self.widget, "--monitor", str(self.monitor),
                     "--action", act],
                    capture_output=True, text=True, timeout=20,
                )
            except Exception as exc:
                self.show_error(str(exc))
                return
            if res.returncode != 0:
                lines = [l for l in (res.stderr or "").splitlines()
                         + (res.stdout or "").splitlines() if l.strip()]
                self.show_error(lines[-1] if lines else "move_ctl rc=%d" % res.returncode)
                return
            Gtk.main_quit()
            return
        action(self.widget, self.monitor, act)

    def show_error(self, msg):
        self.status_label.set_text(msg if len(msg) <= 52 else msg[:49] + "...")
        self.status_label.set_visible(True)

    def on_win_key(self, wdg, ev):
        """Route keys into the percentage field that owns the keyboard.

        The override-redirect toplevel never gains the X input focus, so an
        entry cannot rely on normal key delivery - with the GDK keyboard
        grab held (button press on the entry), this window-level handler
        receives every keystroke and edits the text directly. Handles
        digits, backspace, +/- prefix and Return (=apply).
        """
        for field in self.fields:
            if field.editing:
                return field.handle_key(ev)
        return False

    # ---- periodic session watch + pct refresh ------------------------------
    def tick(self):
        if not session_active():
            Gtk.main_quit()
            return False
        self.raise_above()
        for field in self.fields:
            field.refresh()
        return True

    # ---- dragging ----------------------------------------------------------
    # Both compositors drag the panel live, keeping the grab point (pressed on
    # the title strip) under the cursor. The coordinate basis differs:
    #
    #   * X11     - deltas come from the ROOT coordinates. win.move uses
    #               absolute screen coordinates and root coords are real there,
    #               so the panel can be clamped to the monitor rectangle. The
    #               pointer is grabbed so motion keeps coming even when the
    #               cursor leaves the small panel.
    #   * Wayland - GDK reports only "fake root" coords for a layer-shell
    #               toplevel (always (0,0) offset + window-local), so root
    #               deltas would be wrong. The delta is computed from the
    #               window-relative event.x/y instead: the wl_pointer implicit
    #               grab (button pressed on the surface) keeps every motion
    #               event tied to the panel surface, so win_x + (event.x -
    #               grab_x) simplifies to the pointer position minus the grab
    #               offset, a true chase. NO Gdk.pointer_grab here: it would
    #               route events to the panel even while the cursor is over the
    #               full-monitor eww overlay, and those events carry overlay-
    #               relative (monitor) coordinates instead of panel-relative
    #               ones, making the position oscillate.
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
            nx = self.win_x + dx
            ny = self.win_y + dy
            # Margins are monitor-relative.
            nx = max(0, min(nx, max(0, self.frame_w - MC_W)))
            ny = max(0, min(ny, max(0, self.frame_h - MC_H)))
        else:
            # win.move uses absolute screen coordinates.
            nx = self.start_x + int(event.x_root - self.grab_root_x)
            ny = self.start_y + int(event.y_root - self.grab_root_y)
            nx = max(self.mon_ox, min(nx, self.mon_ox + max(0, self.frame_w - MC_W)))
            ny = max(self.mon_oy, min(ny, self.mon_oy + max(0, self.frame_h - MC_H)))
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
    ap.add_argument("--widget", required=True, choices=["clock", "panel"])
    ap.add_argument("--monitor", type=int, default=0)
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--frame-w", type=int, default=0)
    ap.add_argument("--frame-h", type=int, default=0)
    args = ap.parse_args()

    if not session_active():
        sys.exit(0)

    panel = MovePanel(args.widget, args.monitor, args.x, args.y, args.frame_w, args.frame_h)
    panel.win.show_all()
    panel.win.present()
    GLib.timeout_add(250, panel.tick)
    Gtk.main()


if __name__ == "__main__":
    main()