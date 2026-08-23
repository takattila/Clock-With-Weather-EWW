import subprocess
import types

import close_popup


def test_windows_to_close_per_monitor_overlays():
    data = {"mode": "ctx", "overlays": [1, 0]}
    assert close_popup.windows_to_close(data) == [
        "ctx_menu",
        "dismiss_overlay_1",
        "dismiss_overlay_0",
        "dismiss_overlay",
    ]


def test_windows_to_close_defaults_without_session():
    assert close_popup.windows_to_close(None) == [
        "ctx_menu", "dismiss_overlay"
    ]
    assert close_popup.windows_to_close({}) == [
        "ctx_menu", "dismiss_overlay"
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


# ------------------------------------------------------- orphaned overlays

ACTIVE_SAMPLE = "\n".join([
    "dismiss_overlay_1: dismiss_overlay",
    "main_0: main_window_x11",
    "panel_0: panel_window_x11",
    "dismiss_overlay_0: dismiss_overlay",
    "",
])


def _fake_run(responses, calls):
    """subprocess.run replacement: records commands, feeds canned stdout.

    `responses` maps a substring of the command (e.g. 'active-windows') to a
    list of outputs returned per successive call; other commands return ''.
    """

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        out = ""
        for key, items in responses.items():
            if key in cmd:
                out = items.pop(0) if items else ""
                break
        return types.SimpleNamespace(stdout=out, stderr="")

    return fake_run


def test_active_tracked_parses_ids_and_filters(monkeypatch):
    calls = []
    monkeypatch.setattr(close_popup.subprocess, "run", _fake_run(
        {"active-windows": [ACTIVE_SAMPLE]}, calls))
    assert close_popup.active_tracked() == [
        ("dismiss_overlay_1", "dismiss_overlay"),
        ("dismiss_overlay_0", "dismiss_overlay"),
    ]


def test_active_tracked_none_on_failure(monkeypatch):
    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)

    monkeypatch.setattr(close_popup.subprocess, "run", boom)
    assert close_popup.active_tracked() is None
    assert close_popup.open_popup_names() is None


def test_verify_loop_closes_orphans_by_id(monkeypatch):
    # A Move/Resize session that was ended without popup cleanup already
    # deleted the session file: windows_to_close() only knows the legacy
    # name, yet both per-monitor overlays are still mapped. The verify loop
    # must close them by INSTANCE id discovered via active-windows.
    calls = []
    monkeypatch.setattr(close_popup.subprocess, "run", _fake_run({
        "active-windows": [ACTIVE_SAMPLE, ""],  # 1st query: open, 2nd: gone
    }, calls))
    monkeypatch.setattr(close_popup, "x11_stray_ids", lambda names: [])
    monkeypatch.setattr(close_popup.time, "sleep", lambda s: None)

    close_popup.close_popups_verified(None)

    closed = [c[-1] for c in calls if c[0] == "eww" and "close" in c]
    assert "dismiss_overlay" in closed            # legacy name still tried
    assert "dismiss_overlay_0" in closed          # ...AND the orphaned ids
    assert "dismiss_overlay_1" in closed
