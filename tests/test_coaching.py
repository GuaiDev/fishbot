import json

import pytest
from sqlite_utils import Database

from src.storage.database import ensure_schema


@pytest.fixture
def db_conn(tmp_path):
    db = Database(tmp_path / "test.db")
    ensure_schema(db)
    return db


def test_species_coaching_no_data(db_conn):
    """Coaching with no logged catches returns honest response."""
    from src.services.coaching import get_species_coaching

    result = get_species_coaching(db_conn, "madtom")
    assert isinstance(result, str)
    assert len(result) > 50
    assert "no" in result.lower() or "none" in result.lower() or "haven't" in result.lower()


def test_location_coaching_no_data(db_conn):
    """Location coaching with no data returns informative message."""
    from src.services.coaching import get_location_coaching

    result = get_location_coaching(db_conn, "Nonexistent Creek")
    assert "No logged trips" in result


def test_species_coaching_with_data(db_conn):
    """Coaching with logged data returns substantive response."""
    from src.services.coaching import get_species_coaching

    db_conn["sessions"].insert({"date": "2025-06-14", "overall_notes": None})
    session_id = db_conn.execute("SELECT MAX(id) FROM sessions").fetchone()[0]
    db_conn["stops"].insert({
        "session_id": session_id,
        "location_text": "Byng Island",
        "location_name": "Byng Island",
        "species_caught": json.dumps(["channel catfish"]),
        "party_species_caught": json.dumps([]),
        "was_productive": 1,
        "technique": "Santee Cooper rig",
        "gear": "half chub cutbait, 3/0 circle hook",
        "water_level": "normal",
        "water_clarity": "turbid",
        "notes": "5lb channel cat at 10am",
    })

    result = get_species_coaching(
        db_conn, "channel catfish", "How do I find bigger fish?"
    )
    assert isinstance(result, str)
    assert len(result) > 100
    assert (
        "byng" in result.lower()
        or "catfish" in result.lower()
        or "santee" in result.lower()
    )
