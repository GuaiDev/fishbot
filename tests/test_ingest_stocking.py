"""Tests for the MNRF stocking ingest module. No live downloads — uses fixture CSV."""

import logging
from datetime import datetime
from pathlib import Path

import httpx

from src.ingest.jurisdictions.ca_on import stocking as stocking_mod
from src.ingest.jurisdictions.ca_on.stocking import parse_stocking_records

FIXTURE = Path(__file__).parent / "fixtures" / "mnrf_stocking_sample.csv"


def test_parse_fixture():
    records = parse_stocking_records(FIXTURE)
    # Row 10 has no waterbody name and is skipped → 9 valid records
    assert len(records) == 9


def test_null_coords():
    records = parse_stocking_records(FIXTURE)
    # Row 7 (ObjectId=7): Hidden Pond has empty Latitude/Longitude
    hidden_pond = next(r for r in records if r.record_id == "7")
    assert hidden_pond.lat is None
    assert hidden_pond.lng is None


def test_waterbody_name_coalesce_from_unofficial():
    records = parse_stocking_records(FIXTURE)
    # Row 2 (ObjectId=2): only Unoffcial_Waterbody_Name is populated
    randall = next(r for r in records if r.record_id == "2")
    assert randall.waterbody_name == "Randall Lake (Unofficial Name)"

    # Row 7 (ObjectId=7): only Unoffcial_Waterbody_Name is populated
    hidden = next(r for r in records if r.record_id == "7")
    assert hidden.waterbody_name == "Hidden Pond (local name)"


def test_species_title_case():
    records = parse_stocking_records(FIXTURE)
    species = {r.species for r in records}
    # All should be title-case regardless of source capitalisation
    for s in species:
        assert s == s.title(), f"Species not title-case: {s!r}"
    assert "Brook Trout" in species
    assert "Rainbow Trout" in species
    assert "Walleye" in species


def test_null_quantity():
    records = parse_stocking_records(FIXTURE)
    # Row 5 (ObjectId=5): empty Number_of_Fish_Stocked
    bass_fry = next(r for r in records if r.record_id == "5")
    assert bass_fry.quantity is None


def test_skip_no_waterbody(caplog):
    with caplog.at_level(logging.WARNING):
        records = parse_stocking_records(FIXTURE)
    # Row 10 skipped — log message should mention "no waterbody name" or similar
    assert len(records) == 9
    assert any("waterbody" in msg.lower() for msg in caplog.messages)


def test_record_id_from_object_id():
    records = parse_stocking_records(FIXTURE)
    ids = {r.record_id for r in records}
    # ObjectId values 1-9 should appear as string record_ids
    for expected in ["1", "2", "3", "4", "5", "6", "7", "8", "9"]:
        assert expected in ids


def test_stocked_at_constructed_from_year():
    records = parse_stocking_records(FIXTURE)
    for r in records:
        assert r.stocked_at == datetime(r.year, 1, 1)


def test_jurisdiction_always_ca_on():
    records = parse_stocking_records(FIXTURE)
    for r in records:
        assert r.jurisdiction == "CA-ON"


def test_waterbody_code_parsed():
    records = parse_stocking_records(FIXTURE)
    blackfox = next(r for r in records if r.record_id == "1")
    assert blackfox.waterbody_code == "17-6975-50544"


def test_download_skips_if_fresh(tmp_path, monkeypatch):
    """Fresh file (< 30 days) should not trigger an HTTP download."""
    fresh_file = tmp_path / "mnrf_stocking.csv"
    fresh_file.write_text("placeholder")

    monkeypatch.setattr(stocking_mod, "_RAW_PATH", fresh_file)

    called = []

    def fake_stream(*args, **kwargs):
        called.append(True)
        raise AssertionError("should not make HTTP request for fresh file")

    monkeypatch.setattr(httpx, "stream", fake_stream)

    result = stocking_mod.download_stocking_data()
    assert result == fresh_file
    assert not called
