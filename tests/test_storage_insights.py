"""Tests for behavioral insights storage layer."""

import pytest

from src.models.behavioral_insight import BehavioralInsight
from src.storage.database import ensure_schema
from src.storage.insights import (
    contradict_insight,
    get_insight,
    insert_insight,
    mark_user_verified,
    query_insights,
    refine_insight,
)

try:
    from sqlite_utils import Database
except ImportError:
    Database = None


def _make_db(tmp_path):
    from sqlite_utils import Database as DB

    db = DB(tmp_path / "test.db")
    ensure_schema(db)
    return db


def _insight(**overrides) -> BehavioralInsight:
    base = dict(
        species="brook trout",
        condition_type="behavioral",
        condition_context="post-cold-front",
        conclusion="Brook trout feed aggressively after a cold front in streams under 15°C.",
        confidence="medium",
        source_type="trip_log",
        source_detail="8 personal outings",
        evidence_count=8,
    )
    base.update(overrides)
    return BehavioralInsight(**base)


def test_insert_and_get(tmp_path):
    db = _make_db(tmp_path)
    new_id = insert_insight(db, _insight())
    assert isinstance(new_id, int)
    fetched = get_insight(db, new_id)
    assert fetched is not None
    assert fetched.species == "brook trout"
    assert fetched.version == 1
    assert fetched.is_current is True


def test_get_nonexistent(tmp_path):
    db = _make_db(tmp_path)
    assert get_insight(db, 9999) is None


def test_refine_increments_version(tmp_path):
    db = _make_db(tmp_path)
    old_id = insert_insight(db, _insight())

    refined = _insight(conclusion="Updated: brook trout feed 30-60 min post-front at sub-15°C.")
    new_id = refine_insight(db, old_id, refined)

    old = get_insight(db, old_id)
    new = get_insight(db, new_id)

    assert old is not None and new is not None
    assert old.is_current is False
    assert new.is_current is True
    assert new.version == old.version + 1


def test_refine_sets_contradicted_by(tmp_path):
    db = _make_db(tmp_path)
    old_id = insert_insight(db, _insight())
    new_id = refine_insight(db, old_id, _insight(conclusion="Refined conclusion."))

    old = get_insight(db, old_id)
    assert old is not None
    assert old.contradicted_by == new_id


def test_refine_nonexistent_raises(tmp_path):
    db = _make_db(tmp_path)
    with pytest.raises(ValueError, match="No insight with id=9999"):
        refine_insight(db, 9999, _insight())


def test_query_current_only(tmp_path):
    db = _make_db(tmp_path)
    old_id = insert_insight(db, _insight())
    refine_insight(db, old_id, _insight(conclusion="Refined."))

    results = query_insights(db, species="brook trout", current_only=True)
    assert len(results) == 1
    assert results[0].is_current is True


def test_query_all_versions(tmp_path):
    db = _make_db(tmp_path)
    old_id = insert_insight(db, _insight())
    refine_insight(db, old_id, _insight(conclusion="Refined."))

    results = query_insights(db, species="brook trout", current_only=False)
    assert len(results) == 2


def test_query_condition_type_filter(tmp_path):
    db = _make_db(tmp_path)
    insert_insight(db, _insight(condition_type="behavioral"))
    insert_insight(db, _insight(condition_type="habitat", conclusion="Prefer riffle edges."))

    behavioral = query_insights(db, species="brook trout", condition_type="behavioral")
    assert len(behavioral) == 1
    assert behavioral[0].condition_type == "behavioral"


def test_query_case_insensitive(tmp_path):
    db = _make_db(tmp_path)
    insert_insight(db, _insight(species="Brook Trout"))

    results = query_insights(db, species="brook trout")
    assert len(results) == 1

    results2 = query_insights(db, species="BROOK")
    assert len(results2) == 1


def test_mark_user_verified(tmp_path):
    db = _make_db(tmp_path)
    insight_id = insert_insight(db, _insight())
    mark_user_verified(db, insight_id)
    fetched = get_insight(db, insight_id)
    assert fetched is not None
    assert fetched.user_verified is True


def test_contradict_insight(tmp_path):
    db = _make_db(tmp_path)
    old_id = insert_insight(db, _insight())
    new_id = insert_insight(db, _insight(conclusion="Newer conclusion."))
    contradict_insight(db, old_id=old_id, new_id=new_id)
    old = get_insight(db, old_id)
    assert old is not None
    assert old.contradicted_by == new_id


def test_empty_query(tmp_path):
    db = _make_db(tmp_path)
    results = query_insights(db, species="walleye")
    assert results == []
