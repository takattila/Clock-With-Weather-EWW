#!/usr/bin/env python3
"""Draggable About window (GTK3).

Replaces the eww about_window: eww 0.5.0 cannot move its windows (geometry is
fixed at open time), so the About dialog is a small GTK3 toplevel with a
draggable title strip, using the same mechanics as scripts/move_panel.py:

  * X11     - override-redirect toplevel, dragged with GtkWindow.move
              (absolute screen coordinates).
  * Wayland - layer-shell OVERLAY surface (GtkLayerShell), dragged by updating
              the left/top margins.

The window shows four sections from scripts/about.py collect() plus runtime /
configuration data: Repository (URL, branch/tag, commit, date, author, message),
Runtime (compositor, monitor resolution, eww version, Python version, OS,
hostname, kernel, arch, memory, CPU), Dependencies (eww, python3, requests,
psutil, PyYAML, pillow, xprop, xrandr, Noto Sans with their installed
versions) and Configuration (appearance, icon set, corner radius, font, city,
units, language, hour format, scale). An "Open repository" button
(xdg-open), an "Export TXT" button (writes generated/about_export.txt and opens
it) and a Close button are at the bottom. Closing works three ways, like the
old eww window:

  * click outside  -> hits the eww dismiss_overlay (opened below this window by
                      about.py --open), which runs close_popup.py and clears the
                      session file,
  * ESC            -> the evdev daemon (scripts/input_daemon.py) runs
                      close_popup.py, also clearing the session file,
  * Close button   -> runs close_popup.py directly.

This window polls generated/input_session.json and quits once the "ctx" session
disappears, exactly like move_panel.py watches its own session.

Usage:
  ./about_win.py --monitor 0
"""

import argparse
import datetime
import importlib
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/
# scripts/widgets/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
THEME_FILE = os.path.join(CONFIG_DIR, "eww", "eww.theme.json")
sys.path.insert(0, SCRIPT_DIR)

from about import collect, https_url  # noqa: E402

try:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk, GLib
except Exception as exc:
    sys.exit("about_win: GTK3 unavailable: %s" % exc)

WAYLAND = "WAYLAND_DISPLAY" in os.environ and os.environ.get("GDK_BACKEND", "wayland") != "x11"

if WAYLAND:
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except Exception as exc:
        sys.exit("about_win: GtkLayerShell unavailable: %s" % exc)

ABOUT_W = 580
ABOUT_H = 620
TITLE_H = 30


def theme_values():
    try:
        with open(THEME_FILE) as fh:
            data = json.load(fh)
        bg = data.get("bg_color", "#000000")
        light = data.get("color_light", "#ffffff")
        dark = data.get("color_dark", "#9e9e9e")
        alpha = float(data.get("color_light_alpha", 1.0) or 1.0)
        radius = int(data.get("bg_radius", 15) or 0)
        font = data.get("font_face", "Noto Sans")
        icon_set = data.get("icon_set", "")
        return bg, light, dark, alpha, radius, font, icon_set
    except Exception:
        return "#000000", "#ffffff", "#9e9e9e", 1.0, 15, "Noto Sans", ""


def run(cmd):
    try:
        subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True, cwd=CONFIG_DIR,
        )
    except Exception:
        pass


def close_popup():
    run([sys.executable, os.path.join(SCRIPT_DIR, "close_popup.py")])


def session_active():
    try:
        with open(SESSION_FILE) as fh:
            return json.load(fh).get("mode") == "ctx"
    except Exception:
        return False


def monitor_for_point(monitors, px, py):
    for mon in monitors:
        if mon["x"] <= px < mon["x"] + mon["width"] and mon["y"] <= py < mon["y"] + mon["height"]:
            return mon
    return None


def get_monitors():
    try:
        out = subprocess.check_output(
            [sys.executable, os.path.join(SCRIPTS_DIR, "core", "monitors.py")],
            stderr=subprocess.DEVNULL, text=True, timeout=5,
        )
        return json.loads(out).get("monitors", [])
    except Exception:
        return []


