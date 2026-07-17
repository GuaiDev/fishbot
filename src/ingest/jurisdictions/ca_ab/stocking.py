"""Alberta fish stocking records — planned stocking XLSX from Open Alberta.

Downloads the annual Alberta planned trout stocking schedule as an XLSX file
from the Open Alberta data catalogue and parses it into stocking_records rows.

Source:
  Open Alberta dataset ae7521d6-7629-4b69-ac45-857fc798c10c
  https://open.alberta.ca/dataset/ae7521d6-7629-4b69-ac45-857fc798c10c
  A new dated XLSX resource ("Trout planned stocking dates <YEAR>") is added
  every year, so the URL is resolved dynamically via CKAN package_show
  (same pattern as ca_ab/regulations.py and ca_bc/nuseds.py) rather than
  hardcoded.

The file is NOT a plain table: rows 1-6 are a title block ("TROUT PLANNED
STOCKING 2026", a note, blank rows) before the real header row. The header
row is located by scanning for the first row containing a "SPECIES" cell,
rather than assuming row 1, since the exact title-block row count is not
guaranteed to stay the same across years.

Contrary to an earlier version of this docstring, the current (2026) file
DOES include coordinates — LATITUDE/LONGITUDE columns, one row per
species/size-class per waterbody. Species are Alberta's standard trout
stocking codes (BKTR/RNTR/BNTR/TGTR/WSCT) rather than full names; these are
mapped to full names in `species`, with the raw code preserved in
`species_code`.

There is no clean stocking date or life-stage field. "PROPOSED SIZE STOCKED
- CM" holds a strain/size notation (e.g. "15cm 3N", ">35cm 2N") rather than
a fry/fingerling/yearling vocabulary — stored as-is in `life_stage`.
"PLANNED STOCKING DATE" is unstructured scheduling text ("odd years only
between September 15th - October 15th", "stock every three years next
2025 before June 15") with no consistent format to parse a month from —
rather than fabricate a month or silently drop this real scheduling
information, the raw text is preserved in `stocking_purpose` (the closest
available free-text column; not semantically "purpose" but the only spare
field in the shared stocking_records schema). `month` and `stocked_at` are
left None since no reliable date can be extracted.

Requirements:
  openpyxl (for XLSX reading). Install with: uv add openpyxl

Table: stocking_records (shared schema with MNRF stocking)

Cache TTL: 365 days (annual release).
"""

import logging
import re
import time
from pathlib import Path

import httpx

_PACKAGE_URL = "https://open.alberta.ca/api/3/action/package_show"
_PACKAGE_ID = "ae7521d6-7629-4b69-ac45-857fc798c10c"
_XLSX_PATH = Path("data/raw/ab_stocking.xlsx")
_PACKAGE_CACHE_PATH = Path("data/cache/ab_stocking/package_meta.json")
_XLSX_CACHE_TTL_SECONDS = 365 * 86400
_PACKAGE_CACHE_TTL_SECONDS = 30 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

# Standard Alberta trout stocking species codes -> full name.
_SPECIES_CODES: dict[str, str] = {
    "BKTR": "Brook Trout",
    "RNTR": "Rainbow Trout",
    "BNTR": "Brown Trout",
    "TGTR": "Tiger Trout",
    "WSCT": "Westslope Cutthroat Trout",
}

logger = logging.getLogger(__name__)


