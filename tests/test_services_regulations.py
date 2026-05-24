"""Tests for the regulations service layer."""

import json

import pytest

from src.models.regulation import RegulationChunk
from src.services.regulations import (
    _estimate_fmz,
    _extract_species_context,
    get_regulations_for_agent,
)
from src.storage.database import get_db
from src.storage.regulations import upsert_regulation_chunks


def _make_chunk(zone: int, text: str = "") -> RegulationChunk:
    if not text:
        text = f"ZONE {zone}\nWalleye: open May 1. Limit 4.\nBass: open last Saturday June."
    return RegulationChunk(
        zone=zone,
        jurisdiction="CA-ON",
        regulation_year=2026,
        raw_text=text,
        char_count=len(text),
        source_url="https://www.ontario.ca/files/test.pdf",
        ingested_at="2026-01-01T00:00:00",
    )


@pytest.fixture()
def populated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    db = get_db(db_path)
    chunks = [_make_chunk(z) for z in [5, 16, 20]]
    upsert_regulation_chunks(db, chunks)
    monkeypatch.setattr("src.services.regulations.get_db", lambda: db)
    return db


@pytest.fixture()
def empty_db(tmp_path, monkeypatch):
    db_path = tmp_path / "empty.db"
    db = get_db(db_path)
    monkeypatch.setattr("src.services.regulations.get_db", lambda: db)
    return db


# --- FMZ coordinate estimation ---

def test_estimate_fmz_toronto():
    # Toronto is ~43.65, -79.38 → roughly Zone 6 or 5
    zone = _estimate_fmz(43.65, -79.38)
    assert zone is not None
    assert 1 <= zone <= 20


def test_estimate_fmz_outside_ontario_returns_none():
    # New York City is outside Ontario bounding boxes
    zone = _estimate_fmz(40.7, -74.0)
    assert zone is None


def test_estimate_fmz_thunder_bay():
    # Thunder Bay ~48.4, -89.3 → Zone 17
    zone = _estimate_fmz(48.4, -89.3)
    assert zone is not None


# --- service layer ---

def test_no_zone_no_coords_returns_error():
    result = json.loads(get_regulations_for_agent())
    assert "error" in result
    assert "FMZ" in result["error"]


def test_empty_db_returns_error(empty_db):
    result = json.loads(get_regulations_for_agent(zone=5))
    assert "error" in result
    assert "make ingest" in result["error"].lower()


def test_zone_not_in_db_returns_error(populated_db):
    result = json.loads(get_regulations_for_agent(zone=3))
    assert "error" in result


def test_zone_found_returns_text(populated_db):
    result = json.loads(get_regulations_for_agent(zone=5))
    assert "text" in result
    assert result["zone"] == 5
    assert result["regulation_year"] == 2026
    assert "disclaimer" in result


def test_species_filter_narrows_text(populated_db):
    result = json.loads(get_regulations_for_agent(zone=5, species="Walleye"))
    assert "text" in result
    assert result["species_query"] == "Walleye"


def test_species_not_found_returns_note(populated_db):
    result = json.loads(get_regulations_for_agent(zone=5, species="Muskellunge"))
    assert "text" in result
    assert "not found" in result["text"].lower() or "muskellunge" in result["text"].lower()


def test_latlon_triggers_zone_detection(populated_db):
    # lat/lng near Thunder Bay should auto-detect a northern zone
    result = json.loads(get_regulations_for_agent(lat=48.4, lng=-89.3))
    # Should not return "provide zone" error — coordinates should resolve
    # Zone may or may not be in our test DB; just check it tried
    assert "zone" in result


# --- _extract_species_context ---

def test_extract_species_context_found():
    text = "ZONE 5\n" + "x" * 200 + "Walleye: open May 1, limit 4." + "x" * 200
    excerpt, truncated = _extract_species_context(text, "Walleye")
    assert "Walleye" in excerpt
    assert not truncated


def test_extract_species_context_not_found_returns_overview():
    text = "ZONE 5\nBass rules only."
    excerpt, _ = _extract_species_context(text, "Muskellunge")
    assert "not found" in excerpt.lower()
    assert "ZONE 5" in excerpt or "Bass" in excerpt
