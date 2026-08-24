"""Tests for trip log → SDM presence pipeline."""

import json

import pytest
import sqlite_utils

from src.services.species_mapping import (
    common_to_scientific,
    scientific_to_common,
)

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_with_stops(tmp_path):
    """Minimal DB with stops table containing confirmed catches."""
    db = sqlite_utils.Database(tmp_path / "test.db")
    db["stops"].insert_all(
        [
            {
                "id": 1,
                "lat": 43.0,
                "lng": -80.0,
                "location_name": "Test Creek",
                "location_text": None,
                "species_caught": json.dumps(["creek chub", "pumpkinseed"]),
                "party_species_caught": json.dumps([]),
                "was_productive": 1,
                "technique": "ultralight",
                "gear": None,
                "water_level": None,
                "water_clarity": None,
                "weather_notes": None,
                "notes": None,
                "date": "2026-05-01",
                "date_approx": None,
            },
            {
                "id": 2,
                "lat": 43.1,
                "lng": -80.1,
                "location_name": "Blank Spot",
                "location_text": None,
                "species_caught": json.dumps([]),
                "party_species_caught": json.dumps([]),
                "was_productive": 0,  # blank — should NOT be included
                "technique": None,
                "gear": None,
                "water_level": None,
                "water_clarity": None,
                "weather_notes": None,
                "notes": None,
                "date": "2026-05-02",
                "date_approx": None,
            },
            {
                "id": 3,
                "lat": None,  # no coordinates — should NOT be included
                "lng": None,
                "location_name": "No Coords",
                "location_text": None,
                "species_caught": json.dumps(["creek chub"]),
                "party_species_caught": json.dumps([]),
                "was_productive": 1,
                "technique": None,
                "gear": None,
                "water_level": None,
                "water_clarity": None,
                "weather_notes": None,
                "notes": None,
                "date": "2026-05-03",
                "date_approx": None,
            },
        ]
    )
    return db


# ── mapping tests ──────────────────────────────────────────────────────────────


def test_exact_common_name_maps():
    result = common_to_scientific("creek chub")
    assert result == "Semotilus atromaculatus"


def test_uncertain_tag_stripped():
    result = common_to_scientific("creek chub (uncertain)")
    assert result == "Semotilus atromaculatus"


def test_unknown_name_returns_none():
    result = common_to_scientific("space fish")
    assert result is None


def test_reverse_mapping():
    result = scientific_to_common("Semotilus atromaculatus")
    assert result == "creek chub"


# ── trip log extraction tests ──────────────────────────────────────────────────


def test_trip_log_points_extracted(db_with_stops):
    """Productive stops with coords should appear as presence points."""
    rows = db_with_stops.execute("""
        SELECT st.lat, st.lng
        FROM stops st, json_each(st.species_caught) je
        WHERE LOWER(je.value) LIKE ?
          AND st.lat IS NOT NULL AND st.lng IS NOT NULL
          AND st.was_productive = 1
    """, ["%creek chub%"]).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == pytest.approx(43.0)
    assert rows[0][1] == pytest.approx(-80.0)


def test_blank_stop_excluded(db_with_stops):
    """Stops with was_productive=0 must not contribute presence points."""
    rows = db_with_stops.execute("""
        SELECT COUNT(*)
        FROM stops st, json_each(st.species_caught) je
        WHERE LOWER(je.value) LIKE ?
          AND st.lat IS NOT NULL AND st.lng IS NOT NULL
          AND st.was_productive = 1
    """, ["%creek chub%"]).fetchone()
    # Only stop #1 qualifies; stop #2 is blank; stop #3 has no coords
    assert rows[0] == 1


def test_no_coord_stop_excluded(db_with_stops):
    """Stops without lat/lng must not appear in presence results."""
    rows = db_with_stops.execute("""
        SELECT st.lat, st.lng
        FROM stops st, json_each(st.species_caught) je
        WHERE LOWER(je.value) LIKE ?
          AND st.lat IS NOT NULL AND st.lng IS NOT NULL
          AND st.was_productive = 1
    """, ["%creek chub%"]).fetchall()
    for lat, lng in rows:
        assert lat is not None
        assert lng is not None
