"""Tests for the raindrop layer's pure logic (scripts/core/rain.py, v5.0.0).

The GTK layer itself is exercised by `./rain.py <dir> --selftest` (it needs a
real display to verify click-through); everything tested here is the geometry,
timing, CSS generation and config/cache reading that decides what the layer
shows, so it must all be correct headless and deterministic.
"""

import json
import re

import pytest

import rain


# --- clamping / coercion -----------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (24, 24), ("24", 24), (0, 0), (120, 120),
    (121, 120), (-5, 0), ("60", 60),
    (None, 24), ("nonsense", 24), (12.7, 12),
])
def test_clamp_count(raw, expected):
    assert rain.clamp_count(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    (1, 1), (5, 5), (10, 10), (0, 1), (11, 10), (-3, 1),
    (None, 5), ("fast", 5), ("7", 7),
])
def test_clamp_speed(raw, expected):
    assert rain.clamp_speed(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    (0.0, 0.0), (1.0, 1.0), (0.35, 0.35),
    (1.5, 1.0), (-0.2, 0.0), ("0.5", 0.5), (None, 0.35), ("x", 0.35),
])
def test_clamp_opacity(raw, expected):
    assert rain.clamp_opacity(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw,expected", [
    (True, True), (False, False), ("true", True), ("False", False),
    ("TRUE", True), ("1", True), ("0", False), ("yes", True), ("on", True),
    ("off", False), ("no", False), ("", True),   # unknown -> the default
])
def test_as_bool_true_default(raw, expected):
    assert rain.as_bool(raw, True) is expected


@pytest.mark.parametrize("raw,expected", [
    (True, True), (False, False), ("false", False), ("0", False),
    (None, False), ("maybe", False), (12, False), ("", False),
])
def test_as_bool_false_default(raw, expected):
    assert rain.as_bool(raw, False) is expected


def test_as_bool_default_used_for_unknown():
    assert rain.as_bool("garbage", False) is False
    assert rain.as_bool("garbage", True) is True
    assert rain.as_bool(None, False) is False


# --- speed -> duration mapping ----------------------------------------------

def test_speed_endpoints_match_the_documented_range():
    # config.yaml documents ~2.4s at speed 1 down to ~0.55s at speed 10.
    assert rain.base_duration(1) == pytest.approx(2.4)
    assert rain.base_duration(10) == pytest.approx(0.55)


def test_faster_speed_means_shorter_duration():
    durations = [rain.base_duration(s) for s in range(1, 11)]
    assert durations == sorted(durations, reverse=True)


def test_base_duration_is_monotonic_and_linear():
    # Linear interpolation means equal speed steps shorten by equal amounts.
    steps = [rain.base_duration(s) - rain.base_duration(s + 1) for s in range(1, 10)]
    assert all(step == pytest.approx(steps[0]) for step in steps)


def test_base_duration_clamps_out_of_range_speed():
    assert rain.base_duration(0) == rain.base_duration(1)
    assert rain.base_duration(99) == rain.base_duration(10)


# --- droplet layout ----------------------------------------------------------

def test_plan_drops_count_matches_request():
    drops, _travel = rain.plan_drops(24, 5, 1920, 1080)
    assert len(drops) == 24


def test_plan_drops_zero_count_yields_nothing():
    drops, _travel = rain.plan_drops(0, 5, 1920, 1080)
    assert drops == []


def test_plan_drops_is_deterministic():
    # The seeded RNG is what makes the rain reproducible (and testable).
    a, _ = rain.plan_drops(30, 5, 1920, 1080)
    b, _ = rain.plan_drops(30, 5, 1920, 1080)
    assert a == b


def test_plan_drops_stays_inside_the_monitor_width():
    drops, _travel = rain.plan_drops(120, 5, 1920, 1080)
    assert all(0 <= d["x"] <= 1920 - rain.DROPLET_W for d in drops)


