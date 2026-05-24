"""MNRF Recreational Fishing Regulations Summary ingestion for Ontario (CA-ON).

Downloads the annual province-wide PDF from ontario.ca, extracts text with
pdfplumber, and splits it into per-FMZ chunks for storage.

The PDF is updated once a year (effective January 1). Update _PDF_URL and
_REG_YEAR each December when MNRF publishes the new edition.
"""

import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from src.models.regulation import RegulationChunk

_REG_YEAR = 2026
_PDF_URL = (
    "https://www.ontario.ca/files/2025-12/"
    "mnr-2026-fishing-regulations-summary-en-2025-12-08.pdf"
)
_RAW_PATH = Path(f"data/raw/mnrf_regulations_{_REG_YEAR}.pdf")
_TTL_SECONDS = 365 * 86400  # annual publication; re-download only on next year's release
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

# Matches "ZONE 1", "ZONE 1 —", "FMZ 1", etc. at a line boundary.
# Must capture the zone number as group 1.
_ZONE_HEADER = re.compile(
    r"(?:FISHERIES MANAGEMENT ZONE|FMZ|ZONE)\s+(\d{1,2})\b",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


def download_regulations_pdf() -> Path:
    """Download the MNRF regulations PDF. Returns path; skips if file is fresh."""
    if _RAW_PATH.exists():
        age = time.time() - _RAW_PATH.stat().st_mtime
        if age < _TTL_SECONDS:
            logger.info(
                "MNRF regulations PDF is fresh (%.0f days old), skipping", age / 86400
            )
            return _RAW_PATH

    _RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading MNRF regulations PDF (%d)…", _REG_YEAR)

    with httpx.stream(
        "GET",
        _PDF_URL,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        with _RAW_PATH.open("wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=65536):
                fh.write(chunk)

    logger.info("Downloaded regulations PDF: %s", _RAW_PATH)
    return _RAW_PATH


def extract_zone_chunks(pdf_path: Path) -> list[RegulationChunk]:
    """Extract text from the PDF and split into per-zone RegulationChunk objects."""

    logger.info("Extracting text from %s (this may take a moment)…", pdf_path)

    full_text = _extract_full_text(pdf_path)
    chunks = _split_by_zone(full_text)

    logger.info("Extracted %d FMZ zone chunks from regulations PDF", len(chunks))
    return chunks


def _extract_full_text(pdf_path: Path) -> str:
    """Extract all page text from the PDF."""
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _split_by_zone(full_text: str) -> list[RegulationChunk]:
    """Split the full PDF text into per-FMZ chunks.

    Finds all occurrences of zone header patterns and uses them as boundaries.
    Returns chunks sorted by zone number; zones not found are omitted.
    """
    matches = list(_ZONE_HEADER.finditer(full_text))
    if not matches:
        logger.warning("No zone headers found in regulations PDF text")
        return []

    now = datetime.now(UTC).isoformat()
    zones: dict[int, str] = {}

    for i, m in enumerate(matches):
        zone_num = int(m.group(1))
        if zone_num < 1 or zone_num > 20:
            continue
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        chunk_text = full_text[start:end].strip()
        # Keep the largest chunk if the same zone header appears multiple times
        if zone_num not in zones or len(chunk_text) > len(zones[zone_num]):
            zones[zone_num] = chunk_text

    return [
        RegulationChunk(
            zone=z,
            jurisdiction="CA-ON",
            regulation_year=_REG_YEAR,
            raw_text=text,
            char_count=len(text),
            source_url=_PDF_URL,
            ingested_at=now,
        )
        for z, text in sorted(zones.items())
    ]
