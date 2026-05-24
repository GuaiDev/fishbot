"""Tests for the RegulationChunk Pydantic model."""

import pytest
from pydantic import ValidationError

from src.models.regulation import RegulationChunk


def _valid_data(**overrides) -> dict:
    base = {
        "zone": 5,
        "jurisdiction": "CA-ON",
        "regulation_year": 2026,
        "raw_text": "ZONE 5\nWalleye: open May 1 – Nov 15. Min size 40cm. Limit 4.",
        "source_url": "https://www.ontario.ca/files/test.pdf",
        "ingested_at": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


def test_valid_chunk():
    c = RegulationChunk(**_valid_data())
    assert c.zone == 5
    assert c.jurisdiction == "CA-ON"
    assert c.regulation_year == 2026


def test_char_count_default_zero():
    c = RegulationChunk(**_valid_data())
    assert c.char_count == 0  # validator only fills when explicitly 0 but data not yet in info


def test_char_count_explicit():
    c = RegulationChunk(**_valid_data(char_count=42))
    assert c.char_count == 42


def test_zone_out_of_range_raises():
    with pytest.raises(ValidationError):
        RegulationChunk(**_valid_data(zone=0))
    with pytest.raises(ValidationError):
        RegulationChunk(**_valid_data(zone=21))


def test_zone_boundary_valid():
    c1 = RegulationChunk(**_valid_data(zone=1))
    c2 = RegulationChunk(**_valid_data(zone=20))
    assert c1.zone == 1
    assert c2.zone == 20


def test_jurisdiction_default():
    data = _valid_data()
    del data["jurisdiction"]
    c = RegulationChunk(**data)
    assert c.jurisdiction == "CA-ON"


def test_missing_required_zone_raises():
    data = _valid_data()
    del data["zone"]
    with pytest.raises(ValidationError):
        RegulationChunk(**data)


def test_missing_required_raw_text_raises():
    data = _valid_data()
    del data["raw_text"]
    with pytest.raises(ValidationError):
        RegulationChunk(**data)
