import json

import system


def test_format_bytes_units():
    assert system.format_bytes(0) == "0 B"
    assert system.format_bytes(512) == "512 B"
    assert system.format_bytes(1024) == "1 KB"
    assert system.format_bytes(1536) == "1.5 KB"
    assert system.format_bytes(5 * 1024 * 1024) == "5 MB"
    assert system.format_bytes(2 * 1024**3) == "2 GB"
    assert system.format_bytes(None) == "N/A"


def test_get_system_info(monkeypatch, capsys):
    class Mem:
        used = 4 * 1024**3
        total = 16 * 1024**3

    class Swap:
        percent = 12
        total = 2 * 1024**3

    monkeypatch.setattr(
        system.shutil, "disk_usage", lambda path: (1000, 800, 200)
    )
    monkeypatch.setattr(system.psutil, "virtual_memory", lambda: Mem())
    monkeypatch.setattr(system.psutil, "cpu_percent", lambda interval=0.2: 42.0)
    monkeypatch.setattr(system.psutil, "swap_memory", lambda: Swap())

    system.get_system_info()
    out = json.loads(capsys.readouterr().out)

    assert out["hdd"] == "200 B / 1000 B"
    assert out["ram"] == "4 GB / 16 GB"
    assert out["cpu"] == "42%"
    assert out["swap"] == "12% (size: 2 GB)"