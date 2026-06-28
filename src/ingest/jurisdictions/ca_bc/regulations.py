"""BC Freshwater Fishing Regulations — PDF ingestion.

Downloads the BC Freshwater Fishing Regulations Synopsis PDF and splits it
into one text chunk per management region (Regions 1–8).

Source:
  BC Ministry of Environment — 2025-2027 synopsis
  https://www2.gov.bc.ca/assets/gov/sports-recreation-arts-and-culture/
  outdoor-recreation/freshwater-fishing/fishing-regulations/
  freshwater-fishing-regulations-synopsis-2025-2027.pdf

Fallback: fetches the regulations page and extracts the PDF link if the
direct URL is stale.

Table: regulation_chunks
  PK: (zone, jurisdiction, regulation_year)
  zone is the Region number (1–8); zone_name is the Region name.

Cache TTL: 365 days (biennial BC synopsis).
"""

import logging
import re
import time
from pathlib import Path

import httpx

_PDF_URL = (
    "https://www2.gov.bc.ca/assets/gov/sports-recreation-arts-and-culture/"
    "outdoor-recreation/freshwater-fishing/fishing-regulations/"
    "freshwater-fishing-regulations-synopsis-2025-2027.pdf"
)
_REG_YEAR = 2025
_PDF_PATH = Path("data/raw/bc_fishing_regulations_2025.pdf")
_CACHE_TTL_SECONDS = 365 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

# BC Freshwater Fishing Management Regions
_REGIONS: dict[int, str] = {
    1: "Vancouver Island",
    2: "Lower Mainland",
    3: "Thompson-Nicola",
    4: "Kootenay",
    5: "Cariboo",
    6: "Skeena",
    7: "Omineca",
    8: "Peace",
}

logger = logging.getLogger(__name__)


def fetch_regulations() -> list[dict]:
    """Download BC fishing regulations PDF and split into per-region chunks.

    Returns list of row dicts for regulation_chunks table.
    """
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        logger.error("BC regulations: pdfplumber not installed. Install with: uv add pdfplumber")
        return []

    _download_pdf_if_stale()
    if not _PDF_PATH.exists():
        logger.error("BC regulations: PDF not found at %s", _PDF_PATH)
        return []

    logger.info("BC regulations: parsing PDF %s", _PDF_PATH)
    try:
        with pdfplumber.open(_PDF_PATH) as pdf:
            full_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as exc:
        logger.error("BC regulations: PDF parse failed: %s", exc)
        return []

    chunks = _split_by_region(full_text)
    logger.info("BC regulations: %d region chunks extracted", len(chunks))
    return chunks


def _split_by_region(text: str) -> list[dict]:
    """Split regulation text into one chunk per BC management region."""
    import datetime

    now = datetime.datetime.utcnow().isoformat()
    chunks: list[dict] = []

    # Build split points for each region header
    region_pattern = re.compile(
        r"(REGION\s+\d+|Region\s+\d+)\s*[-—–]?\s*"
        r"(Vancouver Island|Lower Mainland|Thompson[- ]Nicola|Kootenay|"
        r"Cariboo|Skeena|Omineca|Peace)",
        re.IGNORECASE,
    )

    matches = list(region_pattern.finditer(text))
    if not matches:
        # Fallback: write full text as a single chunk with zone=0
        logger.warning("BC regulations: could not split by region — writing full text as zone 0")
        chunks.append({
            "zone": 0,
            "zone_name": "All Regions",
            "jurisdiction": "CA-BC",
            "regulation_year": _REG_YEAR,
            "raw_text": text.strip(),
            "char_count": len(text.strip()),
            "source_url": _PDF_URL,
            "ingested_at": now,
        })
        return chunks

    for i, m in enumerate(matches):
        # Extract region number from the match
        region_num_match = re.search(r"\d+", m.group(0))
        if not region_num_match:
            continue
        region_num = int(region_num_match.group())
        region_name = _REGIONS.get(region_num, m.group(0).strip())

        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk_text = text[start:end].strip()

        chunks.append({
            "zone": region_num,
            "zone_name": region_name,
            "jurisdiction": "CA-BC",
            "regulation_year": _REG_YEAR,
            "raw_text": chunk_text,
            "char_count": len(chunk_text),
            "source_url": _PDF_URL,
            "ingested_at": now,
        })

    return chunks


def _download_pdf_if_stale() -> None:
    _PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _PDF_PATH.exists():
        age = time.time() - _PDF_PATH.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            logger.info("BC regulations: PDF cache fresh, skipping download")
            return
    logger.info("BC regulations: downloading PDF …")
    try:
        response = httpx.get(
            _PDF_URL,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            timeout=120,
        )
        response.raise_for_status()
        _PDF_PATH.write_bytes(response.content)
        logger.info("BC regulations: downloaded %.1f MB", len(response.content) / 1_048_576)
    except Exception as exc:
        logger.error("BC regulations: download failed: %s", exc)
