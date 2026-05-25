"""MNRF fish stocking data ingestion for Ontario (CA-ON).

Downloads the current recreational stocking CSV from ArcGIS GeoHub via Ontario Open Data.
The file is bulk (province-wide) and updated annually, so a 30-day freshness TTL is used.
Unlike query-based ingest modules, this saves to data/raw/ not data/cache/.
"""

import csv
import logging
import time
from datetime import datetime
from pathlib import Path

import httpx

from src.models.stocking_record import StockingRecord

_DOWNLOAD_URL = "https://geohub.lio.gov.on.ca/datasets/c725d683af734e6da7850fe0f0b73eb3_0.csv"
_RAW_PATH = Path("data/raw/mnrf_stocking.csv")
_TTL_SECONDS = 30 * 86400  # 30 days
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

logger = logging.getLogger(__name__)


def download_stocking_data() -> Path:
    """Download the MNRF stocking CSV. Returns path; skips if file is less than 30 days old."""
    if _RAW_PATH.exists():
        age = time.time() - _RAW_PATH.stat().st_mtime
        if age < _TTL_SECONDS:
            logger.info("MNRF stocking CSV is fresh (%.0f days old), skipping", age / 86400)
            return _RAW_PATH

    _RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading MNRF stocking CSV from GeoHub…")

    with httpx.stream(
        "GET",
        _DOWNLOAD_URL,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
        timeout=120,
    ) as response:
        response.raise_for_status()
        with _RAW_PATH.open("wb") as f:
            for chunk in response.iter_bytes(chunk_size=65536):
                f.write(chunk)

    logger.info("Downloaded MNRF stocking CSV to %s", _RAW_PATH)
    return _RAW_PATH


def parse_stocking_records(csv_path: Path) -> list[StockingRecord]:
    """Parse the MNRF stocking CSV into StockingRecord models.

    Skips rows with no usable waterbody name. Logs a warning for each skipped row.
    """
    records: list[StockingRecord] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            # Strip whitespace from keys and values
            row = {k.strip(): v.strip() for k, v in row.items()}
            try:
                record = _parse_row(i, row)
            except Exception as exc:
                logger.warning("Row %d: skipping — %s", i, exc)
                continue
            if record is not None:
                records.append(record)
    return records


def _parse_row(row_num: int, row: dict) -> StockingRecord | None:
    # Waterbody name: prefer official, fall back to unofficial (note: typo in real CSV header)
    official = row.get("Official_Waterbody_Name", "").strip()
    unofficial = row.get("Unoffcial_Waterbody_Name", "").strip()
    waterbody_name = official or unofficial
    if not waterbody_name:
        logger.warning("Row %d: no waterbody name, skipping", row_num)
        return None

    year_str = row.get("Stocking_Year", "").strip()
    if not year_str:
        raise ValueError("missing Stocking_Year")
    year = int(year_str)

    lat_str = row.get("Latitude", "").strip()
    lng_str = row.get("Longitude", "").strip()
    lat = float(lat_str) if lat_str else None
    lng = float(lng_str) if lng_str else None

    qty_str = row.get("Number_of_Fish_Stocked", "").strip()
    quantity = int(qty_str) if qty_str else None

    species_raw = row.get("Species", "").strip()
    species = species_raw.title() if species_raw else ""
    if not species:
        raise ValueError("missing Species")

    object_id = row.get("ObjectId", "").strip()
    if not object_id:
        raise ValueError("missing ObjectId")
    record_id = str(object_id)

    life_stage = row.get("Developmental_Stage", "").strip() or None
    municipality = row.get("Geographic_Township", "").strip() or None
    county = row.get("MNRF_District", "").strip() or None
    waterbody_code = row.get("Waterbody_Location_Identifier", "").strip() or None

    stocked_at = datetime(year, 1, 1)

    return StockingRecord(
        record_id=record_id,
        waterbody_name=waterbody_name,
        waterbody_code=waterbody_code,
        municipality=municipality,
        county=county,
        lat=lat,
        lng=lng,
        jurisdiction="CA-ON",
        species=species,
        year=year,
        quantity=quantity,
        life_stage=life_stage,
        stocked_at=stocked_at,
    )
