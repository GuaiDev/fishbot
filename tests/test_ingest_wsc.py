"""Tests for WSC hydrometric ingest module."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def _make_mock_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


# ── fetch_nearby_stations ─────────────────────────────────────────────────────

def test_fetch_stations_returns_list(tmp_path):
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    fixture = _load_fixture("wsc_stations.json")

    with patch("httpx.get", return_value=_make_mock_response(fixture)), \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        stations = wsc.fetch_nearby_stations(43.65, -79.38)

    assert len(stations) == 3
    ids = [s["STATION_NUMBER"] for s in stations]
    assert "02HB001" in ids
    assert "02HC024" in ids
    assert "02HC003" in ids


def test_fetch_stations_empty_response(tmp_path):
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    with patch("httpx.get", return_value=_make_mock_response({"features": []})), \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        stations = wsc.fetch_nearby_stations(43.65, -79.38)

    assert stations == []


# ── fetch_station_reading ─────────────────────────────────────────────────────

def test_fetch_station_reading_parses_correctly(tmp_path):
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    fixture = _load_fixture("wsc_reading.json")

    with patch("httpx.get", return_value=_make_mock_response(fixture)), \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        reading = wsc.fetch_station_reading("02HB001", 43.5833, -79.7167)

    assert reading is not None
    assert reading.station_id == "02HB001"
    assert reading.station_name == "CREDIT RIVER AT STREETSVILLE"
    assert reading.river_name == "Credit River"
    assert reading.water_level_m == pytest.approx(0.523, abs=0.001)
    assert reading.discharge_cms == pytest.approx(18.3, abs=0.01)
    assert reading.jurisdiction == "CA-ON"


def test_trend_rising(tmp_path):
    """Fixture has level rising 0.183m and discharge rising 46% over 3hr."""
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    fixture = _load_fixture("wsc_reading.json")

    with patch("httpx.get", return_value=_make_mock_response(fixture)), \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        reading = wsc.fetch_station_reading("02HB001", 43.5833, -79.7167)

    assert reading is not None
    assert reading.level_trend == "rising"
    assert reading.discharge_trend == "rising"


def test_trend_stable(tmp_path):
    """Flat readings should produce stable trend."""
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    flat_level = 0.450
    flat_discharge = 16.0
    features = [
        {
            "type": "Feature",
            "geometry": None,
            "properties": {
                "STATION_NUMBER": "02HB001",
                "STATION_NAME": "CREDIT RIVER AT STREETSVILLE",
                "DATETIME": f"2026-05-22T{11 + i}:00:00Z",
                "LEVEL": flat_level,
                "DISCHARGE": flat_discharge,
                "LEVEL_SYMBOL_EN": None,
            },
        }
        for i in range(4)
    ]
    data = {"type": "FeatureCollection", "features": features}

    with patch("httpx.get", return_value=_make_mock_response(data)), \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        reading = wsc.fetch_station_reading("02HB001", 43.5833, -79.7167)

    assert reading is not None
    assert reading.level_trend == "stable"
    assert reading.discharge_trend == "stable"


def test_trend_falling(tmp_path):
    """Readings dropping >0.05m and >2% should produce falling trend."""
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    features = [
        {
            "type": "Feature",
            "geometry": None,
            "properties": {
                "STATION_NUMBER": "02HB001",
                "STATION_NAME": "CREDIT RIVER AT STREETSVILLE",
                "DATETIME": "2026-05-22T11:00:00Z",
                "LEVEL": 0.700,
                "DISCHARGE": 30.0,
                "LEVEL_SYMBOL_EN": None,
            },
        },
        {
            "type": "Feature",
            "geometry": None,
            "properties": {
                "STATION_NUMBER": "02HB001",
                "STATION_NAME": "CREDIT RIVER AT STREETSVILLE",
                "DATETIME": "2026-05-22T14:00:00Z",
                "LEVEL": 0.580,
                "DISCHARGE": 22.0,
                "LEVEL_SYMBOL_EN": None,
            },
        },
    ]
    data = {"type": "FeatureCollection", "features": features}

    with patch("httpx.get", return_value=_make_mock_response(data)), \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        reading = wsc.fetch_station_reading("02HB001", 43.5833, -79.7167)

    assert reading is not None
    assert reading.level_trend == "falling"
    assert reading.discharge_trend == "falling"


def test_returns_none_when_no_features(tmp_path):
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    with patch("httpx.get", return_value=_make_mock_response({"features": []})), \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        reading = wsc.fetch_station_reading("02HB001", 43.5833, -79.7167)

    assert reading is None


def test_returns_none_when_all_values_null(tmp_path):
    """Gauge with both level and discharge null → offline → None."""
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    features = [
        {
            "type": "Feature",
            "geometry": None,
            "properties": {
                "STATION_NUMBER": "02HB001",
                "STATION_NAME": "CREDIT RIVER AT STREETSVILLE",
                "DATETIME": "2026-05-22T14:00:00Z",
                "LEVEL": None,
                "DISCHARGE": None,
                "LEVEL_SYMBOL_EN": None,
            },
        }
    ]
    data = {"type": "FeatureCollection", "features": features}

    with patch("httpx.get", return_value=_make_mock_response(data)), \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        reading = wsc.fetch_station_reading("02HB001", 43.5833, -79.7167)

    assert reading is None


def test_null_discharge_readings_handled_gracefully(tmp_path):
    """Null DISCHARGE on some readings should not prevent trend computation."""
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    fixture = _load_fixture("wsc_reading.json")

    with patch("httpx.get", return_value=_make_mock_response(fixture)), \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        reading = wsc.fetch_station_reading("02HB001", 43.5833, -79.7167)

    # Fixture has 2 null-discharge readings but the rest are valid
    assert reading is not None
    assert reading.discharge_cms is not None


# ── caching ───────────────────────────────────────────────────────────────────

def test_cache_hit_skips_http(tmp_path):
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    fixture = _load_fixture("wsc_stations.json")

    with patch("httpx.get", return_value=_make_mock_response(fixture)) as mock_get, \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        wsc.fetch_nearby_stations(43.65, -79.38)
        wsc.fetch_nearby_stations(43.65, -79.38)  # second call → cache hit

    assert mock_get.call_count == 1


def test_cache_miss_writes_file(tmp_path):
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    fixture = _load_fixture("wsc_stations.json")

    with patch("httpx.get", return_value=_make_mock_response(fixture)), \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        wsc.fetch_nearby_stations(43.65, -79.38)

    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1


def test_stale_cache_triggers_refetch(tmp_path):
    import importlib
    wsc = importlib.import_module("src.ingest.global.wsc")

    fixture = _load_fixture("wsc_stations.json")

    with patch("httpx.get", return_value=_make_mock_response(fixture)) as mock_get, \
         patch.object(wsc, "_CACHE_DIR", tmp_path):
        wsc.fetch_nearby_stations(43.65, -79.38)

        # Age the cache file beyond TTL
        cache_file = next(tmp_path.glob("*.json"))
        old_time = time.time() - wsc._TTL_STATIONS - 1
        import os
        os.utime(cache_file, (old_time, old_time))

        wsc.fetch_nearby_stations(43.65, -79.38)

    assert mock_get.call_count == 2
