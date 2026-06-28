"""Service entry point for federal/national data ingest.

Orchestrates national-scope adapters:
  - DFO critical habitat (all provinces)
  - DFO SAR range (all provinces, requires fiona)
  - CABIN benthic (all provinces — expanded from Ontario-only)
  - DataStream water quality (Manitoba + Atlantic Canada)

Called from the /ingest/data-national API endpoint.
Global sources (iNat, GBIF, WSC, OSM) are handled by the standard pipeline.
"""

import importlib
import logging

from src.storage.database import get_db

logger = logging.getLogger(__name__)


def ingest_dfo_critical_habitat(
    lat: float,
    lng: float,
    radius_km: float = 100.0,
) -> int:
    """Fetch and upsert DFO critical habitat records near lat/lng. Returns count."""
    _mod = importlib.import_module(
        "src.ingest.jurisdictions.ca_national.dfo_critical_habitat"
    )
    db = get_db()
    logger.info(
        "DFO critical habitat: fetching — lat=%.4f lng=%.4f radius=%.0fkm",
        lat, lng, radius_km,
    )
    rows = _mod.fetch_critical_habitat(lat, lng, radius_km)
    if rows:
        db["critical_habitat"].upsert_all(rows, pk="habitat_id")
    logger.info("DFO critical habitat: %d records stored", len(rows))
    return len(rows)


def ingest_dfo_sar_range() -> int:
    """Download DFO SAR range GDB and upsert to species_ranges. Returns count.

    Requires fiona. Returns 0 if fiona is not installed.
    Run once (annual release); does not take lat/lng — province-wide.
    """
    _mod = importlib.import_module(
        "src.ingest.jurisdictions.ca_national.dfo_sar_range"
    )
    db = get_db()
    logger.info("DFO SAR range: downloading and parsing GDB …")
    rows = _mod.fetch_sar_ranges()
    if rows:
        db["species_ranges"].upsert_all(rows, pk="species")
    logger.info("DFO SAR range: %d range records stored", len(rows))
    return len(rows)


def ingest_cabin_all_provinces() -> int:
    """Run CABIN benthic ingest for all provinces (not just Ontario).

    The expanded benthic adapter filters to ALL provinces. Returns count.
    """
    from src.services.benthic import ingest_benthic_samples
    db = get_db()
    logger.info("CABIN (all provinces): starting ingestion …")
    n = ingest_benthic_samples(db)
    logger.info("CABIN (all provinces): %d samples stored", n)
    return n


def ingest_datastream_water_quality(
    lat: float,
    lng: float,
    radius_km: float = 100.0,
) -> int:
    """Fetch DataStream water quality for lat/lng. Returns count."""
    _mod = importlib.import_module(
        "src.ingest.jurisdictions.ca_national.datastream_water_quality"
    )
    db = get_db()
    logger.info(
        "DataStream: fetching water quality — lat=%.4f lng=%.4f radius=%.0fkm",
        lat, lng, radius_km,
    )
    readings = _mod.fetch_water_quality_readings(lat, lng, radius_km)
    if readings:
        db["water_quality_readings"].upsert_all(readings, pk="record_id")
    logger.info("DataStream: %d readings stored", len(readings))
    return len(readings)


def ingest_national_data(
    lat: float,
    lng: float,
    radius_km: float = 100.0,
) -> dict[str, int]:
    """Run all national ingest adapters for a location. Returns counts per source."""
    critical_habitat = ingest_dfo_critical_habitat(lat, lng, radius_km)
    datastream = ingest_datastream_water_quality(lat, lng, radius_km)
    return {
        "dfo_critical_habitat": critical_habitat,
        "datastream_water_quality": datastream,
    }