def fetch_stocking_records() -> list[dict]:
    """Download and parse the current Alberta planned stocking XLSX.

    Returns list of row dicts for stocking_records table.
    """
    try:
        import openpyxl  # type: ignore
    except ImportError:
        logger.warning(
            "AB stocking: openpyxl not installed — cannot read XLSX. "
            "Install with: uv add openpyxl. Returning 0 records."
        )
        return []

    resolved = _find_current_xlsx()
    if not resolved:
        logger.warning(
            "AB stocking: could not resolve current XLSX URL from the CKAN package. "
            "Check https://open.alberta.ca/dataset/ae7521d6-7629-4b69-ac45-857fc798c10c "
            "for the current resource name/URL."
        )
        return []
    xlsx_url, stocking_year = resolved

    _download_xlsx_if_stale(xlsx_url)
    if not _XLSX_PATH.exists():
        logger.error("AB stocking: XLSX not found at %s", _XLSX_PATH)
        return []

    logger.info("AB stocking: parsing XLSX %s", _XLSX_PATH)
    wb = openpyxl.load_workbook(_XLSX_PATH, read_only=True, data_only=True)
    ws = wb.active

    all_rows = list(ws.iter_rows(values_only=True))
    header_i = _find_header_row(all_rows)
    if header_i is None:
        logger.error("AB stocking: could not locate header row (no 'SPECIES' cell found)")
        wb.close()
        return []

    header = [_normalize_header(h) for h in all_rows[header_i]]
    logger.info("AB stocking: columns: %s", [h for h in header if h])

    def col(name: str) -> int | None:
        try:
            return header.index(name)
        except ValueError:
            return None

    idx = {
        "district": col("DISTRICT"),
        "waterbody": col("WATERBODY NAME") or col("WATER BODY"),
        "lat": col("LATITUDE"),
        "lng": col("LONGITUDE"),
        "species": col("SPECIES"),
        "size": col("PROPOSED SIZE STOCKED - CM") or col("STOCKED - CM"),
        "quantity": col("STOCKING NUMBER") or col("NUMBER"),
        "planned_date": col("PLANNED STOCKING DATE") or col("DATE"),
    }

    rows: list[dict] = []
    n_skipped = 0
    for i, raw_row in enumerate(all_rows[header_i + 1 :]):

        def get(field: str):
            j = idx[field]
            return raw_row[j] if j is not None else None

        waterbody = str(get("waterbody") or "").strip()
        species_code = str(get("species") or "").strip().upper()
        species = _SPECIES_CODES.get(species_code)

        if not waterbody or not species:
            n_skipped += 1
            continue

        try:
            quantity = int(get("quantity")) if get("quantity") is not None else None
        except (TypeError, ValueError):
            quantity = None
        try:
            lat = float(get("lat")) if get("lat") is not None else None
        except (TypeError, ValueError):
            lat = None
        try:
            lng = float(get("lng")) if get("lng") is not None else None
        except (TypeError, ValueError):
            lng = None

        district = str(get("district") or "").strip() or None
        size = str(get("size") or "").strip() or None
        planned_date = str(get("planned_date") or "").strip() or None

        rows.append(
            {
                "record_id": f"AB_{stocking_year}_{header_i + 1 + i}",
                "waterbody_name": waterbody,
                "waterbody_code": None,
                "municipality": district,
                "county": None,
                "lat": lat,
                "lng": lng,
                "jurisdiction": "CA-AB",
                "species": species,
                "species_code": species_code,
                "year": stocking_year,
                "month": None,
                "quantity": quantity,
                "life_stage": size,
                "stocking_purpose": planned_date,
                "stocked_at": None,
            }
        )

    wb.close()
    logger.info(
        "AB stocking: %d records parsed (%d rows skipped — missing waterbody/species)",
        len(rows),
        n_skipped,
    )
    return rows


def _normalize_header(h) -> str:
    return re.sub(r"\s+", " ", str(h or "")).strip().upper()


def _find_header_row(all_rows: list[tuple]) -> int | None:
    """Return the index of the first row containing a 'SPECIES' cell.

    The file has a variable-length title block before the real header —
    scanning for the SPECIES marker is more robust than assuming a fixed
    row offset.
    """
    for i, row in enumerate(all_rows):
        normalized = {_normalize_header(c) for c in row}
        if "SPECIES" in normalized:
            return i
    return None


def _find_current_xlsx() -> tuple[str, int] | None:
    """Resolve the current-year XLSX URL + year via CKAN package_show.

    Picks the XLSX-format resource whose name contains the highest 4-digit
    year (falls back to the most-recently-created resource on a tie).
    """
    _PACKAGE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    pkg = None
    if _PACKAGE_CACHE_PATH.exists():
        age = time.time() - _PACKAGE_CACHE_PATH.stat().st_mtime
        if age < _PACKAGE_CACHE_TTL_SECONDS:
            import json

            pkg = json.loads(_PACKAGE_CACHE_PATH.read_text())

    if pkg is None:
        try:
            resp = httpx.get(
                _PACKAGE_URL,
                params={"id": _PACKAGE_ID},
                headers={"User-Agent": _USER_AGENT},
                timeout=30,
            )
            resp.raise_for_status()
            import json

            pkg = resp.json().get("result", {})
            _PACKAGE_CACHE_PATH.write_text(json.dumps(pkg))
        except Exception as exc:
            logger.error("AB stocking: CKAN package fetch failed: %s", exc)
            return None

    best: tuple[int, str, str] | None = None  # (year, created, url)
    for resource in pkg.get("resources", []):
        fmt = (resource.get("format") or "").lower()
        if fmt != "xlsx":
            continue
        name = resource.get("name") or ""
        year_match = re.search(r"(20\d{2})", name)
        if not year_match:
            continue
        year = int(year_match.group(1))
        created = resource.get("created") or ""
        url = resource.get("url") or ""
        if not url:
            continue
        if best is None or (year, created) > (best[0], best[1]):
            best = (year, created, url)

    if best is None:
        return None
    year, _created, url = best
    logger.info("AB stocking: resolved %d edition: %s", year, url)
    return url, year


def _download_xlsx_if_stale(url: str) -> None:
    _XLSX_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _XLSX_PATH.exists():
        age = time.time() - _XLSX_PATH.stat().st_mtime
        if age < _XLSX_CACHE_TTL_SECONDS:
            logger.info("AB stocking: XLSX cache fresh, skipping download")
            return
    logger.info("AB stocking: downloading XLSX from Open Alberta …")
    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            timeout=120,
        )
        response.raise_for_status()
        _XLSX_PATH.write_bytes(response.content)
        logger.info("AB stocking: downloaded %.1f MB", len(response.content) / 1_048_576)
    except Exception as exc:
        logger.error("AB stocking: download failed: %s", exc)
