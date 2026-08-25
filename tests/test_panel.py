import json
import sys
from types import SimpleNamespace

import pytest


def _panel():
    import panel

    return panel


def test_format_bytes():
    panel = _panel()
    assert panel.format_bytes(1024) == "1 KB"
    assert panel.format_bytes(None) == "N/A"
    assert panel.format_bytes(1500) == "1.5 KB"


def test_update_history():
    panel = _panel()
    hist = []
    for i in range(panel.MAX_POINTS + 10):
        panel.update_history(hist, i)
    assert len(hist) == panel.MAX_POINTS
    assert hist[-1] == panel.MAX_POINTS + 9


def test_get_dynamic_max():
    panel = _panel()
    assert panel.get_dynamic_max([100, 200, 300], 1024) == 1024 * 1.1
    assert panel.get_dynamic_max([2000], 1024) == 2200.0


def test_hex_to_rgb255():
    panel = _panel()
    assert panel.hex_to_rgb255("#ffffff") == (255, 255, 255)
    assert panel.hex_to_rgb255("#abc") == (170, 187, 204)


def test_load_chart_colors(monkeypatch, tmp_path):
    panel = _panel()
    theme_json = tmp_path / "eww.theme.json"
    theme_json.write_text(
        json.dumps(
            {
                "chart_cpu": "#ff9500",
                "chart_memory": "#00e5ff",
                "chart_down": "#ff2d95",
                "chart_up": "#39ff14",
                "chart_glow": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(panel, "THEME_JSON_FILE", str(theme_json))
    colors, glow = panel.load_chart_colors()
    assert colors == {
        "cpu": "#ff9500",
        "mem": "#00e5ff",
        "down": "#ff2d95",
        "up": "#39ff14",
    }
    assert glow is True


def test_load_chart_colors_scss_fallback(monkeypatch, tmp_path):
    """Without the theme JSON the $color-light regex still feeds all charts."""
    panel = _panel()
    monkeypatch.setattr(panel, "THEME_JSON_FILE", str(tmp_path / "missing.json"))
    scss = tmp_path / "eww.theme.scss"
    scss.write_text("$color-light: #aabbcc;\n", encoding="utf-8")
    monkeypatch.setattr(panel, "THEME_FILE", str(scss))
    colors, glow = panel.load_chart_colors()
    assert colors == {
        "cpu": "#aabbcc",
        "mem": "#aabbcc",
        "down": "#aabbcc",
        "up": "#aabbcc",
    }
    assert glow is False


def test_load_chart_colors_default(monkeypatch, tmp_path):
    panel = _panel()
    monkeypatch.setattr(panel, "THEME_JSON_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(panel, "THEME_FILE", str(tmp_path / "missing.scss"))
    colors, glow = panel.load_chart_colors()
    assert colors == {
        "cpu": "#ffffff",
        "mem": "#ffffff",
        "down": "#ffffff",
        "up": "#ffffff",
    }
    assert glow is False


def test_render_chart(tmp_path):
    panel = _panel()
    out = tmp_path / "cpu.svg"
    panel.render_chart(str(out), [50, 100, 25], 100, "#ff0000", 100, 50)
    svg = out.read_text(encoding="utf-8")
    assert 'width="100" height="50"' in svg
    assert "<polyline" in svg
    assert '<polygon points="' in svg


def test_render_chart_glow(tmp_path):
    panel = _panel()
    out = tmp_path / "cpu.svg"
    panel.render_chart(str(out), [50, 100, 25], 100, "#ff0000", 100, 50, glow=True)
    svg = out.read_text(encoding="utf-8")
    assert svg.count("<polyline") == 2
    assert 'stroke-width="6"' in svg
    assert 'stroke-width="2"' in svg


def test_main(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["panel.py"])
    panel = _panel()

    cpu_times = [120.0, 30.0, 300.0, 500.0, 50.0]
    monkeypatch.setattr(panel.psutil, "cpu_times", lambda: cpu_times)
    monkeypatch.setattr(
        panel.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(percent=43.5, total=16 * 1024**3),
    )
    monkeypatch.setattr(
        panel.psutil,
        "net_io_counters",
        lambda pernic=True: {"eth0": SimpleNamespace(bytes_recv=10**9, bytes_sent=5 * 10**8)},
    )
    monkeypatch.setattr(panel.psutil, "cpu_freq", lambda: SimpleNamespace(current=2400.0))
    monkeypatch.setattr(panel, "get_active_iface", lambda: "eth0")
    monkeypatch.setattr(panel, "load_panel_heights", lambda: [1080])

    charts = tmp_path / "charts"
    charts.mkdir()
    monkeypatch.setattr(panel, "CHARTS_DIR", str(charts))
    monkeypatch.setattr(panel, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(panel, "THEME_FILE", str(tmp_path / "eww.theme.scss"))
    monkeypatch.setattr(panel, "THEME_JSON_FILE", str(tmp_path / "eww.theme.json"))
    monkeypatch.setattr(panel, "LAYOUT_FILE", str(tmp_path / ".layout.json"))

    panel.main()
    out = json.loads(capsys.readouterr().out)
    assert out["cpu_file"].startswith("../charts/cpu_h1080_")
    assert "cpu_txt" in out
    assert "mem_txt" in out
    assert "down_txt" in out
    assert "up_txt" in out
    assert list(out["files"].keys()) == ["1080"]
    assert list(charts.iterdir())