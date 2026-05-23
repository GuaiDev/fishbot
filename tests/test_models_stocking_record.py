"""Tests for StockingRecord model validation."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.stocking_record import StockingRecord


def _valid_data(**overrides) -> dict:
    base = {
        "record_id": "42",
        "waterbody_name": "Blackfox Lake",
        "waterbody_code": "17-6975-50544",
        "municipality": "SPROULE",
        "county": "Algonquin Park Zone - Ontario Parks",
        "lat": 45.62212,
        "lng": -78.46358,
        "jurisdiction": "CA-ON",
        "species": "Brook Trout",
        "year": 2022,
        "quantity": 2450,
        "life_stage": "Yearlings",
        "stocked_at": datetime(2022, 1, 1),
    }
    base.update(overrides)
    return base


def test_valid_full_record():
    r = StockingRecord(**_valid_data())
    assert r.record_id == "42"
    assert r.waterbody_name == "Blackfox Lake"
    assert r.species == "Brook Trout"
    assert r.jurisdiction == "CA-ON"
    assert r.year == 2022


def test_optional_fields_none():
    r = StockingRecord(**_valid_data(
        waterbody_code=None,
        municipality=None,
        county=None,
        lat=None,
        lng=None,
        species_code=None,
        month=None,
        quantity=None,
        life_stage=None,
        stocking_purpose=None,
    ))
    assert r.waterbody_code is None
    assert r.lat is None
    assert r.lng is None
    assert r.quantity is None
    assert r.species_code is None
    assert r.month is None
    assert r.stocking_purpose is None


def test_jurisdiction_default():
    r = StockingRecord(**_valid_data())
    assert r.jurisdiction == "CA-ON"


def test_stocked_at_year_only():
    r = StockingRecord(**_valid_data(stocked_at=datetime(2022, 1, 1)))
    assert r.stocked_at == datetime(2022, 1, 1)
    assert r.stocked_at.year == 2022
    assert r.stocked_at.month == 1


def test_missing_required_record_id_raises():
    data = _valid_data()
    del data["record_id"]
    with pytest.raises(ValidationError):
        StockingRecord(**data)


def test_missing_required_waterbody_name_raises():
    data = _valid_data()
    del data["waterbody_name"]
    with pytest.raises(ValidationError):
        StockingRecord(**data)


def test_missing_required_species_raises():
    data = _valid_data()
    del data["species"]
    with pytest.raises(ValidationError):
        StockingRecord(**data)
