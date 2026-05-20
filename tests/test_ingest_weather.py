"""Tests for the Open-Meteo weather ingest module."""

import importlib
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.models.weather import CurrentConditions, PressureTrend, WeatherForecast

_weather = importlib.import_module("src.ingest.global.weather")
get_current_conditions = _weather.get_current_conditions
get_forecast = _weather.get_forecast
get_recent_history = _weather.get_recent_history
_compute_trend_from_readings = _weather._compute_trend_from_readings
_TTL_CURRENT = _weather._TTL_CURRENT

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def _mock_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------


def test_get_current_conditions_parses_fixture(tmp_path):
    with (
        patch("src.ingest.global.weather._CACHE_DIR", tmp_path),
        patch("httpx.get", return_value=_mock_response(_load("open_meteo_current.json"))),
        patch("time.sleep"),
    ):
        result = get_current_conditions(43.7, -79.4)

    assert isinstance(result, CurrentConditions)
    assert result.temperature_c == 15.2
    assert result.pressure_hpa == 1013.2
    assert result.humidity_pct == 65.0
    assert result.wind_speed_kmh == 12.3
    assert result.weather_code == 1
    assert result.jurisdiction == "CA-ON"
    assert result.time == datetime(2026, 5, 20, 12, 0)


def test_get_forecast_parses_fixture(tmp_path):
    with (
        patch("src.ingest.global.weather._CACHE_DIR", tmp_path),
        patch("httpx.get", return_value=_mock_response(_load("open_meteo_forecast.json"))),
        patch("time.sleep"),
    ):
        result = get_forecast(43.7, -79.4, days=10)

    assert isinstance(result, WeatherForecast)
    assert len(result.days) == 10
    assert result.days[0].temp_max_c == 18.5
    assert result.days[0].temp_min_c == 10.2
    assert result.days[1].precipitation_sum_mm == 2.3
    assert result.jurisdiction == "CA-ON"


def test_get_recent_history_parses_fixture(tmp_path):
    with (
        patch("src.ingest.global.weather._CACHE_DIR", tmp_path),
        patch("httpx.get", return_value=_mock_response(_load("open_meteo_history.json"))),
        patch("time.sleep"),
    ):
        result = get_recent_history(43.7, -79.4, days_back=3)

    assert len(result) == 48
    assert all(isinstance(r[0], datetime) for r in result)
    assert all(isinstance(r[1], float) for r in result)
    assert result[0] == (datetime(2026, 5, 18, 0, 0), 1019.5)
    assert result[-1] == (datetime(2026, 5, 19, 23, 0), 1014.8)


# ---------------------------------------------------------------------------
# Pressure trend classification
# ---------------------------------------------------------------------------


def _make_current(pressure_hpa: float) -> CurrentConditions:
    return CurrentConditions(
        lat=43.7,
        lng=-79.4,
        jurisdiction="CA-ON",
        time=datetime(2026, 5, 20, 12, 0),
        temperature_c=15.0,
        humidity_pct=60.0,
        precipitation_mm=0.0,
        wind_speed_kmh=10.0,
        pressure_hpa=pressure_hpa,
        cloud_cover_pct=30.0,
        weather_code=1,
    )


def test_compute_trend_falling():
    now = datetime(2026, 5, 20, 12, 0)
    current = _make_current(1013.2)
    readings = [
        (now - timedelta(hours=48), 1018.5),
        (now - timedelta(hours=24), 1017.0),
        (now - timedelta(hours=6), 1014.0),
    ]
    result = _compute_trend_from_readings(43.7, -79.4, current, readings)
    assert isinstance(result, PressureTrend)
    assert result.trend == "falling"
    assert result.delta_24h_hpa == round(1013.2 - 1017.0, 1)
    assert result.delta_48h_hpa == round(1013.2 - 1018.5, 1)


def test_compute_trend_rising():
    now = datetime(2026, 5, 20, 12, 0)
    current = _make_current(1018.0)
    readings = [
        (now - timedelta(hours=48), 1013.0),
        (now - timedelta(hours=24), 1015.5),
        (now - timedelta(hours=6), 1017.0),
    ]
    result = _compute_trend_from_readings(43.7, -79.4, current, readings)
    assert result.trend == "rising"
    assert result.delta_24h_hpa == round(1018.0 - 1015.5, 1)


def test_compute_trend_steady():
    now = datetime(2026, 5, 20, 12, 0)
    current = _make_current(1013.5)
    readings = [
        (now - timedelta(hours=48), 1013.0),
        (now - timedelta(hours=24), 1013.2),
        (now - timedelta(hours=6), 1013.4),
    ]
    result = _compute_trend_from_readings(43.7, -79.4, current, readings)
    assert result.trend == "steady"


def test_compute_trend_empty_readings_defaults_steady():
    current = _make_current(1013.2)
    result = _compute_trend_from_readings(43.7, -79.4, current, [])
    assert result.trend == "steady"
    assert result.delta_24h_hpa == 0.0
    assert result.delta_48h_hpa == 0.0


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


def test_cache_hit_skips_http(tmp_path):
    mock_get = MagicMock(return_value=_mock_response(_load("open_meteo_current.json")))
    with (
        patch("src.ingest.global.weather._CACHE_DIR", tmp_path),
        patch("httpx.get", mock_get),
        patch("time.sleep"),
    ):
        get_current_conditions(43.7, -79.4)
        get_current_conditions(43.7, -79.4)

    assert mock_get.call_count == 1


def test_stale_cache_triggers_refetch(tmp_path):
    mock_get = MagicMock(return_value=_mock_response(_load("open_meteo_current.json")))
    with (
        patch("src.ingest.global.weather._CACHE_DIR", tmp_path),
        patch("httpx.get", mock_get),
        patch("time.sleep"),
    ):
        get_current_conditions(43.7, -79.4)

        cache_file = next(tmp_path.glob("*.json"))
        old_time = time.time() - _TTL_CURRENT - 60
        os.utime(cache_file, (old_time, old_time))

        get_current_conditions(43.7, -79.4)

    assert mock_get.call_count == 2
