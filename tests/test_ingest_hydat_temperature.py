"""Tests for HYDAT stream temperature extraction. No live downloads."""

import importlib
import sqlite3
from pathlib import Path

import pytest

from src.models.stream_temperature import StreamTemperatureReading, StreamTemperatureSummary
from src.storage.database import get_db
from src.storage.stream_temperature import (
    is_data_loaded,
    query_temperature_summaries,
    upsert_temperature_summaries,
)

_hydat = importlib.import_module("src.ingest.global.hydat_temperature")
_extract_from_hydat = _hydat._extract_from_hydat
_compute_monthly_stats = _hydat._compute_monthly_stats
_classify_regime = _hydat._classify_regime
_species_notes = _hydat._species_notes

# Toronto home coordinates used in all spatial tests
_LAT = 43.6532
_LNG = -79.3832

# Expected values derived from fixture data (see _build_hydat_fixture below)
# Station 1 (02HC003): July MAX=16 MIN=10 → mean=13; Aug MAX=18 MIN=12 → mean=15
#   summer_mean = (13×5 + 15×5) / 10 = 14.0 → coldwater
# Station 2 (02GA031): July MAX=24 MIN=16 → mean=20; Aug MAX=26 MIN=18 → mean=22
#   summer_mean = 21.0 → coolwater
# Station 3 (02HC005): July MAX=28 MIN=20 → mean=24; Aug MAX=30 MIN=22 → mean=26
#   summer_mean = 25.0 → warmwater
# Station 4 (02AB001): at ~220km — outside any reasonable radius


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_MAX_COLS = ", ".join(f"MAX{d}" for d in range(1, 32))
_MIN_COLS = ", ".join(f"MIN{d}" for d in range(1, 32))
_INSERT_SQL = (
    f"INSERT INTO DLY_TEMPERATURES "
    f"(STATION_NUMBER, YEAR, MONTH, FULL_MONTH, NO_DATES, {_MAX_COLS}, {_MIN_COLS}) "
    f"VALUES (?, ?, ?, ?, ?, {', '.join(['?'] * 31)}, {', '.join(['?'] * 31)})"
)
_DAYS = 15  # days of data per fixture month


def _build_hydat_fixture(conn: sqlite3.Connection) -> None:
    max_col_defs = ", ".join(f"MAX{d} REAL" for d in range(1, 32))
    min_col_defs = ", ".join(f"MIN{d} REAL" for d in range(1, 32))

    conn.execute("""
        CREATE TABLE STATIONS (
            STATION_NUMBER TEXT PRIMARY KEY,
            STATION_NAME TEXT,
            PROV_TERR_STATE_LOC TEXT,
            HYD_STATUS TEXT,
            LATITUDE REAL,
            LONGITUDE REAL
        )
    """)
    conn.execute(f"""
        CREATE TABLE DLY_TEMPERATURES (
            STATION_NUMBER TEXT NOT NULL,
            YEAR INTEGER NOT NULL,
            MONTH INTEGER NOT NULL,
            FULL_MONTH INTEGER,
            NO_DATES INTEGER,
            {max_col_defs},
            {min_col_defs},
            PRIMARY KEY (STATION_NUMBER, YEAR, MONTH)
        )
    """)

    stations = [
        ("02HC003", "DON RIVER AT THORNHILL",   "ON", "A", 43.805, -79.420),
        ("02GA031", "HUMBER RIVER AT WESTON",   "ON", "A", 43.700, -79.515),
        ("02HC005", "ROUGE RIVER AT MARKHAM",   "ON", "A", 43.877, -79.260),
        ("02AB001", "DISTANT CREEK",             "ON", "A", 44.800, -81.500),
    ]
    conn.executemany("INSERT INTO STATIONS VALUES (?, ?, ?, ?, ?, ?)", stations)

    # Temperature configs: station_id → {month: (max_val, min_val)}
    temp_configs = [
        ("02HC003", {7: (16.0, 10.0), 8: (18.0, 12.0)}),
        ("02GA031", {7: (24.0, 16.0), 8: (26.0, 18.0)}),
        ("02HC005", {7: (28.0, 20.0), 8: (30.0, 22.0)}),
        ("02AB001", {7: (22.0, 14.0), 8: (24.0, 16.0)}),
    ]

    for station_id, month_cfg in temp_configs:
        for year in range(2018, 2023):
            for month, (max_val, min_val) in month_cfg.items():
                max_vals = [max_val if d <= _DAYS else None for d in range(1, 32)]
                min_vals = [min_val if d <= _DAYS else None for d in range(1, 32)]
                conn.execute(_INSERT_SQL, [station_id, year, month, 0, _DAYS] + max_vals + min_vals)

    conn.commit()


