"""Tests for the stocking service layer — is_put_and_take, wild_population_likely, notes."""

import json
from datetime import datetime

from src.models.stocking_record import StockingRecord
from src.storage.database import ensure_schema
from src.storage.stocking import upsert_stocking_records


def _make_db(tmp_path):
    from sqlite_utils import Database
    db = Database(tmp_path / "test.db")
    ensure_schema(db)
    return db


def _make_record(**overrides) -> StockingRecord:
    base = dict(
        record_id="1",
        waterbody_name="Test Lake",
        waterbody_code="17-0000-00001",
        jurisdiction="CA-ON",
        species="Brook Trout",
        year=2020,
        quantity=1000,
        life_stage="Fry",
        stocked_at=datetime(2020, 1, 1),
    )
    base.update(overrides)
    return StockingRecord(**base)


def _seed(db, records: list[StockingRecord]) -> None:
    upsert_stocking_records(db, records)


def _call(db, monkeypatch, **kwargs) -> dict:
    monkeypatch.setattr("src.services.stocking.get_db", lambda: db)
    from src.services.stocking import get_stocking_for_agent
    return json.loads(get_stocking_for_agent(**kwargs))


# --- is_put_and_take ---

def test_is_put_and_take_true(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    # Current year - 2 = recent enough; Yearlings = catchable-size
    from src.services import stocking as svc
    current_year = svc._CURRENT_YEAR
    _seed(db, [_make_record(record_id="1", year=current_year - 1, life_stage="Yearlings")])
    result = _call(db, monkeypatch, waterbody_name="Test Lake")
    wb = result["waterbodies"][0]
    assert wb["is_put_and_take"] is True


def test_is_put_and_take_false_early_stage(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    from src.services import stocking as svc
    current_year = svc._CURRENT_YEAR
    _seed(db, [_make_record(record_id="1", year=current_year - 1, life_stage="Fingerlings")])
    result = _call(db, monkeypatch, waterbody_name="Test Lake")
    wb = result["waterbodies"][0]
    assert wb["is_put_and_take"] is False


def test_is_put_and_take_false_old_yearlings(tmp_path, monkeypatch):
    """Yearlings stocked more than 3 years ago → not put-and-take."""
    db = _make_db(tmp_path)
    from src.services import stocking as svc
    current_year = svc._CURRENT_YEAR
    _seed(db, [_make_record(record_id="1", year=current_year - 5, life_stage="Yearlings")])
    result = _call(db, monkeypatch, waterbody_name="Test Lake")
    wb = result["waterbodies"][0]
    assert wb["is_put_and_take"] is False


# --- wild_population_likely ---

def test_wild_population_likely_true(tmp_path, monkeypatch):
    """Fry only, last stocking >5 years ago → likely wild."""
    db = _make_db(tmp_path)
    from src.services import stocking as svc
    current_year = svc._CURRENT_YEAR
    _seed(db, [
        _make_record(record_id="1", year=current_year - 7, life_stage="Fry"),
        _make_record(record_id="2", year=current_year - 6, life_stage="Fingerlings"),
    ])
    result = _call(db, monkeypatch, waterbody_name="Test Lake")
    wb = result["waterbodies"][0]
    assert wb["wild_population_likely"] is True


def test_wild_population_likely_false_recent(tmp_path, monkeypatch):
    """Fry stocked within last 5 years → too recent to confirm wild."""
    db = _make_db(tmp_path)
    from src.services import stocking as svc
    current_year = svc._CURRENT_YEAR
    _seed(db, [_make_record(record_id="1", year=current_year - 3, life_stage="Fry")])
    result = _call(db, monkeypatch, waterbody_name="Test Lake")
    wb = result["waterbodies"][0]
    assert wb["wild_population_likely"] is False


def test_wild_population_likely_false_exactly_5_years(tmp_path, monkeypatch):
    """Exactly 5 years ago is NOT 'more than 5 years' → False."""
    db = _make_db(tmp_path)
    from src.services import stocking as svc
    current_year = svc._CURRENT_YEAR
    _seed(db, [_make_record(record_id="1", year=current_year - 5, life_stage="Fry")])
    result = _call(db, monkeypatch, waterbody_name="Test Lake")
    wb = result["waterbodies"][0]
    assert wb["wild_population_likely"] is False


def test_wild_population_likely_false_has_yearlings(tmp_path, monkeypatch):
    """Old stocking but includes Yearlings → not all early-stage → False."""
    db = _make_db(tmp_path)
    from src.services import stocking as svc
    current_year = svc._CURRENT_YEAR
    _seed(db, [
        _make_record(record_id="1", year=current_year - 8, life_stage="Fry"),
        _make_record(record_id="2", year=current_year - 8, life_stage="Yearlings"),
    ])
    result = _call(db, monkeypatch, waterbody_name="Test Lake")
    wb = result["waterbodies"][0]
    assert wb["wild_population_likely"] is False


def test_wild_population_likely_false_no_records(tmp_path, monkeypatch):
    """No stocking records → cannot infer wild population."""
    db = _make_db(tmp_path)
    result = _call(db, monkeypatch, waterbody_name="Nonexistent Lake")
    assert result["total_events"] == 0
    assert result["waterbodies"] == []


# --- stocking_note content ---

def test_stocking_note_put_and_take(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    from src.services import stocking as svc
    _seed(db, [_make_record(record_id="1", year=svc._CURRENT_YEAR - 1, life_stage="Yearlings")])
    result = _call(db, monkeypatch, waterbody_name="Test Lake")
    note = result["waterbodies"][0]["stocking_note"]
    assert "put-and-take" in note.lower()


def test_stocking_note_wild_likely(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    from src.services import stocking as svc
    _seed(db, [_make_record(record_id="1", year=svc._CURRENT_YEAR - 8, life_stage="Fry")])
    result = _call(db, monkeypatch, waterbody_name="Test Lake")
    note = result["waterbodies"][0]["stocking_note"]
    assert "self-sustaining" in note.lower() or "wild" in note.lower()


def test_stocking_note_no_records(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    result = _call(db, monkeypatch, waterbody_name="Ghost Lake")
    assert "no mnrf stocking records" in result["note"].lower()


# --- query filters ---

def test_waterbody_filter_partial_match(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    _seed(db, [
        _make_record(record_id="1", waterbody_name="Blackfox Lake"),
        _make_record(record_id="2", waterbody_name="Silverfox Lake"),
        _make_record(record_id="3", waterbody_name="Bass Lake"),
    ])
    result = _call(db, monkeypatch, waterbody_name="fox")
    names = {wb["waterbody_name"] for wb in result["waterbodies"]}
    assert "Blackfox Lake" in names
    assert "Silverfox Lake" in names
    assert "Bass Lake" not in names


def test_species_filter(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    _seed(db, [
        _make_record(record_id="1", waterbody_name="Lake A", species="Brook Trout"),
        _make_record(record_id="2", waterbody_name="Lake B", species="Walleye"),
    ])
    result = _call(db, monkeypatch, species="walleye")
    assert result["total_events"] == 1
    assert result["waterbodies"][0]["waterbody_name"] == "Lake B"


def test_spatial_filter(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    _seed(db, [
        _make_record(record_id="1", waterbody_name="Nearby Lake", lat=43.65, lng=-79.38),
        _make_record(record_id="2", waterbody_name="Far Lake", lat=50.0, lng=-90.0),
    ])
    result = _call(db, monkeypatch, lat=43.65, lng=-79.38, radius_km=10)
    names = {wb["waterbody_name"] for wb in result["waterbodies"]}
    assert "Nearby Lake" in names
    assert "Far Lake" not in names


def test_year_from_filter(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    _seed(db, [
        _make_record(record_id="1", year=2015),
        _make_record(record_id="2", year=2022),
    ])
    result = _call(db, monkeypatch, waterbody_name="Test Lake", year_from=2020)
    assert result["total_events"] == 1
    assert result["waterbodies"][0]["most_recent_year"] == 2022


def test_life_stage_case_insensitive(tmp_path, monkeypatch):
    """is_put_and_take and wild_likely checks must be case-insensitive."""
    db = _make_db(tmp_path)
    from src.services import stocking as svc
    # Use uppercase life stage — should still be recognized
    _seed(db, [_make_record(record_id="1", year=svc._CURRENT_YEAR - 1, life_stage="YEARLINGS")])
    result = _call(db, monkeypatch, waterbody_name="Test Lake")
    assert result["waterbodies"][0]["is_put_and_take"] is True
