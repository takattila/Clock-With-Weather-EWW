#!/usr/bin/env python3
"""Draggable theme editor (GTK3).

Opened by scripts/move/theme_ctl.py CENTERED ON the monitor the context-menu
was opened on (same centering as the About dialog). Edits every field an
appearance definition (appearance.yaml or the inline `appearance:` map) can
carry, in the same structure theme.py parses:

    theme | icon.set | icon.transparency{light,dark} | icon.color{light,dark}
    font.face | font.color{light,dark} | font.transparency{light,dark}
    font.shadow{color,blur} | background{transparency,color}
    chart.colors{cpu,memory,net_down,net_up} | chart.glow
    panel.background{color,transparency,gradient}     + system.corner_radius

Editing is DRAFT-ONLY: nothing is written until a footer button is pressed.

    Save     -> the WHOLE normalized appearance map + system.corner_radius is
                written inline into the git-ignored config.local.yaml, so the
                shipped theme files under assets/themes/appearance/ stay
                untouched and the watcher reloads the widget live.
    Save As  -> asks for a name and creates a NEW theme
                assets/themes/appearance/<name>/appearance.yaml (minimalized
                to the non-default keys, the way the shipped themes are
                written) and activates it through config.local.yaml, so it
                appears in the right-click Theme picker immediately.
    Preview  -> applies the DRAFT to the LIVE widget right now (colors, fonts,
                radius, glow, panel and the re-tinted icon PNGs) WITHOUT
                saving: config.local.yaml stays untouched, so only Save makes
                it permanent. An un-saved preview reverts to the original look
                on Reset / Cancel / editor close (via theme_preview.py).
    Reset    -> refills the form from the LOADED source and reverts any
                un-saved Preview; writes nothing.
    Cancel   -> discards, reverts any un-saved Preview and closes.

Every color field has a swatch button (custom GTK color dialog, override-
redirect so it floats ABOVE the editor and the click-outside overlay), a hex
entry and an on-screen eyedropper ("Pick"). On X11 the picker grabs the pointer and
wins: a full-screen capture is taken once, an overlay follows the cursor with
a live hex readout and the picked pixel is applied on click. On Wayland there
is no global grab, so the cursor position is polled through the KWin scripting
API (workarea.kde_cursor) on a background thread -- so the magnifier/readout
track the real pointer without freezing the GTK main loop (kde_cursor blocks on
subprocess + sleeps); clicking applies the color at the tracked position.

The window mechanics mirror scripts/move/weather_panel.py exactly: draggable
title strip, override-redirect toplevel (X11) / layer-shell OVERLAY (Wayland),
per-entry keyboard grab with the "typing" session marker, and the session
poll that quits once the "theme" session disappears (ESC through the evdev
daemon, click-outside through dismiss_overlay, or the footer buttons).

The window HEIGHT adapts to the desktop: the controller (theme_ctl.py) sizes
it to fit the smallest connected screen's usable height (screen minus
taskbar), so it can be dragged onto any monitor. On X11 the drag is clamped to
the WHOLE virtual desktop (union of all monitors), letting the window be moved
from one monitor to another. Child dialogs (the Save As name prompt and the
color chooser) are CENTERED on the editor, follow it during a drag, and are
clamped to the same virtual desktop, so they come along to whichever monitor
the editor lands on. On X11 the Save As dialog takes the keyboard focus with a
Gdk.keyboard_grab exactly like the editor's own entry fields, so the name can
be typed straight in.

Usage:
  ./theme_panel.py --monitor 0 --x 300 --y 200 --frame-w 1920 --frame-h 1080 \
                   --win-h 738
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

try:
    import cairo  # for cr.select_font_face constants
except Exception:
    cairo = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CR_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/
# scripts/move/ -> scripts/ -> repo (widget) root
CONFIG_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
EWW_CONFIG_DIR = os.path.join(CONFIG_DIR, "eww")  # the eww --config target
SESSION_FILE = os.path.join(CONFIG_DIR, "generated", "input_session.json")
PREVIEW_FILE = os.path.join(CONFIG_DIR, "generated", "preview.json")
PREVIEW_SCRIPT = os.path.join(SCRIPT_DIR, "theme_preview.py")
sys.path.insert(0, os.path.join(CONFIG_DIR, "scripts", "core"))

import yaml  # noqa: E402

try:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, Gtk, GLib, GdkPixbuf
except Exception as exc:
    sys.exit("theme_panel: GTK3 unavailable: %s" % exc)

WAYLAND = "WAYLAND_DISPLAY" in os.environ and os.environ.get("GDK_BACKEND", "wayland") != "x11"

if WAYLAND:
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except Exception as exc:
        sys.exit("theme_panel: GtkLayerShell unavailable: %s" % exc)

EDITOR_W = 560
EDITOR_H = 760
TITLE_H = 30

DEFAULT_FONT = "Noto Sans"
DEFAULT_RADIUS = 15

FIELD_KEYS = (
    "theme",
    "icon_set",
    "icon_transparency_light", "icon_transparency_dark",
    "icon_color_light", "icon_color_dark",
    "font_face",
    "font_color_light", "font_color_dark",
    "font_transparency_light", "font_transparency_dark",
    "font_shadow_color", "font_shadow_blur",
    "background_color", "background_transparency",
    "chart_cpu", "chart_memory", "chart_down", "chart_up", "chart_glow",
    "panel_color", "panel_transparency", "panel_gradient",
    "corner_radius",
)

# Keys whose value may be empty (meaning "omit the section").
OPTIONAL_HEX_KEYS = ("icon_color_light", "icon_color_dark",
                     "font_shadow_color", "panel_color")


# ---------------------------------------------------------------------------
# Pure, headless helpers (under tests/test_theme_panel.py).
# ---------------------------------------------------------------------------

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _f(value, default):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return clamp(v, 0.0, 1.0)


def _i(value, default):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return v


def normalize_hex(value):
    """'#rrggbb' (also 3-digit / upper-case / without '#') -> '#rrggbb' or None."""
    value = str(value).strip() if value is not None else ""
    if not value:
        return None
    t = value.lstrip("#")
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    if len(t) == 6 and all(c in "0123456789abcdefABCDEF" for c in t):
        return "#" + t.lower()
    return None


def hex_or(value, default):
    """normalize_hex() or `default` when empty/invalid."""
    h = normalize_hex(value)
    return h if h is not None else default


def rgb_hex(r, g, b):
    return "#%02x%02x%02x" % (
        clamp(int(round(r)), 0, 255), clamp(int(round(g)), 0, 255),
        clamp(int(round(b)), 0, 255),
    )


def pixel_color_at(pixels, rowstride, n_channels, x, y, width, height):
    """RGB triple of the 8-bit pixel at (x, y), or None outside the surface.

    Works on any PIL/GTK-style buffer (bytes, bytearray, memoryview):
    `pixels[off]` is the byte at `y*rowstride + x*n_channels`; the first three
    channels are the color (alpha, if any, sits at +3 and is ignored).
    """
    if x < 0 or y < 0 or x >= width or y >= height:
        return None
    off = y * rowstride + x * n_channels
    return (int(pixels[off]), int(pixels[off + 1]), int(pixels[off + 2]))


def raw_pixbuf(pixbuf):
    """(pixels, rowstride, n_channels, width, height) snapshot of a Pixbuf."""
    return (pixbuf.get_pixels(), pixbuf.get_rowstride(),
            pixbuf.get_n_channels(), pixbuf.get_width(), pixbuf.get_height())


def _transparency(d):
    """Per-side {light, dark} transparency floats from an appearance map."""
    source = d or {}
    return {
        "light": _f(source.get("light"), 1.0),
        "dark": _f(source.get("dark"), 1.0),
    }


def to_draft(appearance, corner_radius=DEFAULT_RADIUS):
    """Flatten an appearance map into the editor's flat draft model.

    Every missing leaf takes the SAME default theme.py's parse_appearance
    uses, so an empty map yields a valid, fully-populated draft.
    """
    a = appearance or {}
    font = a.get("font") or {}
    font_color = font.get("color") or {}
    icon = a.get("icon") or {}
    icon_color = icon.get("color") or {}
    background = a.get("background") or {}
    chart = a.get("chart") or {}
    chart_colors = chart.get("colors") or {}
    panel = a.get("panel") or {}
    panel_background = panel.get("background") or {}

    it = _transparency(icon.get("transparency"))
    ft = _transparency(font.get("transparency"))
    light = hex_or(font_color.get("light"), "#ffffff")
    return {
        "theme": str(a.get("theme", "light")),
        "icon_set": str(icon.get("set", "dovora")),
        "icon_transparency_light": it["light"],
        "icon_transparency_dark": it["dark"],
        "icon_color_light": hex_or(icon_color.get("light"), ""),
        "icon_color_dark": hex_or(icon_color.get("dark"), ""),
        "font_face": str(font.get("face", DEFAULT_FONT)) or DEFAULT_FONT,
        "font_color_light": light,
        "font_color_dark": hex_or(font_color.get("dark"), "#9e9e9e"),
        "font_transparency_light": ft["light"],
        "font_transparency_dark": ft["dark"],
        "font_shadow_color": hex_or(font.get("shadow", {}).get("color"), ""),
        "font_shadow_blur": _i(font.get("shadow", {}).get("blur"), 0),
        "background_color": hex_or(background.get("color"), "#000000"),
        "background_transparency": _f(background.get("transparency"), 0.0),
        "chart_cpu": hex_or(chart_colors.get("cpu"), light),
        "chart_memory": hex_or(chart_colors.get("memory"), light),
        "chart_down": hex_or(chart_colors.get("net_down"), light),
        "chart_up": hex_or(chart_colors.get("net_up"), light),
        "chart_glow": bool(chart.get("glow", False)),
        "panel_color": hex_or(panel_background.get("color"), ""),
        "panel_transparency": _f(panel_background.get("transparency"), 0.0),
        "panel_gradient": str(panel_background.get("gradient") or "").strip(),
        "corner_radius": _i(corner_radius, DEFAULT_RADIUS),
    }


def normalize_appearance(draft):
    """The FULL appearance map for `draft` (every section present and valid).

    Empty icon colors omit the `icon.color` section ('' would otherwise make
    generate() try to tint the PNGs with an empty color), an empty shadow
    omits `font.shadow`, and an empty panel color omits `panel` (theme.py
    falls back to the widget background). Writes the full inline map into
    config.local.yaml for the editor's Save button.
    """
    light = hex_or(draft.get("font_color_light"), "#ffffff")
    icon_color = {}
    for side in ("light", "dark"):
        v = hex_or(draft.get("icon_color_%s" % side), "")
        if v:
            icon_color[side] = v
    font_shadow = {}
    sc = hex_or(draft.get("font_shadow_color"), "")
    if sc:
        font_shadow = {"color": sc, "blur": max(1, _i(draft.get("font_shadow_blur"), 1))}
    panel = {}
    pc = hex_or(draft.get("panel_color"), "")
    if pc:
        panel_background = {
            "color": pc,
            "transparency": _f(draft.get("panel_transparency"), 0.0),
        }
        gradient = (draft.get("panel_gradient") or "").strip()
        if gradient:
            panel_background["gradient"] = gradient
        panel = {"background": panel_background}
    return {
        "theme": "dark" if draft.get("theme") == "dark" else "light",
        "icon": dict(
            {"set": (draft.get("icon_set") or "dovora").strip() or "dovora",
             "transparency": {
                 "light": _f(draft.get("icon_transparency_light"), 1.0),
                 "dark": _f(draft.get("icon_transparency_dark"), 1.0),
             }},
            **(dict(color=icon_color) if icon_color else {}),
        ),
        "font": dict(
            {"face": (draft.get("font_face") or DEFAULT_FONT).strip() or DEFAULT_FONT,
             "color": {
                 "light": light,
                 "dark": hex_or(draft.get("font_color_dark"), "#9e9e9e"),
             },
             "transparency": {
                 "light": _f(draft.get("font_transparency_light"), 1.0),
                 "dark": _f(draft.get("font_transparency_dark"), 1.0),
             }},
            **(dict(shadow=font_shadow) if font_shadow else {}),
        ),
        "background": {
            "transparency": _f(draft.get("background_transparency"), 0.0),
            "color": hex_or(draft.get("background_color"), "#000000"),
        },
        "chart": {
            "colors": {
                "cpu": hex_or(draft.get("chart_cpu"), light),
                "memory": hex_or(draft.get("chart_memory"), light),
                "net_down": hex_or(draft.get("chart_down"), light),
                "net_up": hex_or(draft.get("chart_up"), light),
            },
            "glow": bool(draft.get("chart_glow", False)),
        },
        **({"panel": panel} if panel else {}),
    }


def minimalize_appearance(draft):
    """normalize_appearance() minus the trivially-default `chart` section.

    Shipped theme files omit the chart block entirely when all four chart
    colors equal font.color.light and glow is off; `-bg` themes show it once
    any value deviates. Used by Save As, so a new theme written to
    assets/themes/appearance/ reads exactly like the checked-in ones.
    """
    m = normalize_appearance(draft)
    colors = m["chart"]["colors"]
    light = m["font"]["color"]["light"]
    if not m["chart"]["glow"] and all(v == light for v in colors.values()):
        m.pop("chart", None)
    return m


def validate(key, value):
    """(ok, error_msg) for ONE flat draft field (pure/testable)."""
    value = "" if value is None else str(value)
    if key == "theme":
        if value in ("light", "dark"):
            return True, None
        return False, "theme must be light or dark"
    if key == "icon_set":
        if value.strip():
            return True, None
        return False, "icon set must not be empty"
    if key == "font_face":
        if value.strip():
            return True, None
        return False, "font must not be empty"
    if key in ("icon_transparency_light", "icon_transparency_dark",
               "font_transparency_light", "font_transparency_dark",
               "background_transparency", "panel_transparency"):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False, "%s must be between 0 and 1" % key
        if 0.0 <= v <= 1.0:
            return True, None
        return False, "%s must be between 0 and 1" % key
    if key == "font_shadow_blur":
        try:
            v = int(value)
        except ValueError:
            return False, "glow blur must be a whole number"
        if 0 <= v <= 120:
            return True, None
        return False, "glow blur must be between 0 and 120"
    if key == "corner_radius":
        try:
            v = int(value)
        except ValueError:
            return False, "corner radius must be a whole number"
        if 0 <= v <= 200:
            return True, None
        return False, "corner radius must be between 0 and 200"
    if key in ("icon_color_light", "icon_color_dark", "font_color_light",
               "font_color_dark", "font_shadow_color", "background_color",
               "chart_cpu", "chart_memory", "chart_down", "chart_up",
               "panel_color"):
        if not value and key in OPTIONAL_HEX_KEYS:
            return True, None
        if normalize_hex(value) is None:
            return False, "%s must be #rrggbb" % key
        return True, None
    if key == "panel_gradient":
        if len(value) > 200:
            return False, "gradient must be 200 chars or fewer"
        if "\n" not in value:
            return True, None
        return False, "gradient must stay on one line"
    if key == "chart_glow":
        return True, None
    return False, "unknown field: %s" % key


def validate_draft(draft):
    """(ok, first_error_msg) over every field of a draft dict."""
    for key in FIELD_KEYS:
        ok, msg = validate(key, draft.get(key))
        if not ok:
            return False, msg
    return True, None


def available_icon_sets(config_dir):
    """Sorted icon-set names present under assets/icons-src/{light,dark}/weather."""
    sets = set()
    for side in ("light", "dark"):
        base = os.path.join(config_dir, "assets", "icons-src", side, "weather")
        try:
            for name in os.listdir(base):
                if os.path.isdir(os.path.join(base, name)):
                    sets.add(name)
        except OSError:
            continue
    return sorted(sets)


def load_source(config_dir):
    """(name, draft, corner_radius, source_label) of the EFFECTIVE appearance.

    `appearance` is either a string (a theme directory) or an inline map in
    config.local.yaml; the merged config (config_io) decides. corner_radius
    comes from system.corner_radius (config.yaml default 15).
    """
    import config_io

    cfg = config_io.load_merged(config_dir)
    appearance = cfg.get("appearance", "light")
    radius = _i(((cfg.get("system") or {}).get("corner_radius")
                 or DEFAULT_RADIUS), DEFAULT_RADIUS)
    if isinstance(appearance, dict):
        return ("custom", to_draft(appearance, radius), radius,
                "inline (config.local.yaml)")
    name = str(appearance)
    path = os.path.join(config_dir, "assets", "themes", "appearance",
                        name, "appearance.yaml")
    if not os.path.isfile(path):
        return (name, to_draft({}, radius), radius,
                "%s (missing file)" % name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        data = {}
    a = data.get("appearance") if isinstance(data, dict) else None
    return (name, to_draft(a or {}, radius), radius, "%s (theme file)" % name)


def save_inline_override(config_dir, draft, corner_radius):
    """Write the FULL appearance map + system.corner_radius into config.local.yaml.

    Preserves every other key of the local file. Returns (ok, error_msg).
    """
    try:
        import config_io

        path = config_io.local_path(config_dir)
        if os.path.isfile(path):
            data = config_io.load_file(config_dir, config_io.LOCAL_CONFIG_FILE)
        else:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data["appearance"] = normalize_appearance(draft)
        system = data.get("system")
        if not isinstance(system, dict):
            system = {}
            data["system"] = system
        system["corner_radius"] = _i(corner_radius, DEFAULT_RADIUS)
        config_io.save_local(config_dir, data)
        return True, None
    except Exception as exc:
        return False, str(exc)


NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def save_as_theme(config_dir, name, draft):
    """Create assets/themes/appearance/<name>/appearance.yaml and activate it.

    The file is written minimalized (only the non-default keys, like the
    checked-in themes) and then activated by setting `appearance: <name>` in
    config.local.yaml, so it shows up in the right-click Theme picker right
    away. Returns (ok, error_msg).
    """
    name = (name or "").strip()
    if not name or not NAME_RE.match(name):
        return False, "invalid theme name (letters, digits, . _ - only)"
    themes_dir = os.path.join(config_dir, "assets", "themes", "appearance")
    target = os.path.join(themes_dir, name)
    if os.path.isdir(target):
        return False, "a theme named '%s' already exists" % name
    try:
        os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, "appearance.yaml"), "w",
                  encoding="utf-8") as fh:
            yaml.safe_dump({"appearance": minimalize_appearance(draft)}, fh,
                           sort_keys=False, allow_unicode=True,
                           default_flow_style=False)
    except Exception as exc:
        return False, str(exc)
    try:
        import config_io

        path = config_io.local_path(config_dir)
        if os.path.isfile(path):
            data = config_io.load_file(config_dir, config_io.LOCAL_CONFIG_FILE)
        else:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data["appearance"] = name
        config_io.save_local(config_dir, data)
        return True, None
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Color field: swatch (native dialog) + hex entry + eyedropper (+ optional
# "use" toggle for the fields that may be left empty).
# ---------------------------------------------------------------------------

class ColorField:
    def __init__(self, panel, key, label="", optional=False):
        self.panel = panel
        self.key = key
        self.box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        self._loading = False
        self._hex = ""

        self.toggle = None
        if optional:
            self.toggle = Gtk.CheckButton.new()
            self.toggle.set_tooltip_text("apply this color")
            self.toggle.connect("toggled", self._on_toggle)
            self.box.pack_start(self.toggle, False, False, 0)

        self.swatch = Gtk.Button.new()
        self.swatch.set_size_request(44, 30)
        self.swatch.set_tooltip_text("open the color dialog")
        self.swatch.connect("clicked", lambda *_: panel.open_color_dialog(self))
        self.box.pack_start(self.swatch, False, False, 0)

        self.entry = Gtk.Entry.new()
        self.entry.set_width_chars(9)
        self.entry.set_max_width_chars(8)
        self.entry.connect("changed", self._on_entry_changed)
        self.entry.connect("button-press-event", panel.make_entry_press(self.key))
        self.entry.connect("focus-in-event",
                           lambda w, e: panel.on_entry_focus_in(w, e, self.key))
        self.entry.connect("focus-out-event",
                           lambda w, e: panel.on_entry_focus_out(w, e, self.key))
        self.box.pack_start(self.entry, True, True, 0)

        pick = Gtk.Button.new_with_label("Pick")
        pick.set_tooltip_text("pick a color from the screen")
        pick.connect("clicked", lambda *_: panel.pick_into(self))
        self.box.pack_start(pick, False, False, 0)

    # -- widget plumbing ------------------------------------------------
    def set_hex(self, value):
        self._loading = True
        self._hex = normalize_hex(value) or ""
        self.entry.set_text(self._hex)
        self._set_swatch(self._hex)
        if self.toggle is not None:
            self.toggle.handler_block_by_func(self._on_toggle)
            self.toggle.set_active(bool(self._hex))
            self.toggle.handler_unblock_by_func(self._on_toggle)
        self._set_enabled(bool(self._hex) or self.toggle is None
                          or not self.toggle.get_active())
        self._loading = False

    def get_hex(self):
        return self.entry.get_text().strip()

    def _set_swatch(self, value):
        h = normalize_hex(value)
        col = Gdk.RGBA()
        if h:
            col.red = int(h[1:3], 16) / 255.0
            col.green = int(h[3:5], 16) / 255.0
            col.blue = int(h[5:7], 16) / 255.0
            col.alpha = 1.0
        else:
            col.red = col.green = col.blue = 0.25
            col.alpha = 0.35
        for state in (Gtk.StateFlags.NORMAL, Gtk.StateFlags.PRELIGHT,
                      Gtk.StateFlags.ACTIVE):
            self.swatch.override_background_color(state, col)

    def _set_enabled(self, enabled):
        self.entry.set_sensitive(enabled)
        self.swatch.set_sensitive(enabled)
        for child in self.box.get_children():
            if child is not self.toggle:
                child.set_sensitive(enabled)

    def _on_toggle(self, *_):
        if self._loading:
            return
        if not self.toggle.get_active():
            self._hex = ""
            self.set_hex("")
        else:
            self._set_enabled(True)

    def _on_entry_changed(self, *_):
        if self._loading:
            return
        self._hex = normalize_hex(self.entry.get_text()) or ""
        self._set_swatch(self._hex)
        if self.toggle is not None:
            self.toggle.handler_block_by_func(self._on_toggle)
            self.toggle.set_active(bool(self._hex))
            self.toggle.handler_unblock_by_func(self._on_toggle)


# ---------------------------------------------------------------------------
# The editor window.
# ---------------------------------------------------------------------------

class ThemePanel:
    def __init__(self, monitor, x, y, frame_w, frame_h, win_h=EDITOR_H):
        self.monitor = monitor
        self.frame_w = frame_w
        self.frame_h = frame_h
        # Resolved window size: the controller adapts win_h so the window also
        # fits the smallest connected screen (screen height minus taskbar).
        self.win_w = EDITOR_W
        self.win_h = max(0, int(win_h or EDITOR_H))
        self.win_x = x
        self.win_y = y
        self.drag = False
        self.grab_root_x = 0.0
        self.grab_root_y = 0.0
        self.grab_x = 0.0
        self.grab_y = 0.0
        self.start_x = x
        self.start_y = y
        self._color_applied = False

        self.name, self.committed, self.radius, self.source = load_source(CONFIG_DIR)
        self.draft = dict(self.committed)
        self.editing = None       # key whose entry owns the keyboard
        self.preview_active = False  # a live (unsaved) preview is applied
        self._preview_file = None    # temp JSON handed to the worker
        self.status_label = None
        self.entries = {}         # text-entry key -> Gtk.Entry
        self.sliders = {}         # pct-key -> Gtk.Scale
        self.spins = {}           # key -> Gtk.SpinButton
        self.dropdowns = {}       # key -> Gtk.Button trigger
        self.dropdowns_vals = {}  # key -> current value id
        self.dropdown_opts = {}   # key -> [(label, value), ...]
        self.dropdown_open = None  # key whose POPUP menu is open right now
        self.child = None         # color dialog / dropdown popup while open
        self.toggles = {}         # check-key -> Gtk.CheckButton
        self.color_fields = {}    # color key -> ColorField
        self.active_field = None  # last focused color field (swatch strip target)
        self.pick = None          # {"overlay":…, "raw":…} while picking
        self._pick_poll_stop = False
        self._pick_poll_thread = None  # background KWin-cursor poll while picking

        # Absolute screen origin of the target monitor (drag clamp, X11).
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

        self.win = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
        self.win.set_title("Theme editor")
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
                    GtkLayerShell.set_monitor(self.win,
                                              display.get_monitor(monitor))
                GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.LEFT, x)
                GtkLayerShell.set_margin(self.win, GtkLayerShell.Edge.TOP, y)
            except Exception:
                pass
        else:
            self.win.move(x, y)

        self.build_ui()
        self.win.connect("destroy",
                         lambda *_: (self._revert_preview(),
                                     self._release_keyboard(), Gtk.main_quit()))
        self.win.connect("realize", self.on_realize)
        self.win.connect("button-press-event", self.on_press)
        self.win.connect("button-release-event", self.on_release)
        self.win.connect("motion-notify-event", self.on_motion)
        self.win.connect("key-press-event", self.on_key_press)

    def on_realize(self, widget):
        if not WAYLAND:
            try:
                widget.get_window().set_override_redirect(True)
            except Exception:
                pass

    def _raise_window(self, win):
        if not WAYLAND:
            try:
                window = win.get_window()
                if window is not None:
                    window.raise_()
            except Exception:
                pass

    def raise_above(self):
        self._raise_window(self.win)

    # -- build --------------------------------------------------------------
    def build_ui(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(_build_css().encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        root = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        root.get_style_context().add_class("panel")

        title = Gtk.EventBox.new()
        title.get_style_context().add_class("title")
        tbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        label = Gtk.Label.new("Theme editor")
        label.set_halign(Gtk.Align.CENTER)
        tbox.pack_start(label, True, True, 0)
        title.add(tbox)
        title.set_events(Gdk.EventMask.BUTTON_PRESS_MASK
                         | Gdk.EventMask.BUTTON_RELEASE_MASK
                         | Gdk.EventMask.POINTER_MOTION_MASK)
        title.connect("realize", lambda w: self._grab_cursor(w))
        root.pack_start(title, False, False, 0)

        info = Gtk.Label.new("Editing: %s  ·  source: %s" % (self.name, self.source))
        info.get_style_context().add_class("source")
        info.set_halign(Gtk.Align.CENTER)
        root.pack_start(info, False, False, 0)

        scrolled = Gtk.ScrolledWindow.new(None, None)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.NONE)
        content = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        content.set_margin_top(4)
        content.set_margin_bottom(4)
        content.set_margin_left(10)
        content.set_margin_right(10)

        content.pack_start(self._palette_row(), False, False, 0)
        content.pack_start(self._section("Basics"), False, False, 0)
        content.pack_start(self._row("Theme", self._dropdown("theme",
                             [("Light", "light"), ("Dark", "dark")])), False, False, 0)
        content.pack_start(self._row("Icon set", self._dropdown("icon_set",
                             [(s, s) for s in available_icon_sets(CONFIG_DIR)]
                             or [("dovora", "dovora")])), False, False, 0)
        content.pack_start(self._row("Corner radius",
                             self._spin("corner_radius", 0, 200, 5)), False, False, 0)

        content.pack_start(self._section("Icons"), False, False, 0)
        content.pack_start(self._row("Transparency · light",
                             self._slider("icon_transparency_light")), False, False, 0)
        content.pack_start(self._row("Transparency · dark",
                             self._slider("icon_transparency_dark")), False, False, 0)
        content.pack_start(self._row("Tint · light",
                             self._color("icon_color_light", optional=True)), False, False, 0)
        content.pack_start(self._row("Tint · dark",
                             self._color("icon_color_dark", optional=True)), False, False, 0)

        content.pack_start(self._section("Font"), False, False, 0)
        content.pack_start(self._row("Face", self._entry("font_face")), False, False, 0)
        content.pack_start(self._row("Color · light",
                             self._color("font_color_light")), False, False, 0)
        content.pack_start(self._row("Color · dark",
                             self._color("font_color_dark")), False, False, 0)
        content.pack_start(self._row("Transparency · light",
                             self._slider("font_transparency_light")), False, False, 0)
        content.pack_start(self._row("Transparency · dark",
                             self._slider("font_transparency_dark")), False, False, 0)
        glow_h = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        glow = self._toggle("chart_glow")
        glow.set_label("glow")
        glow.connect("toggled", self._on_glow_toggled)
        glow_h.pack_start(glow, False, False, 0)
        glow_h_row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        glow_h_row.pack_start(self._label("Shadow color", 150), False, False, 0)
        glow_h_row.pack_start(self._color("font_shadow_color",
                                          optional=True).box, True, True, 0)
        glow_h_row.pack_start(glow_h, False, False, 0)
        content.pack_start(glow_h_row, False, False, 0)
        content.pack_start(self._row("Shadow blur",
                             self._spin("font_shadow_blur", 0, 120, 1)), False, False, 0)

        content.pack_start(self._section("Background"), False, False, 0)
        content.pack_start(self._row("Color",
                             self._color("background_color")), False, False, 0)
        content.pack_start(self._row("Opacity",
                             self._slider("background_transparency")), False, False, 0)

        content.pack_start(self._section("Charts"), False, False, 0)
        content.pack_start(self._row("CPU", self._color("chart_cpu")), False, False, 0)
        content.pack_start(self._row("Memory", self._color("chart_memory")), False, False, 0)
        content.pack_start(self._row("Net down", self._color("chart_down")), False, False, 0)
        content.pack_start(self._row("Net up", self._color("chart_up")), False, False, 0)

        content.pack_start(self._section("Panel background"), False, False, 0)
        content.pack_start(self._row("Custom",
                             self._color("panel_color", optional=True)), False, False, 0)
        content.pack_start(self._row("Opacity",
                             self._slider("panel_transparency")), False, False, 0)
        content.pack_start(self._row("Gradient",
                             self._entry("panel_gradient")), False, False, 0)

        scrolled.add(content)
        root.pack_start(scrolled, True, True, 0)

        self.status_label = Gtk.Label.new("")
        self.status_label.set_visible(False)
        self.status_label.set_halign(Gtk.Align.CENTER)
        self.status_label.get_style_context().add_class("status")
        root.pack_start(self.status_label, False, False, 0)

        action_row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        for text, cls, cb in (("Cancel", "close", self.on_close),
                              ("Reset", "reset", self.on_reset),
                              ("Preview", "preview", self.on_preview),
                              ("Save", "save", self.on_save),
                              ("Save As…", "save", self.on_save_as)):
            btn = Gtk.Button.new_with_label(text)
            btn.get_style_context().add_class(cls)
            btn.connect("clicked", lambda *_, c=cb: c())
            action_row.pack_start(btn, True, True, 0)
        root.pack_start(action_row, False, False, 0)

        self.win.add(root)
        self.load_widgets(self.draft)

    def _label(self, text, width):
        lab = Gtk.Label.new(text)
        lab.get_style_context().add_class("field-label")
        lab.set_size_request(width, -1)
        lab.set_xalign(1.0)
        return lab

    def _section(self, text):
        lab = Gtk.Label.new(text.upper())
        lab.get_style_context().add_class("section")
        lab.set_halign(Gtk.Align.START)
        return lab

    def _row(self, label, widget):
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 6)
        row.get_style_context().add_class("row")
        lab = self._label(label, 150)
        if isinstance(widget, ColorField):
            widget = widget.box
        widget_box = widget if isinstance(widget, Gtk.Box) else Gtk.Box.new(
            Gtk.Orientation.HORIZONTAL, 4)
        if not isinstance(widget, Gtk.Box):
            widget_box.pack_start(widget, True, True, 0)
        row.pack_start(lab, False, False, 0)
        row.pack_start(widget_box, True, True, 0)
        return row

    def _palette_row(self):
        """One swatch per theme color; clicking copies into the active field."""
        row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        pal = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        row.pack_start(self._label("Palette", 150), False, False, 0)
        seen, colors = set(), []
        for key in ("font_color_light", "font_color_dark", "background_color",
                    "chart_cpu", "chart_memory", "chart_down", "chart_up",
                    "panel_color", "icon_color_dark", "icon_color_light"):
            h = hex_or(self.draft.get(key), "")
            if h and h not in seen:
                seen.add(h)
                colors.append(h)
        for h in colors:
            btn = Gtk.Button.new()
            rgba = Gdk.RGBA()
            rgba.red = int(h[1:3], 16) / 255.0
            rgba.green = int(h[3:5], 16) / 255.0
            rgba.blue = int(h[5:7], 16) / 255.0
            rgba.alpha = 1.0
            for state in (Gtk.StateFlags.NORMAL, Gtk.StateFlags.PRELIGHT,
                          Gtk.StateFlags.ACTIVE):
                btn.override_background_color(state, rgba)
            btn.set_size_request(26, 26)
            btn.set_tooltip_text(h)
            btn.connect("clicked", lambda *_, c=h: self._palette_click(c))
            pal.pack_start(btn, False, False, 0)
        row.pack_start(pal, True, True, 0)
        return row

    def _palette_click(self, color):
        if self.active_field is None:
            self.set_status("click a color field first, then a palette swatch")
            return
        self.active_field.set_hex(color)
        self.set_status("copied %s into %s" % (color, self.active_field.key))

    def _entry(self, key):
        entry = Gtk.Entry.new()
        entry.get_style_context().add_class("value-entry")
        entry.connect("button-press-event", self.make_entry_press(key))
        entry.connect("focus-in-event",
                      lambda w, e, k=key: self.on_entry_focus_in(w, e, k))
        entry.connect("focus-out-event",
                      lambda w, e, k=key: self.on_entry_focus_out(w, e, k))
        self.entries[key] = entry
        return entry

    def _slider(self, key):
        adj = Gtk.Adjustment.new(100, 0, 100, 1, 10, 0)
        scale = Gtk.Scale.new(Gtk.Orientation.HORIZONTAL, adj)
        scale.set_digits(0)
        scale.set_hexpand(True)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.sliders[key] = scale
        return scale

    def _spin(self, key, lo, hi, step):
        adj = Gtk.Adjustment.new(0, lo, hi, step, step * 5, 0)
        spin = Gtk.SpinButton.new(adj, step, 0)
        spin.set_numeric(True)
        self.spins[key] = spin
        return spin

    def _dropdown(self, key, options):
        trigger = Gtk.Button.new()
        trigger.set_relief(Gtk.ReliefStyle.NONE)
        trigger.set_tooltip_text("choose…")
        trigger.connect("clicked", lambda *_: self._open_menu(key))
        self.dropdowns[key] = trigger
        self.dropdown_opts[key] = options
        trigger.set_label(self._dropdown_label(key))
        return trigger

    def _dropdown_label(self, key):
        value = self.dropdowns_vals.get(key, "")
        labels = {v: l for l, v in self.dropdown_opts.get(key, ())}
        return ("%s  ▾" % labels.get(value, value)) if value else "▾"

    def _set_dropdown(self, key, value):
        self.dropdowns_vals[key] = value
        self.dropdowns[key].set_label(self._dropdown_label(key))

    def _open_menu(self, key):
        if getattr(self, "child", None) is not None:
            return
        options = self.dropdown_opts.get(key, ())
        if WAYLAND:
            win = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
            win.set_decorated(False)
            win.set_type_hint(Gdk.WindowTypeHint.UTILITY)
            win.set_keep_above(True)
        else:
            win = Gtk.Window.new(Gtk.WindowType.POPUP)
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        box.get_style_context().add_class("menu-popup")
        for label, value in options:
            item = Gtk.Button.new_with_label(label)
            item.get_style_context().add_class("menu-item")
            item.set_relief(Gtk.ReliefStyle.NONE)
            item.set_halign(Gtk.Align.FILL)
            item.connect("clicked", lambda *_, v=value: self._pick_option(key, v))
            box.pack_start(item, False, False, 0)
        win.add(box)
        win.set_resizable(False)
        win.set_size_request(210, -1)
        win.connect("realize", lambda w: self._menu_grab(w))
        win.connect("destroy", lambda *_: self._child_destroyed(win))
        win.connect("button-press-event", self._menu_press)
        self.child = win
        self.dropdown_open = key
        win.show_all()
        self._position_menu(key)
        win.present()

    def _position_menu(self, key):
        try:
            trigger = self.dropdowns.get(key)
            win = self.child
            if trigger is None or win is None:
                return
            ox, oy = trigger.translate_coordinates(self.win, 0, 0)
            w = 210
            h = max(win.get_allocated_height(),
                    4 + 26 * len(self.dropdown_opts.get(key, ())))
            px = self.win_x + ox
            py = self.win_y + oy + trigger.get_allocated_height()
            px = clamp(px, self.mon_ox, self.mon_ox + max(0, self.frame_w - w))
            py = clamp(py, self.mon_oy, self.mon_oy + max(0, self.frame_h - h))
            if WAYLAND:
                try:
                    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, px)
                    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, py)
                except Exception:
                    pass
            else:
                win.move(px, py)
        except Exception:
            pass

    def _menu_grab(self, win, *_):
        if not WAYLAND:
            try:
                Gdk.pointer_grab(win.get_window(), False,
                                 Gdk.EventMask.BUTTON_PRESS_MASK
                                 | Gdk.EventMask.BUTTON_RELEASE_MASK,
                                 None, None, Gdk.CURRENT_TIME)
            except Exception:
                pass

    def _menu_press(self, win, event):
        if not WAYLAND:
            try:
                gx, gy = win.get_position()
                inside = (gx <= event.x_root <= gx + win.get_allocated_width()
                          and gy <= event.y_root <= gy + win.get_allocated_height())
                if not inside:
                    self._close_menu()
            except Exception:
                pass
        return True

    def _pick_option(self, key, value):
        self._close_menu()
        self._set_dropdown(key, value)
        self.set_status("")

    def _close_menu(self):
        if not WAYLAND:
            try:
                Gdk.pointer_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass
        child = getattr(self, "child", None)
        self.child = None
        self.dropdown_open = None
        if child is not None:
            try:
                child.destroy()
            except Exception:
                pass
        self.raise_above()

    def _child_destroyed(self, win, *_):
        if getattr(self, "child", None) is win:
            self.child = None
            self.dropdown_open = None
        self.raise_above()

    def _close_child(self, win):
        """Destroy a floated child dialog (color picker, Save As…). Destroying
        fires the widget's "destroy" signal, which runs _child_destroyed and
        clears self.child/raise_above -- unlike _child_destroyed alone, which
        only clears the reference and leaves the dialog on screen."""
        try:
            win.destroy()
        except Exception:
            if getattr(self, "child", None) is win:
                self.child = None

    # -- child windows (Option A: the color dialog, dropdowns and the Save As
    #    dialog all float ABOVE the editor and the dismiss overlay, exactly
    #    like the editor itself, so nothing can render below or be eaten by
    #    the click-outside overlay).
    def _child_override_redirect(self, win):
        if not WAYLAND:
            try:
                win.set_keep_above(True)
                window = win.get_window()
                if window is not None:
                    window.set_override_redirect(True)
            except Exception:
                pass

    def _child_position(self, w, h):
        """(x, y) for a child dialog, centered on the editor.

        Centers the dialog on the editor's current top-left, then clamps to
        the WHOLE virtual desktop (self.desk_*) so the dialog follows the
        editor even when it is dragged to another monitor.
        """
        w = max(w or 0, 1)
        h = max(h or 0, 1)
        px = clamp(self.win_x + (self.win_w - w) // 2, self.desk_x0,
                   self.desk_x0 + max(0, self.desk_w - w))
        py = clamp(self.win_y + (self.win_h - h) // 2, self.desk_y0,
                   self.desk_y0 + max(0, self.desk_h - h))
        return px, py

    def _child_move(self, win):
        try:
            w = win.get_allocated_width() or 0
            h = win.get_allocated_height() or 0
            px, py = self._child_position(w, h)
            set_position(win, px, py)
        except Exception:
            pass

    def _raise_child(self, win):
        if WAYLAND:
            try:
                win.set_keep_above(True)
            except Exception:
                pass
        self._raise_window(win)

    # -- color dialog ------------------------------------------------------
    def open_color_dialog(self, field):
        if getattr(self, "child", None) is not None:
            return False
        h = normalize_hex(field.get_hex())
        rgba = Gdk.RGBA()
        if h:
            rgba.red = int(h[1:3], 16) / 255.0
            rgba.green = int(h[3:5], 16) / 255.0
            rgba.blue = int(h[5:7], 16) / 255.0
        dialog = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
        dialog.set_title("Pick a color")
        dialog.set_modal(True)
        dialog.set_resizable(False)
        dialog.set_default_size(400, 300)
        dialog.set_destroy_with_parent(False)
        if WAYLAND:
            try:
                GtkLayerShell.init_for_window(dialog)
                GtkLayerShell.set_layer(dialog, GtkLayerShell.Layer.OVERLAY)
                GtkLayerShell.set_keyboard_mode(
                    dialog, GtkLayerShell.KeyboardMode.ON_DEMAND)
                GtkLayerShell.set_anchor(dialog,
                                         GtkLayerShell.Edge.TOP, True)
                GtkLayerShell.set_anchor(dialog,
                                         GtkLayerShell.Edge.LEFT, True)
                GtkLayerShell.set_margin(dialog,
                                         GtkLayerShell.Edge.LEFT, 20)
                GtkLayerShell.set_margin(dialog,
                                         GtkLayerShell.Edge.TOP, 20)
            except Exception:
                pass
        else:
            # X11: float the dialog above the override-redirect editor and the
            # dismiss overlay exactly like the editor itself, otherwise it
            # renders behind them and cannot be used.
            dialog.set_keep_above(True)
            dialog.connect("realize", self._child_override_redirect)
        dialog.connect("destroy", lambda *_: self._child_destroyed(dialog))
        dialog.connect("key-press-event", self.on_key_press)
        color_w = Gtk.ColorChooserWidget.new()
        color_w.set_use_alpha(False)
        if h:
            color_w.set_rgba(rgba)
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 6)
        box.pack_start(color_w, True, True, 0)
        action_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 6)
        btn_ok = Gtk.Button.new_with_label("OK")
        btn_ok.get_style_context().add_class("save")
        btn_ok.connect("clicked",
                       lambda *_: self._color_dialog_ok(field, color_w))
        btn_cancel = Gtk.Button.new_with_label("Cancel")
        btn_cancel.get_style_context().add_class("close")
        btn_cancel.connect("clicked", lambda *_: self._close_child(dialog))
        action_box.pack_start(btn_cancel, True, True, 0)
        action_box.pack_start(btn_ok, True, True, 0)
        box.pack_start(action_box, False, False, 6)
        dialog.add(box)
        self.child = dialog
        GLib.idle_add(self._child_move, dialog)
        dialog.show_all()
        dialog.present()
        return False

    def _color_dialog_ok(self, field, color_w):
        rgba = color_w.get_rgba()
        field.set_hex(rgb_hex(
            int(round(rgba.red * 255)),
            int(round(rgba.green * 255)),
            int(round(rgba.blue * 255))))
        self.set_status("")
        if getattr(self, "child", None) is not None:
            try:
                self.child.destroy()
            except Exception:
                pass
        self.child = None

    def _toggle(self, key):
        toggle = Gtk.CheckButton.new_with_label("")
        self.toggles[key] = toggle
        return toggle

    def _color(self, key, optional=False):
        field = ColorField(self, key, optional=optional)
        self.color_fields[key] = field
        return field

    # -- load/collect the draft --------------------------------------------
    def load_widgets(self, draft):
        for key, entry in self.entries.items():
            entry.set_text(str(draft.get(key, "") or ""))
        for key, scale in self.sliders.items():
            scale.set_value(_f(draft.get(key), 0.0) * 100)
        for key, spin in self.spins.items():
            spin.set_value(_i(draft.get(key), 0))
        for key in self.dropdowns:
            options = self.dropdown_opts[key]
            values = [v for _, v in options]
            value = str(draft.get(key, "") or "")
            if value not in values:
                value = options[0][1]
            self.dropdowns_vals[key] = value
            self.dropdowns[key].set_label(self._dropdown_label(key))
        for key, toggle in self.toggles.items():
            toggle.set_active(bool(draft.get(key, False)))
        for key, field in self.color_fields.items():
            field.set_hex(draft.get(key, ""))
        if "font_color_light" in self.color_fields:
            self.active_field = self.color_fields["font_color_light"]

    def collect_draft(self):
        draft = dict(self.draft)
        for key, entry in self.entries.items():
            draft[key] = entry.get_text()
        for key, scale in self.sliders.items():
            draft[key] = scale.get_value() / 100.0
        for key, spin in self.spins.items():
            draft[key] = int(spin.get_value())
        for key in self.dropdowns:
            draft[key] = self.dropdowns_vals.get(key, "")
        for key, toggle in self.toggles.items():
            draft[key] = toggle.get_active()
        for key, field in self.color_fields.items():
            draft[key] = field.get_hex()
        return draft

    # -- keyboard grab / typing marker (weather_panel.py pattern) -----------
    def make_entry_press(self, key):
        def handler(entry, event, _key=key):
            self._begin_editing(_key)
            if not WAYLAND:
                try:
                    Gdk.keyboard_grab(self.win.get_window(), True,
                                      Gdk.CURRENT_TIME)
                except Exception:
                    pass
            GLib.idle_add(entry.select_region, 0, -1)
            return False
        return handler

    def on_entry_focus_in(self, entry, event, key):
        self._begin_editing(key)
        return False

    def on_entry_focus_out(self, entry, event, key):
        self._end_editing(key)
        return False

    def set_typing(self, flag):
        try:
            with open(SESSION_FILE) as fh:
                data = json.load(fh)
            if data.get("mode") != "theme":
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

    def _end_editing(self, key=None):
        if key is not None and self.editing != key:
            return
        self.editing = None
        self.set_typing(False)
        if not WAYLAND:
            try:
                Gdk.keyboard_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass

    def _release_keyboard(self, *_):
        self.editing = None
        if not WAYLAND:
            try:
                Gdk.keyboard_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass

    def _on_glow_toggled(self, *_):
        pass  # the shadow color field's own "use" toggle is the source of truth

    def set_status(self, msg):
        if self.status_label is None:
            return
        self.status_label.set_text(msg if len(msg) <= 56 else msg[:53] + "...")
        self.status_label.set_visible(bool(msg))

    # -- footer actions -------------------------------------------------------
    def on_close(self, *_):
        self._end_editing(self.editing)
        self._revert_preview()
        close_popup()
        Gtk.main_quit()

    def on_reset(self, *_):
        try:
            self._end_editing(self.editing)
            self._revert_preview()
            self.draft = dict(self.committed)
            self.load_widgets(self.draft)
            self.set_status("")
        except Exception as exc:
            self.set_status("Reset error: %s" % exc)

    def _apply_save(self, draft, radius):
        ok, msg = validate_draft(draft)
        if not ok:
            self.set_status(msg)
            return False
        if "'" in (str(draft.get("font_face", "")) or ""):
            self.set_status("font must not contain quotes")
            return False
        draft["font_face"] = (str(draft.get("font_face") or "")
                              .strip() or DEFAULT_FONT)
        ok, msg = save_inline_override(CONFIG_DIR, draft, radius)
        if not ok:
            self.set_status("Save failed: %s" % msg)
            return False
        return True

    def _spawn_preview_worker(self, argv):
        """Detached theme_preview.py run (never blocks the GTK loop)."""
        run([sys.executable, PREVIEW_SCRIPT] + argv)
        # After eww reload, re-map the editor above the re-created overlays
        GLib.timeout_add(1800, self._restack_after_reload)

    def _restack_after_reload(self, *_):
        if not WAYLAND:
            return False
        if not session_active():
            return False  # session already gone
        try:
            self.win.present()
            set_position(self.win, self.win_x, self.win_y)
            child = getattr(self, "child", None)
            if child is not None:
                child.present()
                self._child_move(child)
        except Exception:
            pass
        return False

    def on_preview(self, *_):
        """Apply the DRAFT to the live widget without saving.

        Writes the generated theme files + tinted icons from the in-memory
        draft via the detached worker, so the change shows on screen but is
        NOT persisted (config.local.yaml untouched) until Save is pressed.
        """
        self._end_editing(self.editing)
        draft = self.collect_draft()
        ok, msg = validate_draft(draft)
        if not ok:
            self.set_status(msg)
            return False
        if "'" in (str(draft.get("font_face", "")) or ""):
            self.set_status("font must not contain quotes")
            return False
        radius = self.spins["corner_radius"].get_value()
        try:
            appearance = normalize_appearance(draft)
        except Exception as exc:
            self.set_status("Preview failed: %s" % exc)
            return False
        try:
            fd, path = tempfile.mkstemp(prefix="wo-prev-", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(appearance, fh)
        except Exception as exc:
            self.set_status("Preview failed: %s" % exc)
            return False
        self._preview_file = path
        self.preview_active = True
        self._spawn_preview_worker(["--apply", path, "--radius", str(int(radius))])
        self.set_status("Previewing — Save keeps it, Cancel/Reset discards")
        return True

    def _revert_preview(self):
        """Undo a live preview (if any), restoring the committed look.

        Idempotent; the worker's --restore is a no-op when no preview marker
        exists. Called on Cancel / Reset / editor close (every exit path that
        does NOT persist the draft).
        """
        if not getattr(self, "preview_active", False):
            return
        self.preview_active = False
        self._spawn_preview_worker(["--restore"])
        GLib.timeout_add(1800, self._restack_after_reload)
        f = getattr(self, "_preview_file", None)
        if f:
            try:
                os.remove(f)
            except OSError:
                pass
            self._preview_file = None

    def on_save(self, *_):
        self._end_editing(self.editing)
        if not self._apply_save(self.collect_draft(), self.spins["corner_radius"].get_value()):
            return False
        self.preview_active = False  # persisted now; never revert
        f = getattr(self, "_preview_file", None)
        if f:
            try:
                os.remove(f)
            except OSError:
                pass
            self._preview_file = None
        self.committed = self.collect_draft()
        close_popup()
        Gtk.main_quit()
        return True

    def on_save_as(self, *_):
        self._end_editing(self.editing)
        draft = self.collect_draft()
        ok, msg = validate_draft(draft)
        if not ok:
            self.set_status(msg)
            return False
        if getattr(self, "child", None) is not None:
            return False

        # Custom child window (not a native Gtk.MessageDialog): a modal,
        # WM-managed dialog cannot work on top of the override-redirect editor
        # and grabs the modal keyboard grab, which froze the whole editor on
        # X11. This floats above the editor exactly like the color dialog, so
        # it behaves identically on X11 and Wayland (the two differ only in
        # how the window is made to float and how the entry gets the keyboard).
        dialog = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
        dialog.set_title("Save theme as…")
        dialog.set_resizable(False)
        dialog.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        dialog.set_decorated(False)
        if WAYLAND:
            try:
                GtkLayerShell.init_for_window(dialog)
                GtkLayerShell.set_layer(dialog, GtkLayerShell.Layer.OVERLAY)
                GtkLayerShell.set_keyboard_mode(
                    dialog, GtkLayerShell.KeyboardMode.ON_DEMAND)
                GtkLayerShell.set_anchor(dialog, GtkLayerShell.Edge.TOP, True)
                GtkLayerShell.set_anchor(dialog, GtkLayerShell.Edge.LEFT, True)
            except Exception:
                pass
        else:
            # X11: float above the override-redirect editor (and the dismiss
            # overlay) like the editor itself; the keyboard is grabbed below
            # so the name entry still gets the typed keys.
            dialog.set_keep_above(True)
            dialog.connect("realize", self._child_override_redirect)

        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
        box.set_margin_start(14)
        box.set_margin_end(14)
        box.set_margin_top(14)
        box.set_margin_bottom(14)

        label = Gtk.Label.new("Save theme as…")
        label.set_halign(Gtk.Align.START)
        box.pack_start(label, False, False, 0)

        entry = Gtk.Entry.new()
        entry.set_placeholder_text("theme-name (rose-gold, my-pastel, …)")
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)

        action_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 6)
        btn_cancel = Gtk.Button.new_with_label("Cancel")
        btn_cancel.get_style_context().add_class("close")
        btn_cancel.connect("clicked", lambda *_: self._close_child(dialog))
        btn_ok = Gtk.Button.new_with_label("Save As")
        btn_ok.get_style_context().add_class("save")
        btn_ok.set_can_default(True)
        btn_ok.connect("clicked",
                       lambda *_: self._save_as_ok(dialog, entry, draft))
        dialog.set_default(btn_ok)
        action_box.pack_start(btn_cancel, True, True, 0)
        action_box.pack_start(btn_ok, True, True, 0)
        box.pack_start(action_box, False, False, 6)
        dialog.add(box)

        def on_destroy(win, *_):
            # Release the X11 keyboard grab the name entry held, then treat it
            # as any other child (clear self.child, re-raise the editor).
            if not WAYLAND:
                try:
                    Gdk.keyboard_ungrab(Gdk.CURRENT_TIME)
                except Exception:
                    pass
            self._child_destroyed(win)

        dialog.connect("destroy", on_destroy)
        dialog.connect("key-press-event", self.on_key_press)
        self.child = dialog
        dialog.show_all()
        GLib.idle_add(self._child_move, dialog)
        dialog.present()
        entry.grab_focus()
        self._grab_dialog_keyboard(dialog)
        return False

    def _grab_dialog_keyboard(self, dialog):
        """Give the Save As name entry the keyboard.

        X11: override-redirect windows never receive WM focus, so the entry
        only gets keystrokes through Gdk.keyboard_grab (the same mechanism the
        editor's own fields use). Wayland: no global grab exists, so focus is
        just moved into the entry. The dialog may not be realized yet when this
        runs, so it retries on idle until it is.
        """
        if WAYLAND:
            return
        attempts = [0]

        def do_grab():
            try:
                window = dialog.get_window()
                if window is None and attempts[0] < 20:
                    attempts[0] += 1
                    return True
                if window is not None and not WAYLAND:
                    Gdk.keyboard_grab(window, True, Gdk.CURRENT_TIME)
            except Exception:
                pass
            return False

        GLib.idle_add(do_grab)

    def _save_as_ok(self, dialog, entry, draft):
        name = entry.get_text().strip()
        if not name:
            self.set_status("Give the theme a name")
            return
        if self.child is dialog:
            self.child = None
        ok, msg = save_as_theme(CONFIG_DIR, name, draft)
        if ok:
            close_popup()
            Gtk.main_quit()
        else:
            self.set_status(msg)
            dialog.destroy()

    # -- on-screen color picker ---------------------------------------------
    def pick_into(self, field):
        self._end_editing(self.editing)
        self.pick_field = field
        if WAYLAND:
            self._pick_wayland()
        else:
            self._pick_x11()

    def _pick_x11(self):
        self._color_applied = False
        screen = Gdk.Screen.get_default()
        root = screen.get_root_window()
        w, h = root.get_width(), root.get_height()
        if w <= 0 or h <= 0:
            self.set_status("screen capture failed")
            return
        try:
            pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, w, h)
        except Exception:
            pixbuf = None
        if pixbuf is None:
            self.set_status("screen capture failed")
            self.win.show_all()
            return
        self.pick = {"raw": raw_pixbuf(pixbuf),
                     "bg": pixbuf,
                     "overlay": None,
                     "x": 0, "y": 0, "rgb": None}
        self.win.hide()
        overlay = Gtk.Window.new(Gtk.WindowType.POPUP)
        overlay.set_app_paintable(True)
        visual = Gdk.Screen.get_default().get_rgba_visual()
        if visual is not None:
            overlay.set_visual(visual)
        overlay.set_size_request(w, h)
        overlay.move(0, 0)
        da = Gtk.DrawingArea.new()
        da.set_size_request(w, h)
        da.set_events(Gdk.EventMask.BUTTON_PRESS_MASK
                      | Gdk.EventMask.BUTTON_RELEASE_MASK
                      | Gdk.EventMask.POINTER_MOTION_MASK)
        overlay.add(da)
        overlay.connect("realize", self._pick_realize)
        da.connect("draw", self._pick_draw)
        da.connect("motion-notify-event", self._pick_motion)
        da.connect("button-release-event", self._pick_release)
        overlay.show_all()
        overlay.present()
        self.pick["overlay"] = overlay
        da.queue_draw()

    def _pick_realize(self, overlay, *_):
        try:
            Gdk.pointer_grab(
                overlay.get_window(), False,
                Gdk.EventMask.BUTTON_PRESS_MASK
                | Gdk.EventMask.BUTTON_RELEASE_MASK
                | Gdk.EventMask.POINTER_MOTION_MASK,
                None, Gdk.Cursor.new_for_display(
                    Gdk.Display.get_default(), Gdk.CursorType.CROSSHAIR),
                Gdk.CURRENT_TIME)
        except Exception:
            pass

    def _pick_sample(self, x, y):
        """RGB at root (x, y), clamped to the captured surface."""
        data = self.pick
        if data is None or data.get("raw") is None:
            return None
        pixels, rowstride, nch, w, h = data["raw"]
        return pixel_color_at(pixels, rowstride, nch,
                              clamp(int(x), 0, w - 1),
                              clamp(int(y), 0, h - 1), w, h)

    def _pick_motion(self, da, event):
        if not self.pick:
            return False
        if WAYLAND:
            # The layer-shell overlay sits on the editor's monitor and DOES get
            # motion events (no grab needed while the pointer is over it). Map
            # the surface-local coords to the captured (global) pixbuf space via
            # the monitor origin so the magnifier tracks the pointer live like
            # on X11. The KWin-cursor poll remains a fallback only when no
            # motion event is arriving (see _pick_apply_cursor).
            x = int(event.x) + self.mon_ox
            y = int(event.y) + self.mon_oy
            self.pick["x"], self.pick["y"] = x, y
            self.pick["rgb"] = self._pick_sample(x, y)
            self.pick["motion_ts"] = time.monotonic()
            da.queue_draw()
            return False
        self.pick["x"] = int(event.x_root)
        self.pick["y"] = int(event.y_root)
        rgb = self._pick_sample(self.pick["x"], self.pick["y"])
        self.pick["rgb"] = rgb
        da.queue_draw()
        return False

    def _pick_draw(self, da, cr):
        bg = self.pick.get("bg") if self.pick else None
        if bg is not None:
            try:
                Gdk.cairo_set_source_pixbuf(
                    cr, bg, 0, 0)
                cr.rectangle(0, 0, da.get_allocated_width(),
                             da.get_allocated_height())
                cr.fill()
            except Exception:
                pass
        rgb = self.pick.get("rgb") if self.pick else None
        if rgb is None:
            # Draw a neutral gray placeholder with "Move to pick" text
            cr.set_source_rgb(0.2, 0.2, 0.2)
            cr.rectangle(12, 12, 110, 34)
            cr.fill()
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.rectangle(12, 12, 110, 34)
            cr.stroke()
            cr.set_source_rgb(0.8, 0.8, 0.8)
            try:
                cr.select_font_face(
                    "Sans",
                    getattr(cairo, "FONT_SLANT_NORMAL", 0) if cairo else 0,
                    getattr(cairo, "FONT_WEIGHT_BOLD", 1) if cairo else 1)
            except Exception:
                pass
            cr.set_font_size(11)
            cr.move_to(20, 34)
            cr.show_text("Move mouse to preview")
            return False
        r, g, b = rgb
        cx = clamp(self.pick["x"], 10, da.get_allocated_width() - 10)
        cy = clamp(self.pick["y"], 10, da.get_allocated_height() - 10)
        # Color preview swatch (large, clearly visible)
        cr.set_source_rgb(r / 255.0, g / 255.0, b / 255.0)
        cr.rectangle(12, 12, 140, 40)
        cr.fill()
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(12, 12, 140, 40)
        cr.set_line_width(2)
        cr.stroke()
        ink = (0, 0, 0) if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else (255, 255, 255)
        cr.set_source_rgb(*(v / 255.0 for v in ink))
        try:
            cr.select_font_face(
                "Sans",
                getattr(cairo, "FONT_SLANT_NORMAL", 0) if cairo else 0,
                getattr(cairo, "FONT_WEIGHT_BOLD", 1) if cairo else 1)
        except Exception:
            pass
        cr.set_font_size(14)
        cr.move_to(20, 30)
        cr.show_text("#%02x%02x%02x" % rgb)
        cr.set_font_size(10)
        cr.move_to(20, 46)
        cr.show_text("Release to apply")
        # magnified viewfinder around the cursor: 16px logical square, 6x zoom
        ox, oy = cx - 48, cy - 48
        px, py = clamp(self.pick["x"] - 8, 0, da.get_allocated_width() - 1), \
                 clamp(self.pick["y"] - 8, 0, da.get_allocated_height() - 1)
        for fy in range(16):
            for fx in range(16):
                s = (px + fx, py + fy)
                # pure sample -> approximate neighbors by same pixel color
                q = self._pick_sample(*s)
                if q:
                    cr.set_source_rgb(q[0] / 255.0, q[1] / 255.0, q[2] / 255.0)
                    cr.rectangle(ox + fx * 6, oy + fy * 6, 6, 6)
                    cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.rectangle(ox - 1, oy - 1, 98, 98)
        cr.stroke()
        return False

    def _pick_release(self, da, event):
        if not self.pick or event.button != 1:
            return False
        if self._color_applied:
            return False
        if WAYLAND:
            # Motion events on the overlay keep the tracked position live; use
            # it directly (no blocking kde_cursor() call on click). If no motion
            # ever arrived, fall back to the polled KWin cursor once.
            rgb = self.pick.get("rgb")
            if not self.pick.get("motion_ts", 0):
                pos = self._wa_kde_cursor()
                if pos:
                    rgb = self._pick_sample(int(pos[0]), int(pos[1]))
        else:
            rgb = self._pick_sample(event.x_root, event.y_root)
        field = getattr(self, "pick_field", None)
        self._pick_finish()
        if rgb is not None and field is not None:
            field.set_hex(rgb_hex(*rgb))
            self.set_status("")
        self._color_applied = True
        return False

    def _pick_finish(self):
        self._stop_pick_poll()
        try:
            Gdk.pointer_ungrab(Gdk.CURRENT_TIME)
        except Exception:
            pass
        overlay = self.pick["overlay"] if self.pick else None
        self.pick = None
        self._color_applied = False
        if overlay is not None:
            overlay.destroy()
        try:
            self.win.show_all()
            self.win.present()
        except Exception:
            pass
        self.raise_above()

    def _pick_wayland(self):
        """Best-effort capture flow (no global grab on Wayland).

        The screen is captured once (spectacle / grim / gnome-screenshot), a
        full-screen layer-shell OVERLAY shows the frozen capture with a live
        magnifier + hex readout, and the GLOBAL cursor is polled through the KDE
        KWin scripting API (workarea.kde_cursor) because without a pointer grab
        the overlay gets no reliable pointer-motion events. On click the color
        under the polled cursor is applied and the editor reappears. Without the
        tools or a KDE cursor API it degrades to the swatch/hex entry.
        """
        tool = None
        for candidate in ("spectacle", "grim", "gnome-screenshot"):
            if subprocess.run(["which", candidate], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                tool = candidate
                break
        if tool is None:
            self.set_status("screen pick needs X11 (or KDE + grim) here; "
                            "use the swatch or hex entry")
            return
        self._color_applied = False
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        try:
            if tool == "spectacle":
                ok = subprocess.run(["spectacle", "--background", "--fullscreen",
                                     "--nonotify", "--output", tmp.name],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL).returncode == 0
            elif tool == "grim":
                ok = subprocess.run(["grim", tmp.name], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL).returncode == 0
            else:
                ok = subprocess.run(["gnome-screenshot", "-f", tmp.name],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL).returncode == 0
            if not ok:
                raise OSError("screenshot failed")
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(tmp.name)
        except Exception as exc:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            self.set_status("screen pick failed: %s" % exc)
            return
        screen = Gdk.Screen.get_default()
        w, h = screen.get_width(), screen.get_height()
        self.pick = {"raw": raw_pixbuf(pixbuf),
                     "bg": pixbuf,
                     "overlay": None, "x": 0, "y": 0, "rgb": None,
                     "motion_ts": 0}
        self.win.hide()
        overlay = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
        overlay.set_decorated(False)
        overlay.set_app_paintable(True)
        overlay.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        overlay.set_keep_above(True)
        if WAYLAND:
            try:
                GtkLayerShell.init_for_window(overlay)
                GtkLayerShell.set_layer(overlay, GtkLayerShell.Layer.OVERLAY)
                GtkLayerShell.set_anchor(overlay, GtkLayerShell.Edge.TOP, True)
                GtkLayerShell.set_anchor(overlay, GtkLayerShell.Edge.LEFT, True)
                GtkLayerShell.set_anchor(overlay, GtkLayerShell.Edge.RIGHT, True)
                GtkLayerShell.set_anchor(overlay, GtkLayerShell.Edge.BOTTOM, True)
                display = Gdk.Display.get_default()
                if display is not None and self.monitor < display.get_n_monitors():
                    GtkLayerShell.set_monitor(
                        overlay, display.get_monitor(self.monitor))
                GtkLayerShell.set_keyboard_mode(
                    overlay, GtkLayerShell.KeyboardMode.ON_DEMAND)
            except Exception:
                pass
        da = Gtk.DrawingArea.new()
        da.set_size_request(w, h)
        da.set_events(Gdk.EventMask.BUTTON_PRESS_MASK
                      | Gdk.EventMask.BUTTON_RELEASE_MASK
                      | Gdk.EventMask.POINTER_MOTION_MASK)
        overlay.add(da)
        da.connect("draw", self._pick_draw)
        da.connect("motion-notify-event", self._pick_motion)
        da.connect("button-release-event", self._pick_release)
        overlay.connect("key-press-event", self.on_key_press)
        overlay.show_all()
        overlay.present()
        self.pick["overlay"] = overlay
        da.queue_draw()
        # Poll the KWin cursor on a background thread so the magnifier/readout
        # follow the pointer without freezing the GTK main loop (kde_cursor()
        # blocks on subprocess + sleeps). Updates are applied on the main loop.
        self._start_pick_poll()

    def _wa_kde_cursor(self):
        """Global pointer (x, y) via the KDE KWin scripting API, or None."""
        try:
            import workarea as _wa
            return _wa.kde_cursor()
        except Exception:
            return None

    def _start_pick_poll(self):
        self._stop_pick_poll()
        self._pick_poll_stop = False
        self._pick_poll_thread = threading.Thread(
            target=self._pick_poll_worker, daemon=True)
        self._pick_poll_thread.start()

    def _pick_poll_worker(self):
        """Background thread: poll the KWin cursor and ship updates to the
        main loop. Running kde_cursor() (which blocks on subprocess + sleeps)
        here keeps the GTK main loop free to redraw the magnifier live."""
        while not self._pick_poll_stop:
            pos = self._wa_kde_cursor()
            if self._pick_poll_stop:
                break
            if pos and self.pick is not None:
                x, y = int(pos[0]), int(pos[1])
                if (x != self.pick.get("x") or y != self.pick.get("y")
                        or self.pick.get("rgb") is None):
                    GLib.idle_add(self._pick_apply_cursor, x, y)
            time.sleep(0.05)

    def _pick_apply_cursor(self, x, y):
        """Main-thread: update the tracked cursor position + rgb and redraw.

        Only applied when the overlay is NOT receiving live motion events (the
        poll is a fallback), so the fast motion-driven tracking is never
        overwritten by the slower KWin-cursor poll (which would stutter).
        """
        if self.pick is None:
            return False
        if self.pick.get("motion_ts", 0) and \
                time.monotonic() - self.pick["motion_ts"] < 0.3:
            return False
        self.pick["x"], self.pick["y"] = x, y
        self.pick["rgb"] = self._pick_sample(x, y)
        try:
            da = self.pick["overlay"].get_children()[0]
            da.queue_draw()
        except Exception:
            pass
        return False

    def _stop_pick_poll(self):
        self._pick_poll_stop = True
        thr = getattr(self, "_pick_poll_thread", None)
        if thr is not None:
            thr.join(timeout=0.5)
            self._pick_poll_thread = None

    def tick(self):
        if not session_active():
            # While picking the editor is hidden and the full-screen picker
            # overlay owns the click, so losing the session there (e.g. a click
            # that for a moment lands on a dismiss layer) must neither quit the
            # editor nor lose the color being picked. The picker itself cancels
            # on ESC / its own click; only close when truly idle.
            if self.pick is not None:
                return True
            self._revert_preview()
            Gtk.main_quit()
            return False
        child = getattr(self, "child", None)
        if child is not None:
            self._raise_child(child)
        else:
            self.raise_above()
        # Do NOT call _restack_after_reload() every tick: it re-asserts the
        # layer-shell margins (set_position / _child_move) on the editor and
        # any open child dialog (Save As) each 250 ms, which on Wayland/KDE
        # keeps re-placing the window so the modal visibly trembles/jumps -- and
        # its win.present() re-shows the editor while the picker has hidden it.
        # The re-stack is only needed once, right after an `eww reload`
        # (preview), and is already scheduled as a one-shot from
        # _spawn_preview_worker / _revert_preview.
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

    # -- dragging (same mechanics as weather_panel.py / gap_ctl.py) ----------
    def on_press(self, widget, event):
        if event.button != 1 or event.y > TITLE_H:
            return False
        if getattr(self, "child", None) is not None:
            try:
                self.child.hide()
            except Exception:
                pass
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
                        None, None, Gdk.CURRENT_TIME)
            except Exception:
                pass
        return False

    def on_motion(self, widget, event):
        if not self.drag:
            return False
        if WAYLAND:
            nx = self.win_x + int(event.x - self.grab_x)
            ny = self.win_y + int(event.y - self.grab_y)
            nx = max(0, min(nx, max(0, self.frame_w - EDITOR_W)))
            ny = max(0, min(ny, max(0, self.frame_h - EDITOR_H)))
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
            if self.dropdown_open is not None:
                self._position_menu(self.dropdown_open)
            elif getattr(self, "child", None) is not None:
                # A dialog (Save As / color) follows the editor during the drag.
                self._child_move(self.child)
            elif self.pick is not None and self.pick.get("overlay") is not None:
                self._child_move(self.pick["overlay"])
        return False

    def on_release(self, widget, event):
        if event.button != 1:
            return False
        self.drag = False
        if getattr(self, "child", None) is not None:
            try:
                self.child.show()
                self.raise_above()
            except Exception:
                pass
        if not WAYLAND:
            try:
                Gdk.pointer_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass
        return False


    def on_key_press(self, widget, event):
        if event.keyval != Gdk.KEY_Escape:
            return False
        if self.pick is not None:
            self._pick_finish()
            return True
        if getattr(self, "child", None) is not None:
            child = self.child
            self.child = None
            try:
                child.destroy()
            except Exception:
                pass
            self.raise_above()
            return True
        self.on_close()
        return True


def _build_css():
    return """
    * { outline: none; }
    .panel {
      background-color: rgba(17, 17, 22, 0.98);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 12px;
    }
    .title {
      font-size: 14px;
      font-weight: bold;
      color: #ffffff;
      padding: 6px 4px 2px 4px;
    }
    .source {
      font-size: 10px;
      color: rgba(255, 255, 255, 0.55);
      padding: 0 4px 4px 4px;
    }
    .section {
      font-size: 11px;
      font-weight: bold;
      color: rgba(255, 255, 255, 0.45);
      padding: 8px 2px 2px 2px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.12);
      margin-bottom: 2px;
    }
    .row { margin: 1px 0; }
    .field-label {
      font-size: 12px;
      color: rgba(255, 255, 255, 0.85);
    }
    entry {
      font-size: 13px;
      color: #ffffff;
      background-color: rgba(255, 255, 255, 0.08);
      border-radius: 6px;
      padding: 2px 6px;
    }
    entry:focus { background-color: rgba(255, 255, 255, 0.16); }
    button {
      min-height: 26px;
      min-width: 28px;
      margin: 2px;
      border: none;
      border-radius: 6px;
      background-color: rgba(255, 255, 255, 0.10);
      color: #ffffff;
      font-size: 13px;
      padding: 0 8px;
    }
    button:hover { background-color: rgba(255, 255, 255, 0.2); }
    button:active { background-color: rgba(255, 255, 255, 0.3); }
    button.close { background-color: rgba(204, 0, 0, 0.25); }
    button.close:hover { background-color: rgba(204, 0, 0, 0.4); }
    button.save { background-color: rgba(78, 154, 6, 0.25); }
    button.save:hover { background-color: rgba(78, 154, 6, 0.4); }
    button.reset { background-color: rgba(200, 150, 0, 0.25); }
    button.reset:hover { background-color: rgba(200, 150, 0, 0.4); }
    button.preview { background-color: rgba(69, 133, 136, 0.28); }
    button.preview:hover { background-color: rgba(69, 133, 136, 0.45); }
    scale trough { min-height: 4px; }
    .status {
      font-size: 11px;
      color: rgba(255, 120, 120, 0.95);
      margin: 2px;
    }
    """


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
            return json.load(fh).get("mode") == "theme"
    except FileNotFoundError:
        return False
    except Exception:
        return True  # átmeneti olvasási hiba: tartsa nyitva az editort


def set_position(win, x, y):
    if WAYLAND:
        try:
            GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, x)
            GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, y)
        except Exception:
            pass
    else:
        win.move(x, y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--monitor", type=int, default=0)
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--frame-w", type=int, default=0)
    ap.add_argument("--frame-h", type=int, default=0)
    ap.add_argument("--win-h", type=int, default=EDITOR_H)
    args = ap.parse_args()

    if not session_active():
        sys.exit(0)

    panel = ThemePanel(args.monitor, args.x, args.y,
                       args.frame_w, args.frame_h, args.win_h)
    panel.win.show_all()
    panel.win.present()
    GLib.timeout_add(250, panel.tick)
    Gtk.main()


if __name__ == "__main__":
    main()