@pytest.fixture()
def hydat_conn(tmp_path: Path):
    db_path = tmp_path / "hydat_test.db"
    conn = sqlite3.connect(str(db_path))
    _build_hydat_fixture(conn)
    yield conn
    conn.close()


@pytest.fixture()
def app_db(tmp_path: Path):
    return get_db(path=tmp_path / "fishing_test.db")


# ---------------------------------------------------------------------------
# Unit: _compute_monthly_stats
# ---------------------------------------------------------------------------

def _make_temp_row(year, month, max_val, min_val, days=15):
    """Build a tuple matching _TEMP_QUERY row layout for a uniform month."""
    maxes = [max_val if d <= days else None for d in range(1, 32)]
    mins = [min_val if d <= days else None for d in range(1, 32)]
    return (year, month, days) + tuple(maxes) + tuple(mins)


def test_compute_monthly_stats_mean():
    row = _make_temp_row(2022, 7, max_val=20.0, min_val=10.0)
    mean, _, _, days = _compute_monthly_stats(row)
    assert mean == pytest.approx(15.0)
    assert days == 15


def test_compute_monthly_stats_max():
    row = _make_temp_row(2022, 7, max_val=20.0, min_val=10.0)
    _, max_c, _, _ = _compute_monthly_stats(row)
    assert max_c == pytest.approx(20.0)


def test_compute_monthly_stats_min():
    row = _make_temp_row(2022, 7, max_val=20.0, min_val=10.0)
    _, _, min_c, _ = _compute_monthly_stats(row)
    assert min_c == pytest.approx(10.0)


def test_compute_monthly_stats_all_null_returns_zeros():
    maxes = [None] * 31
    mins = [None] * 31
    row = (2022, 7, 0) + tuple(maxes) + tuple(mins)
    mean, max_c, min_c, days = _compute_monthly_stats(row)
    assert mean is None
    assert days == 0


def test_compute_monthly_stats_partial_days():
    row = _make_temp_row(2022, 7, max_val=24.0, min_val=16.0, days=5)
    _, _, _, days = _compute_monthly_stats(row)
    assert days == 5


# ---------------------------------------------------------------------------
# Unit: _classify_regime
# ---------------------------------------------------------------------------

def test_classify_regime_coldwater():
    assert _classify_regime(14.0) == "coldwater"


def test_classify_regime_coldwater_boundary():
    assert _classify_regime(17.9) == "coldwater"


def test_classify_regime_coolwater_lower():
    assert _classify_regime(18.0) == "coolwater"


def test_classify_regime_coolwater_upper():
    assert _classify_regime(23.0) == "coolwater"


def test_classify_regime_warmwater():
    assert _classify_regime(23.1) == "warmwater"


def test_classify_regime_unknown_when_none():
    assert _classify_regime(None) == "unknown"


# ---------------------------------------------------------------------------
# Unit: _species_notes
# ---------------------------------------------------------------------------

def test_species_notes_coldwater_mentions_salmonids():
    notes = _species_notes("coldwater")
    assert "salmonid" in notes.lower() or "trout" in notes.lower()


def test_species_notes_coolwater_mentions_walleye():
    notes = _species_notes("coolwater")
    assert "walleye" in notes.lower()


def test_species_notes_warmwater_excludes_salmonids():
    notes = _species_notes("warmwater")
    assert "salmonid" in notes.lower()  # mentioned as "too warm for"


def test_species_notes_warmwater_mentions_bass():
    notes = _species_notes("warmwater")
    assert "bass" in notes.lower()


def test_species_notes_unknown_returns_string():
    notes = _species_notes("unknown")
    assert len(notes) > 0


# ---------------------------------------------------------------------------
# Integration: _extract_from_hydat
# ---------------------------------------------------------------------------

