"""Invisible keyboard daemon (scripts/move/input_daemon.py) key routing.

Window creation and /dev/input access only happen in main(); handle_key() is
pure enough to test with a stubbed run_script.
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "move"))

import input_daemon  # noqa: E402


def capture_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(input_daemon, "run_script", lambda args: calls.append(args))
    return calls


def test_esc_closes_popup_in_every_session_mode(monkeypatch):
    calls = capture_calls(monkeypatch)
    for mode in ("ctx", "gap", "weather"):
        input_daemon.handle_key(input_daemon.KEY_ESC, False, {"mode": mode})
    assert len(calls) == 3
    assert all(
        os.path.normpath(c[0]).endswith(os.path.join("widgets", "close_popup.py"))
        for c in calls
    )


def test_esc_closes_unknown_future_modes_too(monkeypatch):
    calls = capture_calls(monkeypatch)
    # Universal ESC: a future session mode is closed with zero daemon changes.
    input_daemon.handle_key(input_daemon.KEY_ESC, False, {"mode": "bogus"})
    assert len(calls) == 1
    assert os.path.normpath(calls[0][0]).endswith(
        os.path.join("widgets", "close_popup.py")
    )


def test_typing_still_closes_on_esc(monkeypatch):
    calls = capture_calls(monkeypatch)
    # ESC is reserved for closing: it works even while an entry of the GTK
    # panel owns the keyboard (session["typing"] set).
    for mode in ("gap", "weather"):
        input_daemon.handle_key(
            input_daemon.KEY_ESC, False, {"mode": mode, "typing": True}
        )
    assert len(calls) == 2
    assert all(
        os.path.normpath(c[0]).endswith(os.path.join("widgets", "close_popup.py"))
        for c in calls
    )


def test_typing_blocks_every_other_key(monkeypatch):
    calls = capture_calls(monkeypatch)
    input_daemon.handle_key(
        input_daemon.KEY_LEFT, False, {"mode": "weather", "typing": True}
    )
    input_daemon.handle_key(
        input_daemon.KEY_ENTER, False, {"mode": "gap", "typing": True}
    )
    assert calls == []


def test_weather_arrows_do_nothing(monkeypatch):
    calls = capture_calls(monkeypatch)
    # Arrows belong to the move mode only.
    input_daemon.handle_key(input_daemon.KEY_LEFT, False, {"mode": "weather"})
    input_daemon.handle_key(input_daemon.KEY_UP, False, {"mode": "weather"})
    assert calls == []


def test_move_typing_guards_arrows(monkeypatch):
    calls = capture_calls(monkeypatch)
    input_daemon.handle_key(
        input_daemon.KEY_LEFT, False, {"mode": "move", "typing": True}
    )
    assert calls == []


def test_unknown_mode_ignores_non_esc_keys(monkeypatch):
    calls = capture_calls(monkeypatch)
    # Only ESC is universal; non-ESC keys are unmapped outside the move mode.
    input_daemon.handle_key(input_daemon.KEY_LEFT, False, {"mode": "bogus"})
    input_daemon.handle_key(input_daemon.KEY_UP, False, {"mode": "bogus"})
    assert calls == []


def test_move_esc_cancels_not_closes(monkeypatch):
    calls = capture_calls(monkeypatch)
    input_daemon.handle_key(
        input_daemon.KEY_ESC, False, {"mode": "move", "widget": "panel", "monitor": 1}
    )
    assert len(calls) == 1
    args = calls[0]
    assert os.path.normpath(args[0]).endswith(os.path.join("move", "move_ctl.py"))
    assert "--widget" in args and args[args.index("--widget") + 1] == "panel"
    assert "--monitor" in args and args[args.index("--monitor") + 1] == "1"
    assert "--action" in args and args[args.index("--action") + 1] == "cancel"


def test_move_esc_cancels_even_while_typing(monkeypatch):
    calls = capture_calls(monkeypatch)
    # ESC is exempt from the move typing guard too: typing a resize percentage
    # must never block the escape hatch back to the session.
    input_daemon.handle_key(
        input_daemon.KEY_ESC,
        False,
        {"mode": "move", "widget": "clock", "monitor": 0, "typing": True},
    )
    assert len(calls) == 1
    assert "--action" in calls[0]
    assert calls[0][calls[0].index("--action") + 1] == "cancel"


def test_move_typing_guards_non_esc(monkeypatch):
    calls = capture_calls(monkeypatch)
    # Enter would SAVE and -/+ would zoom while the user types a percentage.
    for code in (
        input_daemon.KEY_LEFT,
        input_daemon.KEY_ENTER,
        input_daemon.KEY_MINUS,
        input_daemon.KEY_KPPLUS,
    ):
        input_daemon.handle_key(
            code, False, {"mode": "move", "typing": True}
        )
    assert calls == []