import json

import pytest

from src.storage.database import get_db


@pytest.fixture
def db_conn(tmp_path):
    # get_db() applies ensure_schema + every migration, matching production.
    # ensure_schema() alone omits user_id on stops/sessions, which hid the
    # cross-user data leak these tests now cover.
    return get_db(tmp_path / "test.db")


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


def _insert_stop(db, user_id: int, location: str, species: list[str]) -> None:
    db["sessions"].insert({"date": "2025-06-14", "overall_notes": None, "user_id": user_id})
    session_id = db.execute("SELECT MAX(id) FROM sessions").fetchone()[0]
    db["stops"].insert({
        "session_id": session_id,
        "user_id": user_id,
        "location_text": location,
        "location_name": location,
        "species_caught": json.dumps(species),
        "party_species_caught": json.dumps([]),
        "was_productive": 1,
        "technique": "Santee Cooper rig",
        "gear": "cutbait",
        "notes": f"logged by user {user_id}",
    })


def test_location_coaching_excludes_other_users(db_conn):
    """A user's coaching must not read another user's stops."""
    from src.services.coaching import get_location_coaching

    _insert_stop(db_conn, user_id=2, location="Byng Island", species=["channel catfish"])

    # user 1 has never fished here; user 2's stop must stay invisible.
    result = get_location_coaching(db_conn, "Byng Island", user_id=1)
    assert "No logged trips" in result


def test_species_coaching_excludes_other_users(db_conn, monkeypatch):
    """Another user's catches must not reach the coaching prompt."""
    import src.services.coaching as coaching

    captured: dict = {}

    class _Msg:
        def __init__(self, text):
            self.content = [type("B", (), {"text": text})()]

    class _Client:
        class messages:
            @staticmethod
            def create(**kwargs):
                captured["prompt"] = kwargs["messages"][0]["content"]
                return _Msg("stub response")

    monkeypatch.setattr(coaching, "get_client", lambda: _Client())

    _insert_stop(db_conn, user_id=2, location="Byng Island", species=["channel catfish"])

    coaching.get_species_coaching(db_conn, "channel catfish", user_id=1)

    assert "Byng Island" not in captured["prompt"]
    assert "logged by user 2" not in captured["prompt"]
    assert "SUCCESSFUL CATCHES: None logged" in captured["prompt"]


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
