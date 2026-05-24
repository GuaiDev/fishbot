"""Tests for MNRF regulations ingest — no live downloads, no real PDF."""


import httpx

from src.ingest.jurisdictions.ca_on import regulations as reg_mod
from src.ingest.jurisdictions.ca_on.regulations import _split_by_zone

# --- zone splitting tests (pure text, no pdfplumber) ---

_SAMPLE_TEXT = """\
General Provisions
All anglers must have a valid licence.

ZONE 1
Walleye: open May 1 to Nov 15. Min size 40cm. Daily limit 4.
Bass: open last Saturday in June.

ZONE 2
Brook Trout: open April 1 to Sept 30. Min size 25cm. Daily limit 5.
Walleye: open May 15 to Nov 30. Limit 4.

ZONE 3
Muskellunge: open June 15 to Dec 15. Min size 75cm. Limit 1.
"""


def test_split_finds_three_zones():
    chunks = _split_by_zone(_SAMPLE_TEXT)
    assert len(chunks) == 3
    zones = [c.zone for c in chunks]
    assert zones == [1, 2, 3]


def test_split_zone_text_contains_species():
    chunks = _split_by_zone(_SAMPLE_TEXT)
    zone1 = next(c for c in chunks if c.zone == 1)
    assert "Walleye" in zone1.raw_text
    assert "Bass" in zone1.raw_text


def test_split_zone2_text_does_not_bleed_into_zone3():
    chunks = _split_by_zone(_SAMPLE_TEXT)
    zone2 = next(c for c in chunks if c.zone == 2)
    assert "Muskellunge" not in zone2.raw_text


def test_split_jurisdiction_and_year():
    chunks = _split_by_zone(_SAMPLE_TEXT)
    for c in chunks:
        assert c.jurisdiction == "CA-ON"
        assert c.regulation_year == reg_mod._REG_YEAR


def test_split_empty_text_returns_empty():
    chunks = _split_by_zone("")
    assert chunks == []


def test_split_no_zone_headers_returns_empty():
    chunks = _split_by_zone("General rules only, no zone markers here.")
    assert chunks == []


def test_split_fmz_header_variant():
    text = "FMZ 7\nWalleye rules here.\nFMZ 8\nBass rules here."
    chunks = _split_by_zone(text)
    assert len(chunks) == 2
    assert chunks[0].zone == 7
    assert chunks[1].zone == 8


def test_split_largest_chunk_wins_on_duplicate_zone_header():
    """If the same zone header appears twice, the larger chunk is kept."""
    text = "ZONE 1\nshort.\nZONE 2\nfull content for zone 2 with lots of text.\nZONE 1\neven shorter."  # noqa: E501
    chunks = _split_by_zone(text)
    zone1_chunks = [c for c in chunks if c.zone == 1]
    assert len(zone1_chunks) == 1


# --- download freshness test ---

def test_download_skips_if_fresh(tmp_path, monkeypatch):
    fresh_pdf = tmp_path / "mnrf_regulations_2026.pdf"
    fresh_pdf.write_bytes(b"%PDF-1.4 placeholder")

    monkeypatch.setattr(reg_mod, "_RAW_PATH", fresh_pdf)
    called = []

    def fake_stream(*args, **kwargs):
        called.append(True)
        raise AssertionError("should not fetch fresh file")

    monkeypatch.setattr(httpx, "stream", fake_stream)

    result = reg_mod.download_regulations_pdf()
    assert result == fresh_pdf
    assert not called
