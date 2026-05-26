"""Tests for the StreamTemperatureReading and StreamTemperatureSummary Pydantic models."""

import pytest
from pydantic import ValidationError

from src.models.stream_temperature import StreamTemperatureReading, StreamTemperatureSummary


def _make_reading(**kwargs) -> StreamTemperatureReading:
    defaults = dict(
        station_id="02HC003",
        station_name="DON RIVER AT THORNHILL",
        lat=43.805,
        lng=-79.420,
        jurisdiction="CA-ON",
        year=2022,
        month=7,
        mean_temp_c=14.0,
        max_temp_c=18.0,
        min_temp_c=10.0,
        days_measured=15,
    )
    return StreamTemperatureReading(**{**defaults, **kwargs})


def _make_summary(**kwargs) -> StreamTemperatureSummary:
    defaults = dict(
        station_id="02HC003",
        station_name="DON RIVER AT THORNHILL",
        lat=43.805,
        lng=-79.420,
        jurisdiction="CA-ON",
        summer_mean_c=14.0,
        summer_max_c=17.0,
        thermal_regime="coldwater",
        years_of_data=5,
        species_notes="Summer temps support brook trout, lake trout, and other salmonids.",
    )
    return StreamTemperatureSummary(**{**defaults, **kwargs})


# --- StreamTemperatureReading ---


def test_reading_valid():
    r = _make_reading()
    assert r.station_id == "02HC003"
    assert r.jurisdiction == "CA-ON"
    assert r.year == 2022
    assert r.month == 7


def test_reading_station_name_nullable():
    r = _make_reading(station_name=None)
    assert r.station_name is None


def test_reading_lat_lng_nullable():
    r = _make_reading(lat=None, lng=None)
    assert r.lat is None
    assert r.lng is None


def test_reading_mean_temp_nullable():
    r = _make_reading(mean_temp_c=None)
    assert r.mean_temp_c is None


def test_reading_max_temp_nullable():
    r = _make_reading(max_temp_c=None)
    assert r.max_temp_c is None


def test_reading_min_temp_nullable():
    r = _make_reading(min_temp_c=None)
    assert r.min_temp_c is None


def test_reading_days_measured_nullable():
    r = _make_reading(days_measured=None)
    assert r.days_measured is None


def test_reading_negative_temp_accepted():
    r = _make_reading(mean_temp_c=-5.0, min_temp_c=-10.0, max_temp_c=-2.0)
    assert r.mean_temp_c == -5.0


# --- StreamTemperatureSummary ---


def test_summary_valid():
    s = _make_summary()
    assert s.station_id == "02HC003"
    assert s.thermal_regime == "coldwater"
    assert s.years_of_data == 5


def test_summary_all_regimes_valid():
    for regime in ("coldwater", "coolwater", "warmwater", "unknown"):
        s = _make_summary(thermal_regime=regime)
        assert s.thermal_regime == regime


def test_summary_invalid_regime_rejected():
    with pytest.raises(ValidationError):
        _make_summary(thermal_regime="tepid")


def test_summary_summer_mean_nullable():
    s = _make_summary(summer_mean_c=None)
    assert s.summer_mean_c is None


def test_summary_summer_max_nullable():
    s = _make_summary(summer_max_c=None)
    assert s.summer_max_c is None


def test_summary_lat_lng_nullable():
    s = _make_summary(lat=None, lng=None)
    assert s.lat is None
    assert s.lng is None


def test_summary_station_name_nullable():
    s = _make_summary(station_name=None)
    assert s.station_name is None


def test_summary_years_of_data_zero_valid():
    s = _make_summary(years_of_data=0)
    assert s.years_of_data == 0
