"""NuSEDS salmon escapement data for BC (and Yukon — filtered to BC).

Downloads the DFO NuSEDS (New Salmon Escapement Database System) simplified
XLSX file — 9,100+ spawning populations with annual escapement counts going
back to the 1920s.

Source:
  https://api-proxy.edh-cde.dfo-mpo.gc.ca/catalogue/records/
  c48669a3-045b-400d-b730-48aafe8c5ee6/attachments/
  All Areas Simplified Version_20251030.xlsx

Requirements:
  openpyxl (for XLSX reading). Install with: uv add openpyxl
  Without openpyxl this module returns 0 records with a clear warning.

Table: salmon_escapement
  record_id (PK), population_id, waterbody_name, gazetted_name, watershed_code,
  species, analysis_year, max_estimate, stream_lat, stream_lng,
  jurisdiction='CA-BC', source='NuSEDS'

Cache TTL: 365 days (annual release).
"""

import logging
import time
from pathlib import Path

import httpx

_XLSX_URL = (
    "https://api-proxy.edh-cde.dfo-mpo.gc.ca/catalogue/records/"
    "c48669a3-045b-400d-b730-48aafe8c5ee6/attachments/"
    "All Areas Simplified Version_20251030.xlsx"
)
_XLSX_PATH = Path("data/raw/nuseds_all_areas_simplified.xlsx")
_CACHE_TTL_SECONDS = 365 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

# AREA field values that belong to BC (not Yukon, not other provinces)
_BC_AREA_KEYWORDS = frozenset({
    "fraser",
    "columbia",
    "skeena",
    "nass",
    "central coast",
    "vancouver island",
    "haida gwaii",
    "queen charlotte",
    "okanagan",
    "thompson",
    "boundary bay",
    "strait of georgia",
    "johnstone strait",
    "queen charlotte strait",
    "rivers inlet",
    "smith inlet",
    "bute inlet",
    "howe sound",
    "harrison",
    "lillooet",
    "chilcotin",
    "nicola",
    "similkameen",
})

logger = logging.getLogger(__name__)


def fetch_salmon_escapement() -> list[dict]:
    """Download and parse NuSEDS XLSX. Returns rows for salmon_escapement table.

    Returns empty list if openpyxl is not installed or the download fails.
    Filters to BC only (excludes Yukon and other provinces).
    """
    try:
        import openpyxl  # type: ignore
    except ImportError:
        logger.warning(
            "NuSEDS: openpyxl not installed — cannot read XLSX files. "
            "Install with: uv add openpyxl. Returning 0 records."
        )
        return []

    _download_xlsx_if_stale()
    if not _XLSX_PATH.exists():
        logger.error("NuSEDS: XLSX not found at %s", _XLSX_PATH)
        return []

    logger.info("NuSEDS: parsing XLSX — %s", _XLSX_PATH)
    wb = openpyxl.load_workbook(_XLSX_PATH, read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    header_raw = next(rows_iter, None)
    if header_raw is None:
        logger.error("NuSEDS: XLSX has no header row")
        return []

    # Normalize header: strip whitespace, uppercase
    header = [str(h or "").strip().upper() for h in header_raw]
    logger.info("NuSEDS: XLSX columns: %s", header[:20])

    def col(name: str) -> int | None:
        try:
            return header.index(name)
        except ValueError:
            return None

    # Map expected column names (the XLSX may use these or variants)
    idx = {
        "pop_id":       col("POPULATION_ID") or col("POP_ID"),
        "area":         col("AREA") or col("REGION"),
        "stream":       col("STREAM") or col("STREAM_NAME") or col("WATERBODY_NAME"),
        "gazetted":     col("GAZETTED_NAME") or col("GAZETTED"),
        "watershed":    col("WATERSHED_CDE") or col("WATERSHED_CODE"),
        "species":      col("SPECIES") or col("SPECIES_QUALIFIED"),
        "year":         col("ANALYSIS_YR") or col("YEAR") or col("ANALYSIS_YEAR"),
        "estimate":     col("MAX_ESTIMATE") or col("ESTIMATE") or col("MAX"),
        "lat":          col("Y") or col("LAT") or col("LATITUDE"),
        "lng":          col("X") or col("LON") or col("LONGITUDE") or col("LNG"),
    }

    rows: list[dict] = []
    n_skipped_region = 0

    for raw_row in rows_iter:
        area = str(raw_row[idx["area"]] or "").strip().lower() if idx["area"] is not None else ""
        if not any(kw in area for kw in _BC_AREA_KEYWORDS):
            n_skipped_region += 1
            continue

        pop_id = str(raw_row[idx["pop_id"]] or "").strip() if idx["pop_id"] is not None else ""
        stream = str(raw_row[idx["stream"]] or "").strip() if idx["stream"] is not None else ""
        gazetted = str(raw_row[idx["gazetted"]] or "").strip() if idx["gazetted"] is not None else ""
        watershed = str(raw_row[idx["watershed"]] or "").strip() if idx["watershed"] is not None else ""
        species = str(raw_row[idx["species"]] or "").strip() if idx["species"] is not None else ""

        try:
            year = int(raw_row[idx["year"]]) if idx["year"] is not None else None
        except (TypeError, ValueError):
            year = None
        try:
            estimate = int(raw_row[idx["estimate"]]) if idx["estimate"] is not None else None
        except (TypeError, ValueError):
            estimate = None
        try:
            slat = float(raw_row[idx["lat"]]) if idx["lat"] is not None else None
        except (TypeError, ValueError):
            slat = None
        try:
            slng = float(raw_row[idx["lng"]]) if idx["lng"] is not None else None
        except (TypeError, ValueError):
            slng = None

        if not pop_id or not species or year is None:
            continue

        record_id = f"NUSEDS_{pop_id}_{year}_{species[:20]}"
        rows.append({
            "record_id": record_id,
            "population_id": pop_id,
            "waterbody_name": stream or None,
            "gazetted_name": gazetted or None,
            "watershed_code": watershed or None,
            "species": species,
            "analysis_year": year,
            "max_estimate": estimate,
            "stream_lat": slat,
            "stream_lng": slng,
            "jurisdiction": "CA-BC",
            "source": "NuSEDS",
            "ingested_at": None,  # set by caller
        })

    wb.close()
    logger.info(
        "NuSEDS: %d BC records extracted (%d non-BC rows skipped)",
        len(rows), n_skipped_region,
    )
    return rows


def _download_xlsx_if_stale() -> None:
    _XLSX_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _XLSX_PATH.exists():
        age = time.time() - _XLSX_PATH.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            logger.info("NuSEDS: XLSX cache fresh, skipping download")
            return
    logger.info("NuSEDS: downloading from DFO EDH …")
    try:
        response = httpx.get(
            _XLSX_URL,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            timeout=300,
        )
        response.raise_for_status()
        _XLSX_PATH.write_bytes(response.content)
        logger.info("NuSEDS: downloaded %.1f MB", len(response.content) / 1_048_576)
    except Exception as exc:
        logger.error("NuSEDS: download failed: %s", exc)
