"""Tests for trip CRUD."""

from datetime import date

from src.models.catch import Catch
from src.models.trip import Trip
from src.storage.database import get_db
from src.storage.trips import get_trip, insert_trip, recent_trips


def _trip(d: str, location: str, status: str = "completed") -> Trip:
    return Trip(
        date=date.fromisoformat(d),
        jurisdiction="CA-ON",
        location_name=location,
        status=status,
        species_caught=[Catch(species="smallmouth bass", length_cm=30.0)],
    )


def test_insert_creates_id(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    trip_id = insert_trip(db, _trip("2026-05-01", "Lake Simcoe"))
    assert isinstance(trip_id, int)
    assert trip_id > 0


def test_get_round_trips_a_trip(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    trip_id = insert_trip(db, _trip("2026-05-01", "Credit River"))
    fetched = get_trip(db, trip_id)
    assert fetched is not None
    assert fetched.location_name == "Credit River"
    assert fetched.jurisdiction == "CA-ON"
    assert len(fetched.species_caught) == 1
    assert fetched.species_caught[0].species == "smallmouth bass"
    assert fetched.species_caught[0].length_cm == 30.0


def test_get_returns_none_for_missing(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    assert get_trip(db, 999) is None


def test_recent_trips_orders_by_date_desc(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    insert_trip(db, _trip("2026-05-01", "Old Trip"))
    insert_trip(db, _trip("2026-05-15", "New Trip"))
    insert_trip(db, _trip("2026-05-08", "Mid Trip"))
    trips = recent_trips(db, limit=10)
    assert [t.location_name for t in trips] == ["New Trip", "Mid Trip", "Old Trip"]


def test_recent_trips_respects_limit(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    for i in range(5):
        insert_trip(db, _trip(f"2026-05-{i+1:02d}", f"Trip {i}"))
    assert len(recent_trips(db, limit=3)) == 3


def test_recent_excludes_planned_trips_by_default(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    insert_trip(db, _trip("2026-05-01", "Completed One"))
    insert_trip(db, _trip("2026-06-01", "Planned One", status="planned"))
    locations = [t.location_name for t in recent_trips(db)]
    assert "Completed One" in locations
    assert "Planned One" not in locations