def compositor_name():
    try:
        out = subprocess.check_output(
            [sys.executable, os.path.join(SCRIPTS_DIR, "core", "monitors.py")],
            stderr=subprocess.DEVNULL, text=True, timeout=5,
        )
        return json.loads(out).get("compositor", "")
    except Exception:
        return ""


def monitor_resolution(monitor_index):
    for mon in get_monitors():
        if mon.get("index") == monitor_index:
            return "%dx%d" % (mon["width"], mon["height"])
    return ""


def config_value(key, monitor=None):
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "core", "config.py"), "--key", key]
    if monitor is not None:
        cmd += ["--monitor", str(monitor)]
    try:
        out = subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, text=True, timeout=5,
        )
        return out.strip()
    except Exception:
        return ""


def eww_version():
    try:
        out = subprocess.check_output(
            ["eww", "--version"], stderr=subprocess.DEVNULL, text=True, timeout=5,
        )
        return out.strip()
    except Exception:
        return ""


def python_version():
    try:
        import platform
        return platform.python_version()
    except Exception:
        return ""


def os_name():
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    try:
        import platform
        return "%s %s" % (platform.system(), platform.release())
    except Exception:
        return ""


def lib_version(module_name):
    """Import a Python module and return its __version__ (or "")."""
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, "__version__", "") or ""
    except Exception:
        return ""


def cmd_version(cmd):
    """Run an external command and return the first line of its output."""
    try:
        out = subprocess.check_output(
            cmd, stderr=subprocess.STDOUT, text=True, timeout=5,
        )
        for line in out.splitlines():
            if line.strip():
                return line.strip()
        return ""
    except Exception:
        return ""


def font_status():
    """Return the family fc-match picks for "Noto Sans" (installed / fallback)."""
    try:
        out = subprocess.check_output(
            ["fc-match", "-f", "%{family[0]}", "Noto Sans"],
            stderr=subprocess.DEVNULL, text=True, timeout=5,
        ).strip()
        if not out:
            return ""
        if out.lower() == "noto sans":
            return "installed"
        return "fallback: %s" % out
    except Exception:
        return ""


def hostname_name():
    try:
        import platform
        return platform.node()
    except Exception:
        return ""


def kernel_version():
    try:
        import platform
        return platform.release()
    except Exception:
        return ""


def arch_name():
    try:
        import platform
        return platform.machine()
    except Exception:
        return ""


def human_size(num_bytes):
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if num_bytes < 1024:
            return "%.0f %s" % (num_bytes, unit)
        num_bytes /= 1024.0
    return "%.0f PiB" % num_bytes


def memory_total():
    try:
        import psutil
        return human_size(psutil.virtual_memory().total)
    except Exception:
        return ""


def cpu_info():
    try:
        import psutil
        count = psutil.cpu_count(logical=True) or 0
        try:
            freq = psutil.cpu_freq()
            if freq is not None and freq.current:
                return "%d @ %.0f MHz" % (count, freq.current)
        except Exception:
            pass
        return "%d" % count
    except Exception:
        return ""


def dependencies():
    """Dependencies of the widget with their installed versions.

    Mirrors docs/WIKI.md: eww, python3, the four Python packages and the
    X11 / font helpers the widget relies on at runtime.
    """
    return [
        ("eww", eww_version()),
        ("python3", python_version()),
        ("requests", lib_version("requests")),
        ("psutil", lib_version("psutil")),
        ("PyYAML", lib_version("yaml")),
        ("pillow", lib_version("PIL")),
        ("xprop", cmd_version(["xprop", "-version"])),
        ("xrandr", cmd_version(["xrandr", "--version"])),
        ("Noto Sans", font_status()),
    ]


def set_position(win, x, y):
    if WAYLAND:
        try:
            GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, x)
            GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, y)
        except Exception:
            pass
    else:
        win.move(x, y)


