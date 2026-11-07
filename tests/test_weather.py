import json
import sys

import pytest

import weather


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _argv(*args):
    return ["weather.py"] + list(args)


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch, tmp_path):
    """Point the cache at a tmp file for EVERY test in this module.

    A successful fetch calls write_cache(), so without this any test that
    patches requests.get would overwrite the real generated/weather_cache.json
    in the user's live widget directory with fixture data (and the rain layer
    would then follow a fake sky).
    """
    monkeypatch.setattr(
        weather, "CACHE_FILE", str(tmp_path / "generated" / "weather_cache.json"))


def test_missing_arguments(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["weather.py"])
    weather.get_weather()
    out = json.loads(capsys.readouterr().out)
    assert out == {"error": "Missing arguments"}


def test_success(monkeypatch, capsys):
    payload = {
        "main": {"temp": 21.4, "temp_min": 18.1, "temp_max": 24.9, "feels_like": 20.0},
        "weather": [{"icon": "01d"}],
    }

    def fake_get(url, **kwargs):
        assert "api.openweathermap.org" in url
        assert "appid=secret" in url
        return FakeResponse(200, payload)

    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(
        sys,
        "argv",
        _argv("secret", "Budapest", "hu", "metric", "https://api.openweathermap.org/data/2.5/weather"),
    )
    weather.get_weather()
    out = json.loads(capsys.readouterr().out)
    assert out["temp_fmt"] == "21"
    assert out["temp_min_fmt"] == "18"
    assert out["temp_max_fmt"] == "25"
    assert out["feels_like_fmt"] == "20"
    assert out["icon_path"] == "01d"
    assert out["unit_symbol"] == "°C"


def test_fahrenheit_unit(monkeypatch, capsys):
    payload = {
        "main": {"temp": 70.0, "temp_min": 60.0, "temp_max": 80.0, "feels_like": 72.0},
        "weather": [{"icon": "01d"}],
    }
    monkeypatch.setattr(
        weather.requests,
        "get",
        lambda url, **kwargs: FakeResponse(200, payload),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        _argv("k", "Budapest", "hu", "imperial", "https://api.openweathermap.org/data/2.5/weather"),
    )
    weather.get_weather()
    out = json.loads(capsys.readouterr().out)
    assert out["unit_symbol"] == "°F"


def test_api_error(monkeypatch, capsys):
    monkeypatch.setattr(
        weather.requests,
        "get",
        lambda url, **kwargs: FakeResponse(401, {"message": "Invalid API key"}),
    )
    monkeypatch.setattr(sys, "argv", _argv("k", "X", "hu", "metric", "https://api.openweathermap.org/"))
    weather.get_weather()
    out = json.loads(capsys.readouterr().out)
    assert out == {"error": "Invalid API key"}


def test_exception_handling(monkeypatch, capsys):
    def boom(url, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(weather.requests, "get", boom)
    monkeypatch.setattr(sys, "argv", _argv("k", "X", "hu", "metric", "https://api.openweathermap.org/"))
    weather.get_weather()
    out = json.loads(capsys.readouterr().out)
    assert out == {"error": "network down"}


def test_trailing_slash_api_url(monkeypatch, capsys):
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return FakeResponse(200, {"main": {"temp": 10.0}, "weather": [{"icon": "01n"}]})

    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(
        sys, "argv", _argv("k", "X", "hu", "metric", "https://example.com/base/")
    )
    weather.get_weather()
    assert not captured["url"].startswith("https://example.com/base//")


# --- precipitation flag (v5.0.0: the raindrop layer's "auto" mode) ---------

def _condition_response(main, monkeypatch, capsys):
    """Run weather.py against a one-entry `weather` list with the given `main`."""
    monkeypatch.setattr(
        weather.requests,
        "get",
        lambda url, **kwargs: FakeResponse(
            200,
            {
                "main": {"temp": 10.0, "temp_min": 9.0, "temp_max": 11.0,
                         "feels_like": 9.5},
                "weather": [{"icon": "10d", "main": main}],
            },
        ),
    )
    monkeypatch.setattr(
        sys, "argv",
        _argv("k", "X", "hu", "metric", "https://example.com/"),
    )
    weather.get_weather()
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("condition", [
    "Rain", "Drizzle", "Thunderstorm", "Snow", "Squall", "Shower",
    "rain", "SNOW",   # case-insensitive
])
def test_is_raining_true_for_precipitation(condition, monkeypatch, capsys):
    out = _condition_response(condition, monkeypatch, capsys)
    assert out["condition"] == condition
    assert out["is_raining"] is True


@pytest.mark.parametrize("condition", [
    "Clear", "Clouds", "Mist", "Fog", "Haze", "Dust", "Tornado", "Thundery",
])
def test_is_raining_false_for_non_precipitation(condition, monkeypatch, capsys):
    out = _condition_response(condition, monkeypatch, capsys)
    assert out["is_raining"] is False


def test_condition_missing_defaults_to_not_raining(monkeypatch, capsys):
    # No `main` key at all: must not raise, and must not show rain.
    monkeypatch.setattr(
        weather.requests,
        "get",
        lambda url, **kwargs: FakeResponse(
            200,
            {"main": {"temp": 10.0, "temp_min": 9.0, "temp_max": 11.0,
                      "feels_like": 9.5},
             "weather": [{"icon": "01d"}]},
        ),
    )
    monkeypatch.setattr(
        sys, "argv",
        _argv("k", "X", "hu", "metric", "https://example.com/"),
    )
    weather.get_weather()
    out = json.loads(capsys.readouterr().out)
    assert out["condition"] == ""
    assert out["is_raining"] is False


def test_successful_fetch_writes_cache(monkeypatch, capsys, tmp_path):
    # rain.py reads generated/weather_cache.json instead of polling the API.
    cache = tmp_path / "generated" / "weather_cache.json"
    monkeypatch.setattr(weather, "CACHE_FILE", str(cache))
    out = _condition_response("Rain", monkeypatch, capsys)
    assert out["is_raining"] is True
    assert cache.exists()
    cached = json.loads(cache.read_text())
    assert cached["is_raining"] is True
    assert cached["condition"] == "Rain"


def test_error_response_does_not_overwrite_cache(monkeypatch, capsys, tmp_path):
    # A failed fetch must leave the last good state in place, otherwise the
    # rain would flicker off on every API hiccup.
    cache = tmp_path / "generated" / "weather_cache.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"is_raining": True, "condition": "Rain"}))
    monkeypatch.setattr(weather, "CACHE_FILE", str(cache))
    monkeypatch.setattr(
        weather.requests,
        "get",
        lambda url, **kwargs: FakeResponse(500, {"message": "boom"}),
    )
    monkeypatch.setattr(
        sys, "argv",
        _argv("k", "X", "hu", "metric", "https://example.com/"),
    )
    weather.get_weather()
    assert json.loads(capsys.readouterr().out) == {"error": "boom"}
    assert json.loads(cache.read_text())["is_raining"] is True


def test_cache_write_failure_is_not_fatal(monkeypatch, capsys, tmp_path):
    # A generated/ that cannot be written must not break the widget's weather
    # poll: the payload is still printed for the eww defpoll.
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    monkeypatch.setattr(weather, "CACHE_FILE", str(blocked / "weather_cache.json"))
    out = _condition_response("Rain", monkeypatch, capsys)
    assert out["is_raining"] is True