def test_plan_drops_negative_delays_spread_the_rain():
    # A POSITIVE delay would leave every drop bunched at the start line and
    # then stop; negative delays start each drop mid-flight.
    drops, _travel = rain.plan_drops(40, 5, 1920, 1080)
    assert all(d["delay"] < 0 for d in drops)
    # The delays must actually differ, otherwise the rain falls in lockstep.
    assert len({d["delay"] for d in drops}) > 20


def test_plan_drops_delay_magnitude_below_duration():
    # A delay more negative than the duration would wrap to a later iteration,
    # which is fine, but a zero-ish delay means the drop never really staggers.
    drops, _travel = rain.plan_drops(24, 5, 1920, 1080)
    for drop in drops:
        assert drop["duration"] + drop["delay"] > 0


def test_plan_drops_sorted_by_x_for_stable_css():
    drops, _travel = rain.plan_drops(40, 5, 1920, 1080)
    assert [d["x"] for d in drops] == sorted(d["x"] for d in drops)


def test_plan_drops_indices_are_the_original_sequence():
    # Sorting reorders the x positions, but the CSS class names must stay
    # unique, or two drops would collapse onto one rule.
    drops, _travel = rain.plan_drops(40, 5, 1920, 1080)
    assert sorted(d["index"] for d in drops) == list(range(40))


def test_plan_drops_travel_covers_the_screen_plus_overscan():
    _drops, travel = rain.plan_drops(10, 5, 1920, 1080)
    assert travel == 1080 + rain.OVERSCAN


def test_plan_drops_faster_speed_gives_shorter_durations():
    slow, _ = rain.plan_drops(20, 1, 1920, 1080)
    fast, _ = rain.plan_drops(20, 10, 1920, 1080)
    avg_slow = sum(d["duration"] for d in slow) / len(slow)
    avg_fast = sum(d["duration"] for d in fast) / len(fast)
    assert avg_fast < avg_slow


def test_plan_drops_includes_some_streaks():
    # A little variation in drop length stops the rain looking like a grid.
    drops, _travel = rain.plan_drops(60, 5, 1920, 1080)
    heights = {d["height"] for d in drops}
    assert len(heights) > 1
    assert rain.DROPLET_H in heights


def test_plan_drops_handles_degenerate_monitor_size():
    drops, travel = rain.plan_drops(5, 5, 0, 0)
    assert len(drops) == 5
    assert travel > 0


# --- CSS generation ----------------------------------------------------------

def test_build_css_defines_the_keyframes():
    drops, travel = rain.plan_drops(10, 5, 1920, 1080)
    css = rain.build_css(drops, travel, 0.35)
    assert "@keyframes raindrop" in css
    # The fall has to start above the top edge and end below the bottom one,
    # otherwise drops pop in and out.
    assert "margin-top: -%dpx" % rain.DROPLET_H in css
    assert "margin-top: %dpx" % travel in css


def test_build_css_has_one_rule_per_drop():
    drops, travel = rain.plan_drops(12, 5, 1920, 1080)
    css = rain.build_css(drops, travel, 0.4)
    for drop in drops:
        assert ".rain-drop-%d {" % drop["index"] in css


def test_build_css_no_drops_is_still_valid():
    css = rain.build_css([], 1140, 0.35)
    assert "@keyframes raindrop" in css
    assert "rain-drop-0" not in css


def test_build_css_uses_the_tint():
    drops, travel = rain.plan_drops(5, 5, 1920, 1080)
    css = rain.build_css(drops, travel, 0.5, tint="#ff8800")
    assert "background-color: #ff8800" in css


def test_build_css_animates_margin_top_only():
    # GTK3 3.24.41 has no CSS `transform` / `top` property (measured:
    # "No property named 'transform'"), so the animation MUST be margin-top.
    drops, travel = rain.plan_drops(5, 5, 1920, 1080)
    css = rain.build_css(drops, travel, 0.35)
    assert "transform" not in css
    assert re.search(r"animation-name:\s*raindrop", css)


def test_build_css_sets_linear_and_infinite():
    drops, travel = rain.plan_drops(5, 5, 1920, 1080)
    css = rain.build_css(drops, travel, 0.35)
    assert "animation-timing-function: linear" in css
    assert "animation-iteration-count: infinite" in css