def build_css(bg, light, dark, alpha, radius, font):
    def rgba(c, a):
        return "rgba(%d, %d, %d, %s)" % (
            int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), a,
        )

    return """
    * {
      font-family: "%s";
      outline: none;
    }
    .about {
      background-color: %s;
      border: 1px solid %s;
      border-radius: %dpx;
      padding: 12px;
    }
    .title {
      font-size: 15px;
      font-weight: bold;
      color: %s;
      padding: 4px 4px 10px 4px;
    }
    .sec {
      font-size: 13px;
      font-weight: bold;
      color: %s;
      padding: 8px 4px 2px 4px;
    }
    .k {
      font-size: 13px;
      color: %s;
      min-width: 110px;
      padding: 1px 4px;
    }
    .v {
      font-size: 13px;
      color: %s;
      padding: 1px 4px;
    }
    .sep {
      min-height: 1px;
      margin: 8px 2px;
      background-color: %s;
    }
    .scroll {
      background-color: transparent;
    }
    .scroll > scrollbar {
      background-color: transparent;
    }
    button {
      min-width: 100px;
      min-height: 32px;
      margin: 4px;
      border: none;
      border-radius: 8px;
      background-color: %s;
      color: %s;
      font-size: 14px;
      padding: 0;
    }
    button:hover { background-color: %s; }
    button:active { background-color: %s; }
    button.open { background-color: %s; }
    button.open:hover { background-color: %s; }
    button.export { background-color: %s; }
    button.export:hover { background-color: %s; }
    button.close { background-color: rgba(204, 0, 0, 0.25); }
    button.close:hover { background-color: rgba(204, 0, 0, 0.4); }
    """ % (
        font,
        rgba(bg, 0.97),
        rgba(light, 0.15),
        radius,
        rgba(light, alpha),
        rgba(light, alpha),
        rgba(dark, alpha),
        rgba(light, alpha),
        rgba(light, 0.1),
        rgba(light, 0.08),
        rgba(light, alpha),
        rgba(light, 0.16),
        rgba(light, 0.28),
        rgba("#4e9a06", 0.25),
        rgba("#4e9a06", 0.4),
        rgba("#3184bd", 0.25),
        rgba("#3184bd", 0.4),
    )


