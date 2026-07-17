"""Tests for BC NuSEDS salmon escapement ingest. No live downloads."""

from pathlib import Path

import pytest

from src.ingest.jurisdictions.ca_bc import nuseds

FIXTURE = Path(__file__).parent / "fixtures" / "nuseds_sample.xlsx"


@pytest.fixture(autouse=True)
def _patch_paths(monkeypatch, tmp_path):
    """Point the adapter at the fixture XLSX and skip the network entirely."""
    monkeypatch.setattr(nuseds, "_XLSX_PATH", FIXTURE)
    monkeypatch.setattr(nuseds, "_find_xlsx_url", lambda: "https://example.invalid/fixture.xlsx")
    monkeypatch.setattr(nuseds, "_download_xlsx_if_stale", lambda url: None)


def test_fetch_salmon_escapement_returns_rows():
    rows = nuseds.fetch_salmon_escapement()
    # 5 fixture rows in, 2 malformed (missing ACT_ID / missing SPECIES) skipped
    assert len(rows) == 3


def test_all_rows_tagged_ca_bc():
    rows = nuseds.fetch_salmon_escapement()
    assert all(r["jurisdiction"] == "CA-BC" for r in rows)
    assert all(r["source"] == "NuSEDS" for r in rows)


def test_record_id_uses_act_id():
    rows = nuseds.fetch_salmon_escapement()
    ids = {r["record_id"] for r in rows}
    assert ids == {"NUSEDS_1001", "NUSEDS_1002", "NUSEDS_1003"}


def test_max_estimate_prefers_natural_spawners_total():
    rows = {r["record_id"]: r for r in nuseds.fetch_salmon_escapement()}
    assert rows["NUSEDS_1001"]["max_estimate"] == 150


def test_max_estimate_falls_back_to_total_return_to_river():
    rows = {r["record_id"]: r for r in nuseds.fetch_salmon_escapement()}
    assert rows["NUSEDS_1002"]["max_estimate"] == 42


def test_presence_only_row_kept_with_null_estimate():
    rows = {r["record_id"]: r for r in nuseds.fetch_salmon_escapement()}
    assert rows["NUSEDS_1003"]["max_estimate"] is None
    assert rows["NUSEDS_1003"]["species"] == "Coho"


def test_missing_act_id_or_species_rows_skipped():
    rows = {r["record_id"] for r in nuseds.fetch_salmon_escapement()}
    assert "NUSEDS_None" not in rows
    assert len(rows) == 3


def test_stream_coordinates_are_null():
    """Neither NuSEDS export includes lat/lng as of the 2026-06 release."""
    rows = nuseds.fetch_salmon_escapement()
    assert all(r["stream_lat"] is None and r["stream_lng"] is None for r in rows)


def test_no_openpyxl_returns_empty_list(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openpyxl":
            raise ImportError("no openpyxl")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert nuseds.fetch_salmon_escapement() == []