def test_build_css_applies_opacity_to_every_drop():
    drops, travel = rain.plan_drops(6, 5, 1920, 1080)
    css = rain.build_css(drops, travel, 0.250, tint="#ffffff")
    assert css.count("opacity: 0.250") == len(drops)


def test_build_css_carries_the_negative_delay():
    drops, travel = rain.plan_drops(4, 5, 1920, 1080)
    css = rain.build_css(drops, travel, 0.35)
    for drop in drops:
        assert "animation-delay: %.3fs" % drop["delay"] in css


# --- settings / cache reading -----------------------------------------------

def _write_rain_config(config_dir, body):
    (config_dir / "config.yaml").write_text(
        "weather:\n  name: default\n" + body, encoding="utf-8")


def test_read_settings_defaults_without_a_rain_block(config_dir):
    _write_rain_config(config_dir, "  window:\n    alignment: middle_middle\n")
    settings = rain.read_settings(str(config_dir))
    assert settings == {
        "enabled": True, "auto": True,
        "count": 24, "speed": 5, "opacity": 0.35,
    }


def test_read_settings_merges_local_overrides(config_dir):
    _write_rain_config(config_dir, "  rain:\n    count: 40\n    speed: 8\n")
    (config_dir / "config.local.yaml").write_text(
        "weather:\n  rain:\n    count: 12\n", encoding="utf-8")
    settings = rain.read_settings(str(config_dir))
    assert settings["count"] == 12   # local wins
    assert settings["speed"] == 8    # base survives the merge


def test_read_settings_clamps_out_of_range_values(config_dir):
    _write_rain_config(config_dir, "  rain:\n    count: 999\n    speed: 42\n    opacity: 5\n")
    settings = rain.read_settings(str(config_dir))
    assert settings["count"] == 120
    assert settings["speed"] == 10
    assert settings["opacity"] == 1.0


def test_read_settings_accepts_string_booleans(config_dir):
    # config_set.py may have written "true"/"false" strings.
    _write_rain_config(config_dir, "  rain:\n    enabled: 'false'\n    auto: 'false'\n")
    settings = rain.read_settings(str(config_dir))
    assert settings["enabled"] is False
    assert settings["auto"] is False


def test_read_settings_survives_a_rain_scalar(config_dir):
    # A hand-edited `rain: true` must not crash the daemon.
    _write_rain_config(config_dir, "  rain: true\n")
    assert rain.read_settings(str(config_dir))["count"] == 24


def test_read_settings_survives_a_broken_config(config_dir):
    (config_dir / "config.yaml").write_text("weather: [oops\n", encoding="utf-8")
    assert rain.read_settings(str(config_dir))["count"] == 24


def test_read_is_raining_true_flag(config_dir):
    cache = config_dir / "generated" / "weather_cache.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"is_raining": True, "condition": "Rain"}))
    assert rain.read_is_raining(str(config_dir)) is True


def test_read_is_raining_false_flag(config_dir):
    cache = config_dir / "generated" / "weather_cache.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"is_raining": False, "condition": "Clear"}))
    assert rain.read_is_raining(str(config_dir)) is False


def test_read_is_raining_missing_cache_defaults_true(config_dir):
    # No cache yet means weather.py has not succeeded; showing rain is the
    # friendlier failure than a silently dry screen.
    assert rain.read_is_raining(str(config_dir)) is True


