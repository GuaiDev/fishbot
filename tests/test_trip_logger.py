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


# ── parse_size_to_cm ────────────────────────────────────────────────────────


def test_parse_size_to_cm_bare_number_assumed_cm():
    from src.services.trip_logger import parse_size_to_cm

    assert parse_size_to_cm(35) == 35.0
    assert parse_size_to_cm(35.5) == 35.5
    assert parse_size_to_cm("35") == 35.0


def test_parse_size_to_cm_converts_inches():
    from src.services.trip_logger import parse_size_to_cm

    assert parse_size_to_cm("14in") == pytest.approx(35.56)
    assert parse_size_to_cm("14 inches") == pytest.approx(35.56)
    assert parse_size_to_cm('14"') == pytest.approx(35.56)


def test_parse_size_to_cm_explicit_cm_suffix():
    from src.services.trip_logger import parse_size_to_cm

    assert parse_size_to_cm("35cm") == 35.0
    assert parse_size_to_cm("35.5 cm") == 35.5


def test_parse_size_to_cm_invalid_or_empty_returns_none():
    from src.services.trip_logger import parse_size_to_cm

    assert parse_size_to_cm(None) is None
    assert parse_size_to_cm("") is None
    assert parse_size_to_cm("not a number") is None


# ── structured_catches (multi-catch logging UI) ──────────────────────────────


def test_structured_catch_merges_onto_matching_nl_species(db_conn):
    from src.services.trip_logger import log_session
    from src.storage.catches import get_catches_for_session

    parsed = {
        "date": "2026-06-01",
        "stops": [{"location_text": "Bronte Creek", "species_caught": ["smallmouth bass"]}],
    }
    structured = [{
        "species": "smallmouth bass", "count": 2, "biggest_size_cm": 35.0,
        "bait": "spinnerbait", "photo_path": None, "photo_url": None,
    }]

    result = log_session(parsed, db_conn, user_id=1, structured_catches=structured)

    catches = get_catches_for_session(db_conn, result["session_id"])
    assert len(catches) == 1
    c = catches[0]
    assert c["species"] == "smallmouth bass"
    assert c["count"] == 2
    assert c["biggest_size_cm"] == 35.0
    assert c["bait"] == "spinnerbait"
    # Merged rows still come from the NL/vision suggestion flow, so they're
    # unconfirmed like any NL-parsed catch.
    assert c["species_confirmed"] == 0
    assert len(result["pending_catches"]) == 1


def test_structured_catch_with_no_nl_match_becomes_own_row(db_conn):
    from src.services.trip_logger import log_session
    from src.storage.catches import get_catches_for_session

    parsed = {
        "date": "2026-06-01",
        "stops": [{"location_text": "Bronte Creek", "species_caught": ["creek chub"]}],
    }
    structured = [{
        "species": "rock bass", "count": 1, "biggest_size_cm": 20.0,
        "bait": "worm", "photo_path": None, "photo_url": None,
    }]

    result = log_session(parsed, db_conn, user_id=1, structured_catches=structured)

    catches = {c["species"]: c for c in get_catches_for_session(db_conn, result["session_id"])}
    assert set(catches) == {"creek chub", "rock bass"}
    # No photo to reconcile against — directly typed, trusted human input,
    # so it's already confirmed and never shows up as pending.
    assert catches["rock bass"]["species_confirmed"] == 1
    assert catches["rock bass"]["count"] == 1
    assert catches["rock bass"]["biggest_size_cm"] == 20.0
    assert catches["creek chub"]["species_confirmed"] == 0


def test_duplicate_species_structured_catches_get_separate_rows(db_conn):
    """Two catch cards for the same species (different sizes/bait) must not
    collapse into one row — the count stepper on a single card is how a user
    logs "N of the same fish"; two cards means two distinct catch events."""
    from src.services.trip_logger import log_session
    from src.storage.catches import get_catches_for_session

    parsed = {
        "date": "2026-06-01",
        "stops": [{"location_text": "Bronte Creek", "species_caught": ["smallmouth bass"]}],
    }
    structured = [
        {"species": "smallmouth bass", "count": 1, "biggest_size_cm": 35.0,
         "bait": "spinnerbait", "photo_path": None, "photo_url": None},
        {"species": "smallmouth bass", "count": 1, "biggest_size_cm": 25.0,
         "bait": "worm", "photo_path": None, "photo_url": None},
    ]

    result = log_session(parsed, db_conn, user_id=1, structured_catches=structured)

    catches = get_catches_for_session(db_conn, result["session_id"])
    assert len(catches) == 2
    sizes = sorted(c["biggest_size_cm"] for c in catches)
    assert sizes == [25.0, 35.0]


def test_structured_catches_empty_is_pure_nl_behavior(db_conn):
    """structured_catches=[] must produce byte-identical rows to omitting it."""
    from src.services.trip_logger import log_session
    from src.storage.catches import get_catches_for_session

    parsed = {
        "date": "2026-06-01",
        "stops": [{"location_text": "Bronte Creek", "species_caught": ["creek chub"]}],
    }

    result = log_session(parsed, db_conn, user_id=1, structured_catches=[])
    catches = get_catches_for_session(db_conn, result["session_id"])
    assert len(catches) == 1
    assert catches[0]["species"] == "creek chub"
    assert catches[0]["species_confirmed"] == 0
    assert catches[0]["count"] is None
    assert catches[0]["biggest_size_cm"] is None


def test_structured_catch_updates_personal_best(db_conn):
    from src.services.trip_logger import log_session
    from src.storage.catches import get_personal_best

    parsed = {
        "date": "2026-06-01",
        "stops": [{"location_text": "Bronte Creek", "species_caught": ["smallmouth bass"]}],
    }

    log_session(parsed, db_conn, user_id=1, structured_catches=[
        {"species": "smallmouth bass", "count": 1, "biggest_size_cm": 30.0,
         "bait": None, "photo_path": None, "photo_url": None},
    ])
    assert get_personal_best(db_conn, 1, "smallmouth bass") == 30.0

    # A smaller catch afterward must not overwrite the recorded best.
    parsed2 = {
        "date": "2026-06-02",
        "stops": [{"location_text": "Bronte Creek", "species_caught": ["smallmouth bass"]}],
    }
    log_session(parsed2, db_conn, user_id=1, structured_catches=[
        {"species": "smallmouth bass", "count": 1, "biggest_size_cm": 22.0,
         "bait": None, "photo_path": None, "photo_url": None},
    ])
    assert get_personal_best(db_conn, 1, "smallmouth bass") == 30.0

    # A bigger catch must update it.
    parsed3 = {
        "date": "2026-06-03",
        "stops": [{"location_text": "Bronte Creek", "species_caught": ["smallmouth bass"]}],
    }
    log_session(parsed3, db_conn, user_id=1, structured_catches=[
        {"species": "smallmouth bass", "count": 1, "biggest_size_cm": 38.0,
         "bait": None, "photo_path": None, "photo_url": None},
    ])
    assert get_personal_best(db_conn, 1, "smallmouth bass") == 38.0
