"""Tests for Alberta regulations ingest — no live downloads, no real PDF."""

import httpx

from src.ingest.jurisdictions.ca_ab import regulations as reg_mod
from src.ingest.jurisdictions.ca_ab.regulations import _split_by_watershed_unit

_SAMPLE_TEXT = """\
Table of Contents
Fish Management Zone 1 - Eastern Slopes ... 30

n The Eastern Slopes consists of the mountains and foothills.
ES1 WATERSHED UNIT REGULATIONS
n The Oldman and Bow rivers watershed.
Rainbow trout daily quota = 2.

ES2 WATERSHED UNIT REGULATIONS
n The Red Deer and North Saskatchewan rivers watershed.
Bull trout catch and release.

NB4 WATERSHED UNIT REGULATIONS
n The Athabasca River watershed downstream.
Walleye daily quota = 5.
"""


def test_split_finds_all_watershed_units():
    chunks = _split_by_watershed_unit(_SAMPLE_TEXT, "https://example.invalid/regs.pdf", 2026)
    zones = {c["zone"] for c in chunks}
    assert zones == {1, 2, 10}


def test_zone_names_are_descriptive():
    chunks = _split_by_watershed_unit(_SAMPLE_TEXT, "https://example.invalid/regs.pdf", 2026)
    es1 = next(c for c in chunks if c["zone"] == 1)
    nb4 = next(c for c in chunks if c["zone"] == 10)
    assert es1["zone_name"] == "Eastern Slopes — ES1"
    assert nb4["zone_name"] == "Northern Boreal — NB4"


def test_chunks_do_not_bleed_into_each_other():
    chunks = _split_by_watershed_unit(_SAMPLE_TEXT, "https://example.invalid/regs.pdf", 2026)
    es1 = next(c for c in chunks if c["zone"] == 1)
    es2 = next(c for c in chunks if c["zone"] == 2)
    assert "Rainbow trout" in es1["raw_text"]
    assert "Bull trout" not in es1["raw_text"]
    assert "Bull trout" in es2["raw_text"]
    assert "Rainbow trout" not in es2["raw_text"]


def test_split_jurisdiction_and_year():
    chunks = _split_by_watershed_unit(_SAMPLE_TEXT, "https://example.invalid/regs.pdf", 2026)
    for c in chunks:
        assert c["jurisdiction"] == "CA-AB"
        assert c["regulation_year"] == 2026


def test_split_empty_text_returns_zone_zero_fallback():
    chunks = _split_by_watershed_unit("", "https://example.invalid/regs.pdf", 2026)
    assert len(chunks) == 1
    assert chunks[0]["zone"] == 0


def test_split_no_headers_returns_zone_zero_fallback():
    chunks = _split_by_watershed_unit(
        "General rules only, no watershed unit markers here.",
        "https://example.invalid/regs.pdf",
        2026,
    )
    assert len(chunks) == 1
    assert chunks[0]["zone"] == 0


def test_find_current_pdf_picks_highest_year(monkeypatch, tmp_path):
    cache_path = tmp_path / "package_meta.json"
    monkeypatch.setattr(reg_mod, "_PACKAGE_CACHE_PATH", cache_path)

    def fake_get(*args, **kwargs):
        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "result": {
                        "resources": [
                            {
                                "name": "2025 Alberta guide to sportfishing regulations",
                                "format": "PDF",
                                "url": "https://example.invalid/2025.pdf",
                                "created": "2025-03-25",
                            },
                            {
                                "name": "2026 Alberta guide to sportfishing regulations",
                                "format": "PDF",
                                "url": "https://example.invalid/2026.pdf",
                                "created": "2026-03-23",
                            },
                            {
                                "name": "2024 Alberta guide - amended",
                                "format": "PDF",
                                "url": "https://example.invalid/2024-amended.pdf",
                                "created": "2025-02-12",
                            },
                        ]
                    }
                }

        return FakeResp()

    monkeypatch.setattr(httpx, "get", fake_get)
    result = reg_mod._find_current_pdf()
    assert result == ("https://example.invalid/2026.pdf", 2026)


def test_download_skips_if_fresh(tmp_path, monkeypatch):
    fresh_pdf = tmp_path / "ab_regulations.pdf"
    fresh_pdf.write_bytes(b"%PDF-1.4 placeholder")

    monkeypatch.setattr(reg_mod, "_PDF_PATH", fresh_pdf)
    called = []

    def fake_stream(*args, **kwargs):
        called.append(True)
        raise AssertionError("should not fetch fresh file")

    monkeypatch.setattr(httpx, "stream", fake_stream)

    reg_mod._download_pdf_if_stale("https://example.invalid/regs.pdf")
    assert not called
