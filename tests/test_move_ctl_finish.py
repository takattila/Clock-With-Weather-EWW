"""finish() must close the popup stack before clearing the session file.

Regression: ending a Move/Resize session with Save / Cancel / Reset (or
Enter / ESC on the keyboard) only removed generated/input_session.json --
the per-monitor dismiss overlays stayed mapped above the widget, swallowing
every further right-click until restart.
"""

import json
import sys

import move_ctl
import session


def _write_session(tmp_path):
    p = tmp_path / "input_session.json"
    p.write_text(json.dumps({"mode": "move", "overlays": [0, 1]}), encoding="utf-8")
    return p


def test_finish_closes_popups_before_clearing(tmp_path, monkeypatch):
    sess = _write_session(tmp_path)
    monkeypatch.setattr(session, "SESSION_FILE", str(sess))

    calls = {}

    class FakeClosePopup:
        @staticmethod
        def read_session_data():
            return {"mode": "move", "widget": "clock", "overlays": [0, 1]}

        @staticmethod
        def close_popups_verified(data):
            calls["data"] = data
            calls["closed"] = True

    monkeypatch.setitem(sys.modules, "close_popup", FakeClosePopup)

    move_ctl.finish()

    assert calls["closed"] is True
    assert calls["data"]["overlays"] == [0, 1]  # ids read BEFORE the delete
    assert not sess.exists()                    # session still ends


def test_finish_survives_close_popup_failure(tmp_path, monkeypatch):
    sess = _write_session(tmp_path)
    monkeypatch.setattr(session, "SESSION_FILE", str(sess))

    class Boom:
        @staticmethod
        def read_session_data():
            raise RuntimeError("boom")

        @staticmethod
        def close_popups_verified(data):
            raise RuntimeError("boom")

    monkeypatch.setitem(sys.modules, "close_popup", Boom)

    move_ctl.finish()  # must not raise

    assert not sess.exists()
