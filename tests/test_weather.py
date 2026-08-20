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