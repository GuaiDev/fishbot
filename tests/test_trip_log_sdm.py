"""Tests for trip log → SDM presence pipeline."""

import json

import pytest
import sqlite_utils

from src.services.sdm_training import trip_log_presence_stops
from src.services.species_mapping import (
    common_to_scientific,
    scientific_to_common,
)

CREEK_CHUB = "Semotilus atromaculatus"

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
                "location_name": "Unproductive Stop",
                "location_text": None,
                # Species logged but the stop was marked unproductive: only the
                # was_productive clause can exclude this row.
                "species_caught": json.dumps(["creek chub"]),
                "party_species_caught": json.dumps([]),
                "was_productive": 0,
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
                # Half-coordinates, one row per side: with both NULL either
                # clause alone would exclude the stop and dropping one would
                # go unnoticed.
                "id": 3,
                "lat": None,
                "lng": -80.3,
                "location_name": "No Latitude",
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
            {
                "id": 4,
                "lat": 43.4,
                "lng": None,
                "location_name": "No Longitude",
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
                "date": "2026-05-04",
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
    stops = trip_log_presence_stops(CREEK_CHUB, db_with_stops)
    assert [stop_id for stop_id, _lat, _lng in stops] == [1]
    _stop_id, lat, lng = stops[0]
    assert lat == pytest.approx(43.0)
    assert lng == pytest.approx(-80.0)


def test_unproductive_stop_excluded(db_with_stops):
    """Stops with was_productive=0 must not contribute presence points."""
    ids = {stop_id for stop_id, _lat, _lng in trip_log_presence_stops(CREEK_CHUB, db_with_stops)}
    assert 2 not in ids


def test_no_coord_stop_excluded(db_with_stops):
    """Stops missing either coordinate must not appear in presence results."""
    ids = {stop_id for stop_id, _lat, _lng in trip_log_presence_stops(CREEK_CHUB, db_with_stops)}
    assert 3 not in ids  # lat NULL
    assert 4 not in ids  # lng NULL


def test_unmapped_species_yields_nothing(db_with_stops):
    """A species with no common-name mapping matches no stops."""
    assert trip_log_presence_stops("Ghostus fictus", db_with_stops) == []
