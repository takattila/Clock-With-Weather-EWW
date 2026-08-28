"""scripts/widgets/submenu_hide.py: hides the picker pane (sub_show=false)."""

import submenu_hide  # noqa: E402  (scripts/widgets on pythonpath)


def test_hides_pane_via_eww_update(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

    monkeypatch.setattr(submenu_hide.subprocess, "run", fake_run)

    submenu_hide.main()

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[:3] == ["eww", "--config", submenu_hide.EWW_CONFIG_DIR]
    assert cmd[3:] == ["update", "sub_show=false"]
    assert submenu_hide.EWW_CONFIG_DIR.endswith(
        ("eww", "Clock-With-Weather-EWW/eww")
    )


def test_survives_eww_failure(monkeypatch):
    def boom(cmd, **kwargs):
        raise RuntimeError("eww down")

    monkeypatch.setattr(submenu_hide.subprocess, "run", boom)
    submenu_hide.main()  # must not raise