def test_extract_returns_three_summaries_within_100km(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    assert len(summaries) == 3


def test_extract_distant_station_excluded(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    ids = {s.station_id for s in summaries}
    assert "02AB001" not in ids


def test_extract_all_jurisdictions_ca_on(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    assert all(s.jurisdiction == "CA-ON" for s in summaries)


def test_extract_coldwater_regime(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    s = next(s for s in summaries if s.station_id == "02HC003")
    assert s.thermal_regime == "coldwater"


def test_extract_coolwater_regime(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    s = next(s for s in summaries if s.station_id == "02GA031")
    assert s.thermal_regime == "coolwater"


def test_extract_warmwater_regime(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    s = next(s for s in summaries if s.station_id == "02HC005")
    assert s.thermal_regime == "warmwater"


def test_extract_coldwater_summer_mean(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    s = next(s for s in summaries if s.station_id == "02HC003")
    assert s.summer_mean_c == pytest.approx(14.0)


def test_extract_coolwater_summer_mean(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    s = next(s for s in summaries if s.station_id == "02GA031")
    assert s.summer_mean_c == pytest.approx(21.0)


def test_extract_warmwater_summer_mean(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    s = next(s for s in summaries if s.station_id == "02HC005")
    assert s.summer_mean_c == pytest.approx(25.0)


def test_extract_years_of_data(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    assert all(s.years_of_data == 5 for s in summaries)


def test_extract_species_notes_populated(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    assert all(len(s.species_notes) > 0 for s in summaries)


def test_extract_readings_count(hydat_conn):
    readings, _ = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    # 3 stations × 5 years × 2 months = 30 readings
    assert len(readings) == 30


def test_extract_readings_are_stream_temperature_reading_models(hydat_conn):
    readings, _ = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    assert all(isinstance(r, StreamTemperatureReading) for r in readings)


def test_extract_summaries_are_summary_models(hydat_conn):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    assert all(isinstance(s, StreamTemperatureSummary) for s in summaries)


def test_extract_small_radius_excludes_far_station(hydat_conn):
    # Station 02HC005 (Rouge at Markham) is ~27km — use 20km to exclude it
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=20)
    ids = {s.station_id for s in summaries}
    assert "02HC005" not in ids
    # Stations 1 and 2 at ~17km and ~11km should still be present
    assert "02HC003" in ids
    assert "02GA031" in ids


def test_extract_missing_temperature_table_returns_empty(tmp_path):
    db_path = tmp_path / "no_temp.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE STATIONS (
            STATION_NUMBER TEXT PRIMARY KEY,
            STATION_NAME TEXT,
            PROV_TERR_STATE_LOC TEXT,
            HYD_STATUS TEXT,
            LATITUDE REAL,
            LONGITUDE REAL
        )
    """)
    conn.execute(
        "INSERT INTO STATIONS VALUES ('02HC003', 'DON RIVER', 'ON', 'A', 43.805, -79.420)"
    )
    conn.commit()
    readings, summaries = _extract_from_hydat(conn, _LAT, _LNG, radius_km=100)
    conn.close()
    assert readings == []
    assert summaries == []


def test_extract_no_stations_returns_empty(hydat_conn):
    # Use coordinates far from Ontario (Pacific coast)
    readings, summaries = _extract_from_hydat(hydat_conn, 49.2827, -123.1207, radius_km=50)
    assert readings == []
    assert summaries == []


# ---------------------------------------------------------------------------
# Integration: storage round-trip
# ---------------------------------------------------------------------------

def test_is_data_loaded_false_when_empty(app_db):
    assert is_data_loaded(app_db) is False


def test_is_data_loaded_true_after_upsert(hydat_conn, app_db):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    upsert_temperature_summaries(app_db, summaries)
    assert is_data_loaded(app_db) is True


def test_query_summaries_returns_correct_count(hydat_conn, app_db):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    upsert_temperature_summaries(app_db, summaries)
    results = query_temperature_summaries(app_db, _LAT, _LNG, radius_km=100)
    assert len(results) == 3


def test_query_summaries_radius_filter(hydat_conn, app_db):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    upsert_temperature_summaries(app_db, summaries)
    results = query_temperature_summaries(app_db, _LAT, _LNG, radius_km=20)
    ids = {s.station_id for s in results}
    assert "02HC005" not in ids


def test_query_summaries_sorted_by_distance(hydat_conn, app_db):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    upsert_temperature_summaries(app_db, summaries)
    results = query_temperature_summaries(app_db, _LAT, _LNG, radius_km=100)
    # Humber at Weston (~11km) should be closer than Don at Thornhill (~17km)
    assert results[0].station_id == "02GA031"


def test_upsert_is_idempotent(hydat_conn, app_db):
    _, summaries = _extract_from_hydat(hydat_conn, _LAT, _LNG, radius_km=100)
    upsert_temperature_summaries(app_db, summaries)
    upsert_temperature_summaries(app_db, summaries)  # second upsert
    count = app_db.execute("SELECT COUNT(*) FROM stream_temperature_summaries").fetchone()[0]
    assert count == 3
