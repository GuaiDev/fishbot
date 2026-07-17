"""Tests for Alberta stocking ingest. No live downloads."""

from pathlib import Path

import httpx
import pytest

from src.ingest.jurisdictions.ca_ab import stocking

FIXTURE = Path(__file__).parent / "fixtures" / "ab_stocking_sample.xlsx"
_REAL_FIND_CURRENT_XLSX = stocking._find_current_xlsx


@pytest.fixture(autouse=True)
def _patch_paths(monkeypatch):
    monkeypatch.setattr(stocking, "_XLSX_PATH", FIXTURE)
    monkeypatch.setattr(
        stocking, "_find_current_xlsx", lambda: ("https://example.invalid/fixture.xlsx", 2026)
    )
    monkeypatch.setattr(stocking, "_download_xlsx_if_stale", lambda url: None)


def test_fetch_stocking_records_returns_rows():
    rows = stocking.fetch_stocking_records()
    # 5 data rows in, 2 malformed (blank species / missing waterbody) skipped
    assert len(rows) == 3


def test_species_codes_mapped_to_full_names():
    rows = stocking.fetch_stocking_records()
    species = {r["species"] for r in rows}
    assert species == {"Westslope Cutthroat Trout", "Rainbow Trout"}
    codes = {r["species_code"] for r in rows}
    assert codes == {"WSCT", "RNTR"}


def test_coordinates_present():
    rows = stocking.fetch_stocking_records()
    assert all(r["lat"] is not None and r["lng"] is not None for r in rows)


def test_life_stage_and_planned_date_preserved_as_free_text():
    rows = stocking.fetch_stocking_records()
    sizes = {r["life_stage"] for r in rows}
    assert "15cm 3N" in sizes
    assert ">35cm 2N" in sizes
    purposes = {r["stocking_purpose"] for r in rows}
    assert "odd years only" in purposes


def test_month_and_stocked_at_are_null():
    """No reliable month/date can be parsed from AB's free-text schedule field."""
    rows = stocking.fetch_stocking_records()
    assert all(r["month"] is None and r["stocked_at"] is None for r in rows)


def test_all_rows_tagged_ca_ab():
    rows = stocking.fetch_stocking_records()
    assert all(r["jurisdiction"] == "CA-AB" for r in rows)
    assert all(r["year"] == 2026 for r in rows)


def test_record_ids_unique():
    rows = stocking.fetch_stocking_records()
    ids = [r["record_id"] for r in rows]
    assert len(set(ids)) == len(ids)


def test_malformed_rows_skipped():
    rows = stocking.fetch_stocking_records()
    waterbodies = {r["waterbody_name"] for r in rows}
    assert "NO SPECIES POND" not in waterbodies
    assert None not in waterbodies


def test_no_openpyxl_returns_empty_list(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openpyxl":
            raise ImportError("no openpyxl")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert stocking.fetch_stocking_records() == []


def test_find_current_xlsx_picks_highest_year(monkeypatch, tmp_path):
    # Restore the real function — the autouse fixture stubs it for the other tests.
    monkeypatch.setattr(stocking, "_find_current_xlsx", _REAL_FIND_CURRENT_XLSX)
    monkeypatch.setattr(stocking, "_PACKAGE_CACHE_PATH", tmp_path / "package_meta.json")

    def fake_get(*args, **kwargs):
        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "result": {
                        "resources": [
                            {
                                "name": "Trout planned stocking dates 2025",
                                "format": "XLSX",
                                "url": "https://example.invalid/2025.xlsx",
                                "created": "2025-04-01",
                            },
                            {
                                "name": "Trout planned stocking dates 2026",
                                "format": "XLSX",
                                "url": "https://example.invalid/2026.xlsx",
                                "created": "2026-03-25",
                            },
                        ]
                    }
                }

        return FakeResp()

    monkeypatch.setattr(httpx, "get", fake_get)
    assert stocking._find_current_xlsx() == ("https://example.invalid/2026.xlsx", 2026)