def test_read_is_raining_corrupt_cache_defaults_true(config_dir):
    cache = config_dir / "generated" / "weather_cache.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("{not json")
    assert rain.read_is_raining(str(config_dir)) is True


def test_read_tint_prefers_color_light(config_dir):
    (config_dir / "eww").mkdir()
    (config_dir / "eww" / "eww.theme.json").write_text(
        json.dumps({"color_light": "#abcdef", "color_dark": "#123456"}),
        encoding="utf-8",
    )
    assert rain.read_tint(str(config_dir)) == "#abcdef"


def test_read_tint_falls_back_when_theme_is_missing(config_dir):
    assert rain.read_tint(str(config_dir)) == rain.DEFAULT_TINT


def test_read_tint_ignores_a_bogus_color(config_dir):
    (config_dir / "eww").mkdir()
    (config_dir / "eww" / "eww.theme.json").write_text(
        json.dumps({"color_light": "not-a-color", "menu_ink": "#00ff00"}),
        encoding="utf-8",
    )
    assert rain.read_tint(str(config_dir)) == "#00ff00"


# --- layer geometry ----------------------------------------------------------

def test_monitor_geometry_returns_four_values():
    # Needs no display: with no monitors it must still yield a usable box.
    x, y, w, h = rain.RainLayer._monitor_geometry(99)
    assert isinstance((x, y, w, h), tuple)
    assert w > 0 and h > 0


def test_rain_app_active_now_matrix(config_dir):
    _write_rain_config(config_dir, "  rain:\n    enabled: true\n    auto: false\n    count: 10\n")
    cache = config_dir / "generated" / "weather_cache.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"is_raining": False}))

    app = rain.RainApp.__new__(rain.RainApp)
    app.config_dir = str(config_dir)
    app.layers = []

    # manual mode falls through to "enabled and count > 0"
    assert app.active_now({"enabled": True, "auto": False, "count": 10}) is True
    assert app.active_now({"enabled": False, "auto": False, "count": 10}) is False
    assert app.active_now({"enabled": True, "auto": False, "count": 0}) is False
    # auto mode gates on the cached precipitation flag
    assert app.active_now({"enabled": True, "auto": True, "count": 10}) is False

    cache.write_text(json.dumps({"is_raining": True}))
    assert app.active_now({"enabled": True, "auto": True, "count": 10}) is True
    # enabled: false wins over a rainy sky
    assert app.active_now({"enabled": False, "auto": True, "count": 10}) is False


# --- layer bookkeeping (GTK calls stubbed out) -------------------------------

class _FakeWin:
    def __init__(self):
        self.visible = False

    def get_visible(self):
        return self.visible

    def show_all(self):
        self.visible = True

    def hide(self):
        self.visible = False


class _FakeOverlay:
    def __init__(self):
        self.children = []

    def add_overlay(self, child):
        self.children.append(child)

    def remove(self, child):
        self.children.remove(child)


class _FakeCssProvider:
    loaded = []

    def load_from_data(self, data):
        _FakeCssProvider.loaded.append(data.decode("utf-8"))


def _layer_stub():
    layer = rain.RainLayer.__new__(rain.RainLayer)
    layer.monitor = 0
    layer.win = _FakeWin()
    layer.overlay = _FakeOverlay()
    layer.drops = []
    layer._signature = None
    layer._provider = None
    layer.geometry = (0, 0, 1920, 1080)
    return layer


def test_apply_registers_exactly_one_provider_per_rebuild(monkeypatch):
    # Providers added for a screen are only dropped by removing them again: a
    # slider drag used to stack one provider per frame and leak the old rules.
    added, removed = [], []
    monkeypatch.setattr(rain.Gtk, "CssProvider", _FakeCssProvider)
    monkeypatch.setattr(rain.Gtk.StyleContext, "add_provider_for_screen",
                        lambda screen, provider, prio: added.append(provider))
    monkeypatch.setattr(rain.Gtk.StyleContext, "remove_provider_for_screen",
                        lambda screen, provider: removed.append(provider))
    monkeypatch.setattr(rain.Gtk, "Box", lambda: _FakeDrop())
    monkeypatch.setattr(rain.Gtk, "Align", type("A", (), {"START": 0}))

    layer = _layer_stub()
    settings = {"count": 10, "speed": 5, "opacity": 0.35}
    for _ in range(5):
        settings["count"] += 1     # force a rebuild every time
        layer.apply(settings, "#ffffff")

    assert len(added) == 5
    # 4 intermediate providers released, the live one kept.
    assert len(removed) == 4
    assert layer._provider is added[-1]
    assert layer._provider not in removed


def test_apply_skips_work_when_nothing_changed(monkeypatch):
    added = []
    monkeypatch.setattr(rain.Gtk, "CssProvider", _FakeCssProvider)
    monkeypatch.setattr(rain.Gtk.StyleContext, "add_provider_for_screen",
                        lambda screen, provider, prio: added.append(provider))
    monkeypatch.setattr(rain.Gtk.StyleContext, "remove_provider_for_screen",
                        lambda screen, provider: None)
    monkeypatch.setattr(rain.Gtk, "Box", lambda: _FakeDrop())
    monkeypatch.setattr(rain.Gtk, "Align", type("A", (), {"START": 0}))

    layer = _layer_stub()
    settings = {"count": 10, "speed": 5, "opacity": 0.35}
    assert layer.apply(settings, "#ffffff") is True
    assert layer.apply(settings, "#ffffff") is False   # same signature
    assert len(added) == 1


def test_apply_rebuilds_when_the_tint_moves(monkeypatch):
    monkeypatch.setattr(rain.Gtk, "CssProvider", _FakeCssProvider)
    monkeypatch.setattr(rain.Gtk.StyleContext, "add_provider_for_screen",
                        lambda screen, provider, prio: None)
    monkeypatch.setattr(rain.Gtk.StyleContext, "remove_provider_for_screen",
                        lambda screen, provider: None)
    monkeypatch.setattr(rain.Gtk, "Box", lambda: _FakeDrop())
    monkeypatch.setattr(rain.Gtk, "Align", type("A", (), {"START": 0}))

    layer = _layer_stub()
    settings = {"count": 4, "speed": 5, "opacity": 0.35}
    layer.apply(settings, "#ffffff")
    assert layer.apply(settings, "#00ff00") is True
    assert "#00ff00" in _FakeCssProvider.loaded[-1]


def test_deactivate_releases_the_droplet_widgets():
    layer = _layer_stub()
    layer.drops = [_FakeDrop(), _FakeDrop()]
    layer.overlay.children = list(layer.drops)
    layer._signature = ("x",)
    layer.deactivate()
    assert layer.drops == []
    assert layer.overlay.children == []
    assert layer.win.get_visible() is False
    assert layer._signature is None, "a stale signature would skip the rebuild"


class _FakeDrop:
    def get_style_context(self):
        return self

    def add_class(self, name):
        pass

    def set_halign(self, align):
        pass

    def set_valign(self, align):
        pass


def test_set_active_shows_and_hides():
    layer = _layer_stub()
    layer.set_active(True)
    assert layer.win.get_visible() is True
    layer.set_active(False)
    assert layer.win.get_visible() is False


# --- monitor topology -------------------------------------------------------

def test_monitor_signature_is_a_tuple_of_boxes():
    sig = rain.RainApp._monitor_signature()
    assert isinstance(sig, tuple)
    assert all(isinstance(box, tuple) and len(box) == 4 for box in sig)


def test_rebuild_layers_replaces_every_layer(monkeypatch):
    # A hotplug / resolution change must tear the old windows down and build
    # fresh ones for the new monitor set, not keep the stale geometry.
    destroyed = []
    app = rain.RainApp.__new__(rain.RainApp)
    app.config_dir = "."
    app.layers = [_layer_stub(), _layer_stub()]
    monkeypatch.setattr(rain.RainLayer, "destroy",
                        lambda self: destroyed.append(self))
    app._build_layers = lambda: app.layers.append("fresh")
    app._rebuild_layers()
    assert len(destroyed) == 2
    assert app.layers == ["fresh"]


def test_rebuild_layers_survives_a_failing_destroy(monkeypatch):
    # One broken window must not abort the rebuild and leave the old layers.
    def boom(self):
        raise RuntimeError("already gone")

    app = rain.RainApp.__new__(rain.RainApp)
    app.config_dir = "."
    app.layers = [_layer_stub()]
    monkeypatch.setattr(rain.RainLayer, "destroy", boom)
    app._build_layers = lambda: app.layers.append("fresh")
    app._rebuild_layers()
    assert app.layers == ["fresh"]


# --- transparency (the wallpaper must show through the layer) ----------------

def test_build_css_makes_the_window_background_transparent():
    # Regression: without this rule the full-screen layer was an opaque
    # rectangle, so the rain was visible but the wallpaper and the desktop
    # icons disappeared behind it (only the droplets could be seen through).
    drops, travel = rain.plan_drops(5, 5, 1920, 1080)
    css = rain.build_css(drops, travel, 0.35)
    assert "window.rain-window" in css
    assert "background-color: transparent" in css


def test_build_css_transparent_rule_covers_the_overlay():
    # The overlay is the child that actually fills the window, so it needs the
    # transparent background too, not just the toplevel.
    drops, travel = rain.plan_drops(5, 5, 1920, 1080)
    css = rain.build_css(drops, travel, 0.35)
    assert "rain-overlay" in css
    # Every background-color before the @keyframes must be transparent: a
    # single opaque value on the window / overlay brings the wallpaper bug back.
    head = css.split("@keyframes")[0]
    values = re.findall(r"background-color:\s*([^;}]+)", head)
    assert values == ["transparent"]


def test_layer_requests_an_alpha_visual_and_app_paintable(monkeypatch):
    # The three transparency pieces: an RGBA visual on the toplevel,
    # set_app_paintable, and the CSS rule above. Set up in __init__ BEFORE the
    # window is realized, which is the only moment a visual can be changed.
    if rain.WAYLAND:
        pytest.skip("on Wayland the compositor draws the layer-shell surface")

    calls = []

    class _FakeScreen:
        def get_rgba_visual(self):
            return "rgba-visual"

    class _FakeCtx2:
        """Records add_class() on whatever object it was created for."""

        def __init__(self, owner):
            self._owner = owner

        def add_class(self, name):
            self._owner.classes.append(name)

    class _FakeWin:
        def __init__(self):
            self.classes = []
            self.visual = None
            self.app_paintable = False

        def get_screen(self):
            return _FakeScreen()

        def set_visual(self, visual):
            calls.append("set_visual")
            self.visual = visual

        def set_app_paintable(self, value):
            calls.append("set_app_paintable")
            self.app_paintable = bool(value)

        def get_style_context(self):
            return _FakeCtx2(self)

        def __getattr__(self, name):
            # every other window setter (title, decorated, keep_below, ...) is
            # a no-op for this test
            return lambda *a, **k: None

    win = _FakeWin()
    monkeypatch.setattr(rain.Gtk, "Window",
                        type("W", (), {"new": staticmethod(lambda *_a: win)}))
    monkeypatch.setattr(rain.Gtk, "WindowType", type("W", (), {"TOPLEVEL": 0}))
    monkeypatch.setattr(rain.Gdk, "WindowTypeHint",
                        type("H", (), {"UTILITY": 0, "DESKTOP": 1}))
    class _FakeOverlay(_FakeDrop):
        def __init__(self):
            # __getattr__ below swallows anything missing, so `classes` has to
            # be a real attribute for _FakeCtx2 to record into.
            self.classes = []

        def get_style_context(self):
            return _FakeCtx2(self)

        def __getattr__(self, name):
            return lambda *a, **k: None

    overlay = _FakeOverlay()
    # Gtk.Overlay() is called directly (no .new), unlike Gtk.Window.new(...)
    monkeypatch.setattr(rain.Gtk, "Overlay", lambda *_a: overlay)
    monkeypatch.setattr(rain.RainLayer, "_monitor_geometry",
                        staticmethod(lambda m: (0, 0, 800, 600)))

    layer = rain.RainLayer(0)

    assert "rain-window" in win.classes, "the CSS rule needs this class"
    assert "rain-overlay" in overlay.classes, "the overlay needs the class too"
    assert win.visual == "rgba-visual", "an RGBA visual is required for alpha"
    assert win.app_paintable is True, (
        "without app_paintable GTK fills the window with the theme background")
    assert calls[:2] == ["set_visual", "set_app_paintable"]