class AboutWin:
    def __init__(self, monitor, x, y, fx, fy, fw, fh):
        self.monitor = monitor
        # Window position in frame-local coordinates (0/0 = frame top-left).
        self.win_x = x
        self.win_y = y
        self.frame_x = fx
        self.frame_y = fy
        self.frame_w = fw
        self.frame_h = fh
        self.drag = False
        self.grab_root_x = 0.0
        self.grab_root_y = 0.0
        self.grab_x = 0.0
        self.grab_y = 0.0
        self.start_x = x
        self.start_y = y

        bg, light, dark, alpha, radius, font, icon_set = theme_values()
        info = collect()
        self.url = info.get("url") or ""

        self.win = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
        self.win.set_title("")
        self.win.set_decorated(False)
        self.win.set_skip_taskbar_hint(True)
        self.win.set_skip_pager_hint(True)
        self.win.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.win.set_keep_above(True)
        self.win.set_resizable(False)
        self.win.set_accept_focus(False)
        self.win.set_default_size(ABOUT_W, ABOUT_H)

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
            self.win.move(self.frame_x + x, self.frame_y + y)

        self.build_ui(bg, light, dark, alpha, radius, font, icon_set, info)
        self.win.connect("destroy", lambda *_: Gtk.main_quit())
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

    def build_ui(self, bg, light, dark, alpha, radius, font, icon_set, info):
        css = build_css(bg, light, dark, alpha, radius, font)
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        root = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        root.get_style_context().add_class("about")

        # Draggable title strip: the whole top area is the grab surface.
        title = Gtk.EventBox.new()
        title.get_style_context().add_class("title")
        box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        label = Gtk.Label.new("About")
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

        # Scrollable content so all sections fit in the fixed window even
        # with long commit messages / URLs.
        scrolled = Gtk.ScrolledWindow.new(None, None)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.get_style_context().add_class("scroll")
        content = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)

        # All sections collected once; the same rows feed both the UI and the
        # TXT export (on_export).
        self.rows = [
            ("Repository", [
                ("URL", info.get("url", "")),
                ("Branch", "%s   (%s)" % (info.get("branch", ""), info.get("tag", ""))),
                ("Commit", "%s  %s" % (info.get("commit", ""), info.get("full_commit", ""))),
                ("Date", info.get("date", "")),
                ("Author", "%s <%s>" % (info.get("author", ""), info.get("author_email", ""))),
                ("Message", info.get("message", "")),
            ]),
            ("Runtime", [
                ("Compositor", compositor_name()),
                ("Monitor", monitor_resolution(self.monitor)),
                ("Eww", eww_version()),
                ("Python", python_version()),
                ("OS", os_name()),
                ("Hostname", hostname_name()),
                ("Kernel", kernel_version()),
                ("Arch", arch_name()),
                ("Memory", memory_total()),
                ("CPU", cpu_info()),
            ]),
            ("Dependencies", list(dependencies())),
            ("Configuration", [
                ("Appearance", config_value("appearance")),
                ("Icon set", icon_set),
                ("Corner radius", "%d px" % radius),
                ("Font", font),
                ("City", config_value("city")),
                ("Units", config_value("units")),
                ("Language", config_value("lang")),
                ("Hour format", config_value("hour_format")),
                ("Scale", config_value("scale", self.monitor)),
            ]),
        ]

        for sec_name, rows in self.rows:
            content.pack_start(self.sec(sec_name), False, False, 0)
            for key, value in rows:
                content.pack_start(self.kv(key, value), False, False, 0)

        scrolled.add(content)
        root.pack_start(scrolled, True, True, 0)

        brow = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        open_btn = Gtk.Button.new_with_label("Open repository")
        open_btn.get_style_context().add_class("open")
        open_btn.connect("clicked", self.on_open)
        export_btn = Gtk.Button.new_with_label("Export TXT")
        export_btn.get_style_context().add_class("export")
        export_btn.connect("clicked", self.on_export)
        close_btn = Gtk.Button.new_with_label("Close")
        close_btn.get_style_context().add_class("close")
        close_btn.connect("clicked", self.on_close)
        brow.pack_start(open_btn, True, True, 0)
        brow.pack_start(export_btn, True, True, 0)
        brow.pack_start(close_btn, True, True, 0)
        root.pack_start(brow, False, False, 0)

        self.win.add(root)

    @staticmethod
    def sec(text):
        header = Gtk.Label.new(text)
        header.get_style_context().add_class("sec")
        header.set_halign(Gtk.Align.START)
        return header

    @staticmethod
    def kv(key, value):
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        k = Gtk.Label.new(key + ":")
        k.get_style_context().add_class("k")
        k.set_halign(Gtk.Align.START)
        k.set_selectable(True)
        v = Gtk.Label.new(value)
        v.get_style_context().add_class("v")
        v.set_halign(Gtk.Align.START)
        v.set_xalign(0.0)
        v.set_line_wrap(True)
        v.set_selectable(True)
        row.pack_start(k, False, False, 0)
        row.pack_start(v, True, True, 0)
        return row

    @staticmethod
    def _grab_cursor(widget):
        try:
            window = widget.get_window()
            if window is not None:
                window.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "grab"))
        except Exception:
            pass

    def close_dismiss_layers(self):
        # The transparent dismiss layers sit on the compositor's overlay
        # level - ABOVE every normal window. Left mapped they would eat
        # every click meant for other applications, so they are closed here
        # before a browser / editor is launched (the About window itself stays
        # open: it quits when the session file disappears).
        try:
            mon = subprocess.check_output(
                ["python3", os.path.join(CONFIG_DIR, "scripts", "core", "monitors.py")],
                stderr=subprocess.DEVNULL, text=True, timeout=5,
            )
            screens = [int(m["index"]) for m in json.loads(mon).get("monitors", [])]
        except Exception:
            screens = []
        for idx in screens or [0]:
            run(["eww", "--config", EWW_CONFIG_DIR, "close",
                 "dismiss_overlay_%d" % idx])
        run(["eww", "--config", EWW_CONFIG_DIR, "close", "dismiss_overlay"])

    def export_text(self):
        out = ["=== Clock-With-Weather-EWW - About ===", ""]
        for sec_name, rows in self.rows:
            out.append("--- %s ---" % sec_name)
            for key, value in rows:
                out.append("%s: %s" % (key, value))
            out.append("")
        out.append("Generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return "\n".join(out).rstrip() + "\n"

    def on_export(self, *_):
        try:
            gen_dir = os.path.join(CONFIG_DIR, "generated")
            os.makedirs(gen_dir, exist_ok=True)
            path = os.path.join(gen_dir, "about_export.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.export_text())
            self.close_dismiss_layers()
            run(["xdg-open", path])
        except Exception:
            pass

    def on_open(self, *_):
        if self.url:
            self.close_dismiss_layers()
            run(["xdg-open", self.url])

    def on_close(self, *_):
        close_popup()
        Gtk.main_quit()

    # ---- dragging (same logic as move_panel.py) -----------------------------
    # X11: deltas from the ROOT coordinates; win.move uses absolute screen
    # coordinates and root coords are real there.
    # Wayland: GDK reports only "fake root" coords for a layer-shell toplevel,
    # so the delta comes from the window-relative event.x/y (the wl_pointer
    # implicit grab keeps every motion event tied to the panel surface). NO
    # Gdk.pointer_grab here: it would route events to this window even while the
    # cursor is over the full-monitor dismiss_overlay and those events carry
    # overlay-relative coordinates instead, making the position oscillate.
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
            nx = max(0, min(nx, max(0, self.frame_w - ABOUT_W)))
            ny = max(0, min(ny, max(0, self.frame_h - ABOUT_H)))
        else:
            nx = self.start_x + int(event.x_root - self.grab_root_x)
            ny = self.start_y + int(event.y_root - self.grab_root_y)
            nx = max(0, min(nx, max(0, self.frame_w - ABOUT_W)))
            ny = max(0, min(ny, max(0, self.frame_h - ABOUT_H)))
        if nx != self.win_x or ny != self.win_y:
            self.win_x, self.win_y = nx, ny
            set_position(self.win, self.frame_x + nx, self.frame_y + ny)
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

    def tick(self):
        if not session_active():
            Gtk.main_quit()
            return False
        return True


def clamp(value, lo, hi):
    return max(lo, min(value, hi))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--monitor", type=int, default=0)
    args = ap.parse_args()

    monitors = get_monitors()
    mon = next((m for m in monitors if m["index"] == args.monitor), None)
    if mon is None:
        mon = {"index": 0, "x": 0, "y": 0, "width": 1920, "height": 1080}

    # Center on the monitor (the layer-shell margins on Wayland and the X11
    # screen coordinates are both monitor-relative through mon's origin).
    mx, my, mw, mh = mon["x"], mon["y"], mon["width"], mon["height"]
    cx = clamp((mw - ABOUT_W) // 2, 0, max(0, mw - ABOUT_W))
    cy = clamp((mh - ABOUT_H) // 2, 0, max(0, mh - ABOUT_H))

    win = AboutWin(args.monitor, cx, cy, mx, my, mw, mh)
    win.win.show_all()
    win.win.present()
    GLib.timeout_add(250, win.tick)
    Gtk.main()


if __name__ == "__main__":
    main()
