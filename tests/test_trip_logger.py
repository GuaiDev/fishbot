"""Tests for trip_logger service functions."""
import json

import pytest

from src.storage.database import get_db


@pytest.fixture
def db_conn(tmp_path):
    return get_db(path=tmp_path / "test.db")


def _insert_stop(db, location_name, location_text, species, date="2025-05-15",
                 lat=None, lng=None):
    """Insert a session + stop directly, bypassing log_session enrichment."""
    session_id = db["sessions"].insert({
        "date": date,
        "date_approx": None,
        "overall_notes": None,
    }).last_pk
    db["stops"].insert({
        "session_id": session_id,
        "location_text": location_text,
        "location_name": location_name,
        "lat": lat,
        "lng": lng,
        "ohn_segment_id": None,
        "location_method": "text_only",
        "location_confidence": None,
        "species_caught": json.dumps(species),
        "was_productive": 1 if species else 0,
        "technique": None,
        "gear": None,
        "water_level": None,
        "water_clarity": None,
        "water_temp_c": None,
        "weather_notes": None,
        "notes": None,
    })
    return session_id


def test_get_trips_at_location_by_name(db_conn):
    from src.services.trip_logger import get_trips_at_location

    _insert_stop(
        db_conn,
        location_name="Byng Island Conservation Area",
        location_text="Byng Island Conservation Area",
        species=["channel catfish"],
        date="2025-05-15",
    )

    result = get_trips_at_location(db_conn, location_query="Byng Island")
    assert "channel catfish" in result
    assert "No logged trips" not in result


def test_get_trips_at_location_no_match(db_conn):
    from src.services.trip_logger import get_trips_at_location

    result = get_trips_at_location(db_conn, location_query="Nonexistent Lake")
    assert "No logged trips" in result or "No trips logged" in result


def test_get_trips_at_location_multiple_visits(db_conn):
    from src.services.trip_logger import get_trips_at_location

    _insert_stop(db_conn, "Byng Island", "Byng Island", ["channel catfish"], date="2025-05-10")
    _insert_stop(db_conn, "Byng Island", "Byng Island", ["bowfin", "channel catfish"], date="2025-06-01")

    result = get_trips_at_location(db_conn, location_query="Byng Island")
    assert "2 visits" in result
    assert "bowfin" in result
    assert "2025-05-10" in result


def test_get_trips_at_location_proximity(db_conn):
    from src.services.trip_logger import get_trips_at_location

    _insert_stop(
        db_conn,
        location_name="Willoway Brook",
        location_text="Willoway Brook",
        species=["rainbow darter"],
        lat=43.417,
        lng=-79.774,
    )

    # Query by nearby coordinates, not name
    result = get_trips_at_location(db_conn, lat=43.418, lng=-79.775, radius_km=2.0)
    assert "rainbow darter" in result
    assert "No logged trips" not in result


def test_get_trips_at_location_blank_stop(db_conn):
    from src.services.trip_logger import get_trips_at_location

    _insert_stop(db_conn, "Bronte Creek", "Bronte Creek at Burloak", species=[])

    result = get_trips_at_location(db_conn, location_query="Bronte Creek")
    assert "no fish (blank)" in result
    assert "No logged trips" not in result


def test_log_session_inserts_one_catch_row_per_species(db_conn):
    from src.services.trip_logger import log_session
    from src.storage.catches import get_catches_for_session

    parsed = {
        "date": "2026-06-01",
        "stops": [{
            "location_text": "Bronte Creek",
            "species_caught": ["creek chub", "rock bass"],
            "photo_url": "/photos/abc123.jpg",
            "photo_lat": 43.4,
            "photo_lng": -79.7,
            "photo_taken_at": "2026-06-01T14:00:00",
        }],
    }

    result = log_session(parsed, db_conn, user_id=1)

    catches = get_catches_for_session(db_conn, result["session_id"])
    assert {c["species"] for c in catches} == {"creek chub", "rock bass"}
    assert all(c["photo_url"] == "/photos/abc123.jpg" for c in catches)
    assert all(c["photo_lat"] == 43.4 for c in catches)


def test_log_session_no_species_inserts_no_catches(db_conn):
    from src.services.trip_logger import log_session
    from src.storage.catches import get_catches_for_session

    parsed = {
        "date": "2026-06-01",
        "stops": [{"location_text": "Bronte Creek", "species_caught": []}],
    }

    result = log_session(parsed, db_conn, user_id=1)
    assert get_catches_for_session(db_conn, result["session_id"]) == []
