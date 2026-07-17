"""Tests for the catches table — one row per species caught at a stop."""

from src.storage.catches import get_catches_for_session, get_catches_for_sessions, insert_catch
from src.storage.database import get_db


def _session_and_stop(db):
    session_id = db["sessions"].insert({"date": "2026-06-01"}).last_pk
    stop_id = db["stops"].insert({
        "session_id": session_id,
        "location_text": "Bronte Creek",
        "species_caught": "[]",
    }).last_pk
    return session_id, stop_id


def test_insert_catch_returns_id(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    session_id, stop_id = _session_and_stop(db)

    catch_id = insert_catch(
        db, stop_id=stop_id, session_id=session_id, user_id=1, species="creek chub",
        photo_url="/photos/abc123.jpg",
    )
    assert isinstance(catch_id, int)
    assert catch_id > 0


def test_get_catches_for_session_round_trips_photo_fields(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    session_id, stop_id = _session_and_stop(db)

    insert_catch(
        db, stop_id=stop_id, session_id=session_id, user_id=1, species="rainbow darter",
        photo_url="/photos/xyz789.jpg", photo_lat=43.4, photo_lng=-79.7,
        photo_taken_at="2026-06-01T14:00:00",
    )

    catches = get_catches_for_session(db, session_id)
    assert len(catches) == 1
    assert catches[0]["species"] == "rainbow darter"
    assert catches[0]["photo_url"] == "/photos/xyz789.jpg"
    assert catches[0]["photo_lat"] == 43.4


def test_multiple_species_at_one_stop_get_separate_rows(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    session_id, stop_id = _session_and_stop(db)

    insert_catch(db, stop_id=stop_id, session_id=session_id, user_id=1, species="creek chub")
    insert_catch(db, stop_id=stop_id, session_id=session_id, user_id=1, species="rock bass")

    catches = get_catches_for_session(db, session_id)
    assert {c["species"] for c in catches} == {"creek chub", "rock bass"}


def test_catch_with_no_photo_has_none_url(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    session_id, stop_id = _session_and_stop(db)

    insert_catch(db, stop_id=stop_id, session_id=session_id, user_id=1, species="smallmouth bass")

    catches = get_catches_for_session(db, session_id)
    assert catches[0]["photo_url"] is None


def test_get_catches_for_sessions_batches_multiple_sessions(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    s1, stop1 = _session_and_stop(db)
    s2, stop2 = _session_and_stop(db)

    insert_catch(db, stop_id=stop1, session_id=s1, user_id=1, species="creek chub")
    insert_catch(db, stop_id=stop2, session_id=s2, user_id=1, species="rock bass")

    by_session = get_catches_for_sessions(db, [s1, s2])
    assert by_session[s1][0]["species"] == "creek chub"
    assert by_session[s2][0]["species"] == "rock bass"


def test_get_catches_for_sessions_empty_list_returns_empty_dict(tmp_path):
    db = get_db(path=tmp_path / "test.db")
    assert get_catches_for_sessions(db, []) == {}
