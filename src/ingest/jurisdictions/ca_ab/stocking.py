"""Alberta fish stocking records — planned stocking XLSX from Open Alberta.

Downloads the annual Alberta planned fish stocking schedule as an XLSX file
from the Open Alberta data catalogue.

Source:
  https://open.alberta.ca/dataset/ae7521d6-7629-4b69-ac45-857fc798c10c/
  resource/48b6985f-a110-488e-8508-5546dd6e10fd/download/
  fp-fish-stocking-planned-dates-2026.xlsx

Note: Alberta stocking data does not include coordinates — waterbody names
are provided but lat/lng fields are null. Match to water_features via name
if coordinates are needed downstream.

Requirements:
  openpyxl (for XLSX reading). Install with: uv add openpyxl

Table: stocking_records (shared schema with MNRF stocking)

Cache TTL: 365 days (annual release).
"""

import logging
import time
from pathlib import Path

import httpx

_XLSX_URL = (
    "https://open.alberta.ca/dataset/ae7521d6-7629-4b69-ac45-857fc798c10c/"
    "resource/48b6985f-a110-488e-8508-5546dd6e10fd/download/"
    "fp-fish-stocking-planned-dates-2026.xlsx"
)
_STOCKING_YEAR = 2026
_XLSX_PATH = Path(f"data/raw/ab_stocking_{_STOCKING_YEAR}.xlsx")
_CACHE_TTL_SECONDS = 365 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

logger = logging.getLogger(__name__)


def fetch_stocking_records() -> list[dict]:
    """Download and parse Alberta planned stocking XLSX.

    Returns list of row dicts for stocking_records table.
    Note: lat/lng are null — Alberta data does not include coordinates.
    """
    try:
        import openpyxl  # type: ignore
    except ImportError:
        logger.warning(
            "AB stocking: openpyxl not installed — cannot read XLSX. "
            "Install with: uv add openpyxl. Returning 0 records."
        )
        return []

    _download_xlsx_if_stale()
    if not _XLSX_PATH.exists():
        logger.error("AB stocking: XLSX not found at %s", _XLSX_PATH)
        return []

    logger.info("AB stocking: parsing XLSX %s", _XLSX_PATH)
    wb = openpyxl.load_workbook(_XLSX_PATH, read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    header_raw = next(rows_iter, None)
    if header_raw is None:
        logger.error("AB stocking: XLSX has no header row")
        wb.close()
        return []

    header = [str(h or "").strip().upper() for h in header_raw]
    logger.info("AB stocking: columns: %s", header)

    def col(name: str) -> int | None:
        try:
            return header.index(name)
        except ValueError:
            return None

    # Alberta stocking XLSX common column names (may vary by year)
    idx = {
        "waterbody": col("WATER BODY") or col("WATERBODY") or col("LAKE NAME") or col("LOCATION"),
        "region":    col("REGION") or col("FISH AND WILDLIFE REGION"),
        "species":   col("SPECIES") or col("FISH SPECIES"),
        "strain":    col("STRAIN") or col("STRAIN/TYPE"),
        "quantity":  col("NUMBER") or col("QUANTITY") or col("# STOCKED") or col("TARGET NUMBER"),
        "life_stage": col("LIFE STAGE") or col("STAGE") or col("SIZE CLASS"),
        "stocking_date": col("DATE") or col("STOCKING DATE") or col("PLANNED DATE"),
        "month":     col("MONTH") or col("STOCKING MONTH"),
    }

    rows: list[dict] = []
    for i, raw_row in enumerate(rows_iter):
        waterbody = (
            str(raw_row[idx["waterbody"]] or "").strip() if idx["waterbody"] is not None else ""
        )
        if not waterbody:
            continue

        species = str(raw_row[idx["species"]] or "").strip() if idx["species"] is not None else ""
        strain = str(raw_row[idx["strain"]] or "").strip() if idx["strain"] is not None else ""
        region = str(raw_row[idx["region"]] or "").strip() if idx["region"] is not None else ""
        life_stage = (
            str(raw_row[idx["life_stage"]] or "").strip() if idx["life_stage"] is not None else ""
        )

        try:
            quantity = int(raw_row[idx["quantity"]]) if idx["quantity"] is not None else None
        except (TypeError, ValueError):
            quantity = None

        try:
            month_raw = raw_row[idx["month"]] if idx["month"] is not None else None
            month = int(month_raw) if month_raw is not None else None
        except (TypeError, ValueError):
            month = None

        stocked_at = f"{_STOCKING_YEAR}-{month:02d}-01" if month else f"{_STOCKING_YEAR}-01-01"
        record_id = f"AB_{_STOCKING_YEAR}_{i}"

        rows.append({
            "record_id": record_id,
            "waterbody_name": waterbody,
            "waterbody_code": None,
            "municipality": region or None,
            "county": None,
            "lat": None,
            "lng": None,
            "jurisdiction": "CA-AB",
            "species": species or "Unknown",
            "species_code": strain or None,
            "year": _STOCKING_YEAR,
            "month": month,
            "quantity": quantity,
            "life_stage": life_stage or None,
            "stocking_purpose": None,
            "stocked_at": stocked_at,
        })

    wb.close()
    logger.info("AB stocking: %d records parsed", len(rows))
    return rows


def _download_xlsx_if_stale() -> None:
    _XLSX_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _XLSX_PATH.exists():
        age = time.time() - _XLSX_PATH.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            logger.info("AB stocking: XLSX cache fresh, skipping download")
            return
    logger.info("AB stocking: downloading XLSX from Open Alberta …")
    try:
        response = httpx.get(
            _XLSX_URL,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            timeout=120,
        )
        response.raise_for_status()
        _XLSX_PATH.write_bytes(response.content)
        logger.info("AB stocking: downloaded %.1f MB", len(response.content) / 1_048_576)
    except Exception as exc:
        logger.error("AB stocking: download failed: %s", exc)
