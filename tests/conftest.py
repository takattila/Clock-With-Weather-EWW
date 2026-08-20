import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

BASE_CONFIG = textwrap.dedent(
    """\
    # header comment
    appearance: light
    weather:
      city: Tatabánya
      language_code: hu
      lang: hu
      units: metric
      api_url: https://api.openweathermap.org/data/2.5/weather
      window:
        alignment: middle_middle
        per_monitor:
          0:
            position_x: 10
            position_y: 20
            scale: 0.80
          1:
            position_x: 0
            position_y: 0
            scale: 0.90
    system:
      hour_format: "24"
    panel:
      enabled: true
      window:
        alignment: right
        per_monitor:
          0:
            position_x: 0
            position_y: 0
            scale: 1.00
          1:
            position_x: 30
            position_y: 40
            scale: 0.70
      gap: { top: 5, bottom: 5, left: 0, right: 0 }
    """
)


@pytest.fixture
def config_dir(tmp_path):
    d = tmp_path / "config"
    d.mkdir()
    return d


@pytest.fixture
def write_config(config_dir):
    def _write(content=BASE_CONFIG):
        p = config_dir / "config.yaml"
        p.write_text(content, encoding="utf-8")
        return p

    return _write