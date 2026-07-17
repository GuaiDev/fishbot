"""Service entry point for Alberta-specific data ingest.

Orchestrates CA-AB adapters:
  - AB stocking records (planned stocking XLSX from Open Alberta)
  - AB regulations (stub — see ca_ab/regulations.py)
  - AB water quality (stub — no public API as of 2026)
  - AB hydro network (stub — NHN tile download not yet implemented)

Global sources (iNat, GBIF, WSC, OSM) are handled by the standard pipeline.
NuSEDS salmon escapement is BC-only (not applicable to AB).
"""

import importlib
import logging
from datetime import datetime

from src.storage.database import get_db

logger = logging.getLogger(__name__)


def ingest_ab_stocking() -> int:
    """Download and store Alberta planned stocking XLSX. Returns count."""
    _mod = importlib.import_module("src.ingest.jurisdictions.ca_ab.stocking")
    db = get_db()
    logger.info("AB stocking: fetching records …")
    rows = _mod.fetch_stocking_records()
    if rows:
        # stocking_records has no ingested_at column (unlike regulation_chunks) —
        # upsert_all would raise sqlite3.OperationalError if we set one.
        db["stocking_records"].upsert_all(rows, pk="record_id")
    logger.info("AB stocking: %d records stored", len(rows))
    return len(rows)


def ingest_ab_regulations() -> int:
    """Fetch Alberta fishing regulations. Returns chunk count (currently 0 — stub)."""
    _mod = importlib.import_module("src.ingest.jurisdictions.ca_ab.regulations")
    db = get_db()
    logger.info("AB regulations: fetching regulation chunks …")
    chunks = _mod.fetch_regulations()
    if chunks:
        _upsert_regulation_chunks(db, chunks)
    logger.info("AB regulations: %d chunks stored", len(chunks))
    return len(chunks)


def ingest_ab_water_quality(
    lat: float,
    lng: float,
    radius_km: float = 50.0,
) -> int:
    """Fetch Alberta water quality readings. Returns count (currently 0 — stub)."""
    _mod = importlib.import_module("src.ingest.jurisdictions.ca_ab.water_quality")
    logger.info(
        "AB water quality: fetching — lat=%.4f lng=%.4f radius=%.0fkm",
        lat, lng, radius_km,
    )
    readings = _mod.fetch_water_quality_readings(lat, lng, radius_km)
    if readings:
        db = get_db()
        db["water_quality_readings"].upsert_all(readings, pk="record_id")
    logger.info("AB water quality: %d readings stored", len(readings))
    return len(readings)


def ingest_ab_data(
    lat: float,
    lng: float,
    radius_km: float = 50.0,
) -> dict[str, int]:
    """Run all Alberta-specific ingest adapters. Returns counts per source."""
    stocking = ingest_ab_stocking()
    regulations = ingest_ab_regulations()
    wq = ingest_ab_water_quality(lat, lng, radius_km)
    return {
        "ab_stocking": stocking,
        "ab_regulations": regulations,
        "ab_water_quality": wq,
    }


def _upsert_regulation_chunks(db, chunks: list[dict]) -> None:
    """Write regulation chunks; add zone_name if column exists."""
    for chunk in chunks:
        row = {
            "zone": chunk["zone"],
            "jurisdiction": chunk["jurisdiction"],
            "regulation_year": chunk["regulation_year"],
            "raw_text": chunk["raw_text"],
            "char_count": chunk["char_count"],
            "source_url": chunk.get("source_url", ""),
            "ingested_at": chunk.get("ingested_at", datetime.utcnow().isoformat()),
        }
        if chunk.get("zone_name"):
            row["zone_name"] = chunk["zone_name"]
        db["regulation_chunks"].upsert(row, pk=["zone", "jurisdiction", "regulation_year"])
