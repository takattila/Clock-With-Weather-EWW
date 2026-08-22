import close_popup


def test_windows_to_close_per_monitor_overlays():
    data = {"mode": "ctx", "overlays": [1, 0]}
    assert close_popup.windows_to_close(data) == [
        "ctx_menu",
        "submenu",
        "dismiss_overlay_1",
        "dismiss_overlay_0",
        "dismiss_overlay",
    ]


def test_windows_to_close_defaults_without_session():
    assert close_popup.windows_to_close(None) == [
        "ctx_menu", "submenu", "dismiss_overlay"
    ]
    assert close_popup.windows_to_close({}) == [
        "ctx_menu", "submenu", "dismiss_overlay"
    ]


def test_windows_to_close_skips_invalid_indices():
    data = {"overlays": [0, "x", None, 3]}
    out = close_popup.windows_to_close(data)
    assert "dismiss_overlay_0" in out
    assert "dismiss_overlay_3" in out
    assert "dismiss_overlay_x" not in out
    assert "dismiss_overlay_None" not in out


def test_windows_to_close_deduplicates():
    data = {"overlays": [2, 2]}
    out = close_popup.windows_to_close(data)
    assert out.count("dismiss_overlay_2") == 1


def test_legacy_dismiss_always_present():
    for data in ({"overlays": [5]}, {}, None):
        assert "dismiss_overlay" in close_popup.windows_to_close(data)
