"""Tests for BC regulations ingest — no live downloads, no real PDF."""

import httpx

from src.ingest.jurisdictions.ca_bc import regulations as reg_mod
from src.ingest.jurisdictions.ca_bc.regulations import _split_by_region

# Mimics the real synopsis structure: a table of contents that mentions every
# region once (incidental, should be ignored), then real chapters with a
# running header repeated per page. Region 7A's running header is corrupted
# the way pdfplumber renders the real PDF's doubled text layer for that
# region only — every character doubled.
_SAMPLE_TEXT = """\
Table of Contents
REGION 1 - Vancouver Island .......... 12
REGION 2 - Lower Mainland ............ 20
REGION 7A - Omineca ................... 57
REGION 7B - Peace ..................... 63

REGION 1 - Vancouver Island
CONTACT INFO
Steelhead: open Apr 1 to Oct 31. Bait ban.
REGION 1 - Vancouver Island
Coho: daily limit 2.

REGION 2 - Lower Mainland
CONTACT INFO
Chinook: open May 1 to Sept 15.
REGION 2 - Lower Mainland
Sockeye: closed all year.

RREEGGIIOONN 77AA -- OOmmiinneeccaa
CONTACT INFO
Kokanee: daily quota = 5.
Lake trout: catch and release.

REGION 7B - Peace
CONTACT INFO
Bull trout: no bait.
"""


def test_split_finds_all_regions_including_garbled_omineca():
    chunks = _split_by_region(_SAMPLE_TEXT)
    zones = {c["zone"] for c in chunks}
    assert zones == {1, 2, 71, 72}


def test_running_header_repeats_merge_into_one_chunk_per_region():
    """Region 1's header repeats twice — both pages' content must survive,
    not just the last occurrence (this was the original bug: upserting on
    (zone, jurisdiction, regulation_year) meant only the last of several
    same-zone chunks would survive)."""
    chunks = _split_by_region(_SAMPLE_TEXT)
    zone1 = next(c for c in chunks if c["zone"] == 1)
    assert "Steelhead" in zone1["raw_text"]
    assert "Coho" in zone1["raw_text"]


def test_toc_mentions_do_not_create_spurious_chunks():
    """Each region is named once in the table of contents — that must not
    produce its own tiny chunk instead of the real chapter."""
    chunks = _split_by_region(_SAMPLE_TEXT)
    zone2 = next(c for c in chunks if c["zone"] == 2)
    # The real chapter (with Chinook/Sockeye), not the one-line TOC mention.
    assert "Chinook" in zone2["raw_text"]
    assert "Sockeye" in zone2["raw_text"]


def test_garbled_omineca_header_recovered_and_body_text_clean():
    chunks = _split_by_region(_SAMPLE_TEXT)
    omineca = next(c for c in chunks if c["zone"] == 71)
    assert omineca["zone_name"] == "Omineca"
    assert "Kokanee" in omineca["raw_text"]
    assert "Lake trout" in omineca["raw_text"]


def test_zone_71_72_do_not_bleed_into_each_other():
    chunks = _split_by_region(_SAMPLE_TEXT)
    omineca = next(c for c in chunks if c["zone"] == 71)
    peace = next(c for c in chunks if c["zone"] == 72)
    assert "Bull trout" not in omineca["raw_text"]
    assert "Kokanee" not in peace["raw_text"]


def test_split_jurisdiction_and_year():
    chunks = _split_by_region(_SAMPLE_TEXT)
    for c in chunks:
        assert c["jurisdiction"] == "CA-BC"
        assert c["regulation_year"] == reg_mod._REG_YEAR


def test_split_empty_text_returns_zone_zero_fallback():
    chunks = _split_by_region("")
    assert len(chunks) == 1
    assert chunks[0]["zone"] == 0


def test_split_no_region_headers_returns_zone_zero_fallback():
    chunks = _split_by_region("General rules only, no region markers here.")
    assert len(chunks) == 1
    assert chunks[0]["zone"] == 0


def test_download_skips_if_fresh(tmp_path, monkeypatch):
    fresh_pdf = tmp_path / "bc_fishing_regulations_2025.pdf"
    fresh_pdf.write_bytes(b"%PDF-1.4 placeholder")

    monkeypatch.setattr(reg_mod, "_PDF_PATH", fresh_pdf)
    called = []

    def fake_get(*args, **kwargs):
        called.append(True)
        raise AssertionError("should not fetch fresh file")

    monkeypatch.setattr(httpx, "get", fake_get)

    reg_mod._download_pdf_if_stale()
    assert not called
