"""CABIN benthic macroinvertebrate ingestion for Ontario (CA-ON).

Downloads CABIN BINAT (Canadian Aquatic Biomonitoring Network) benthic
invertebrate data from Environment and Climate Change Canada via the
open.canada.ca CKAN API. Filters to Ontario, computes EPT metrics per
site visit, and returns BenthicSample models.

EPT (Ephemeroptera, Plecoptera, Trichoptera) proportion is a standard
proxy for benthic habitat quality: high-EPT reaches have clean,
well-oxygenated gravel substrate; low-EPT reaches are degraded.
"""

import csv
import json
import logging
import time
from pathlib import Path

import httpx

from src.models.benthic_sample import BenthicSample

_CKAN_API = "https://open.canada.ca/api/3/action/package_show"
_PACKAGE_ID = "13564ca4-e330-40a5-9521-bfb1be767147"
_CACHE_DIR = Path("data/cache/cabin")
_RAW_DIR = Path("data/raw")
_PACKAGE_TTL = 30 * 86400
_CSV_TTL = 30 * 86400
_SCALE_TARGET = 500.0
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

logger = logging.getLogger(__name__)

# Non-taxon metadata columns (after bilingual normalization)
_META_COLS: frozenset[str] = frozenset(
    {
        "SiteVisitID",
        "Site",
        "SiteName",
        "Latitude",
        "Longitude",
        "Province",
        "VisitYear",
        "Year",
        "JulianDay",
        "StreamOrder",
        "LocalBasin",
        "SubSample",
        "SubSampleType",
        "Comments",
        "Datum",
        "DataSource",
        "StudyName",
        "Agency",
        "Waterbody",
        "WaterbodyName",
        "StreamName",
        "SiteDescription",
        "Method",
        "Habitat",
        "Substrate",
        "HabitatType",
    }
)

# EPT family names — columns matching these are clean-water indicator taxa
_EPT_FAMILIES: frozenset[str] = frozenset(
    {
        # Ephemeroptera (mayflies)
        "Baetidae",
        "Ephemerellidae",
        "Heptageniidae",
        "Siphlonuridae",
        "Leptophlebiidae",
        "Caenidae",
        "Ephemeridae",
        "Tricorythidae",
        "Polymitarcyidae",
        "Potamanthidae",
        "Neoephemeridae",
        "Isonychiidae",
        "Metretopodidae",
        "Ametropodidae",
        # Plecoptera (stoneflies)
        "Capniidae",
        "Chloroperlidae",
        "Leuctridae",
        "Nemouridae",
        "Perlidae",
        "Perlodidae",
        "Pteronarcyidae",
        "Taeniopterygidae",
        # Trichoptera (caddisflies)
        "Brachycentridae",
        "Glossosomatidae",
        "Hydropsychidae",
        "Hydroptilidae",
        "Lepidostomatidae",
        "Leptoceridae",
        "Limnephilidae",
        "Molannidae",
        "Odontoceridae",
        "Philopotamidae",
        "Phryganeidae",
        "Polycentropodidae",
        "Psychomyiidae",
        "Rhyacophilidae",
        "Sericostomatidae",
        "Uenoidae",
    }
)

# Coarser order-level EPT names, used when data is at order resolution
_EPT_ORDERS: frozenset[str] = frozenset(
    {
        "Ephemeroptera",
        "Plecoptera",
        "Trichoptera",
    }
)


def _normalize_col(col: str) -> str:
    """Strip bilingual suffix from column header.

    'SiteVisitID/IDVisite' → 'SiteVisitID'
    'Province/Province'    → 'Province'
    'Baetidae'             → 'Baetidae'
    """
    if "/" in col:
        return col.split("/")[0].strip()
    return col.strip()


def _is_ept(col: str) -> bool:
    return col in _EPT_FAMILIES or col in _EPT_ORDERS


def _habitat_quality(ept_prop: float) -> str:
    if ept_prop >= 0.5:
        return "high"
    if ept_prop >= 0.25:
        return "moderate"
    return "impaired"


def _parse_float(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_int(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _get_cabin_resources() -> list[dict]:
    """Query CKAN for CABIN BINAT CSV resources. Returns [{name, url}]."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pkg_cache = _CACHE_DIR / "cabin_package.json"

    if pkg_cache.exists() and time.time() - pkg_cache.stat().st_mtime < _PACKAGE_TTL:
        pkg = json.loads(pkg_cache.read_text())
    else:
        logger.info("Fetching CABIN CKAN package metadata…")
        try:
            r = httpx.get(
                _CKAN_API,
                params={"id": _PACKAGE_ID},
                timeout=30,
                headers={"User-Agent": _USER_AGENT},
            )
            r.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning("CABIN CKAN API unavailable: %s — skipping benthic ingest", exc)
            return []
        pkg = r.json()
        pkg_cache.write_text(json.dumps(pkg))

    resources = pkg.get("result", {}).get("resources", [])
    csv_resources = []
    for res in resources:
        url = res.get("url", "")
        fmt = res.get("format", "").upper()
        name = res.get("name", "")
        if fmt == "CSV" or url.lower().endswith(".csv"):
            csv_resources.append({"name": name, "url": url})
    logger.info("Found %d CABIN CSV resources", len(csv_resources))
    return csv_resources


def download_cabin_csv(name: str, url: str) -> Path | None:
    """Download one CABIN CSV file with caching. Returns path or None on failure."""
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:60]
    dest = _RAW_DIR / f"cabin_{safe_name}.csv"
    _RAW_DIR.mkdir(parents=True, exist_ok=True)

    if dest.exists() and time.time() - dest.stat().st_mtime < _CSV_TTL:
        logger.info("CABIN CSV '%s' is fresh, skipping download", name)
        return dest

    logger.info("Downloading CABIN CSV '%s' from %s…", name, url)
    try:
        with httpx.stream(
            "GET",
            url,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            timeout=120,
        ) as r:
            if r.status_code == 404:
                logger.warning("CABIN CSV '%s' returned 404, skipping", name)
                return None
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
    except httpx.HTTPStatusError as exc:
        logger.warning("CABIN CSV '%s' download failed: %s", name, exc)
        return None
    logger.info("Downloaded CABIN CSV '%s' to %s", name, dest)
    return dest


def parse_cabin_data(csv_path: Path) -> list[BenthicSample]:
    """Parse a CABIN BINAT wide-format CSV into BenthicSample models.

    Filters to Ontario (Province == 'ON'). Normalizes bilingual column
    headers. Scales taxon counts by SubSample when SubSample > 0;
    uses raw counts when SubSample == 0. Skips rows with zero total
    abundance.
    """
    records: list[BenthicSample] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            logger.warning("CABIN CSV %s has no header row", csv_path)
            return records

        # Normalize bilingual headers once; build old→new mapping
        norm_map: dict[str, str] = {raw: _normalize_col(raw) for raw in reader.fieldnames}

        for i, raw_row in enumerate(reader, start=1):
            row = {norm_map[k]: v.strip() for k, v in raw_row.items() if k}
            record = _parse_row(i, row, reader.fieldnames)
            if record is not None:
                records.append(record)

    return records


def _parse_row(row_num: int, row: dict, raw_fieldnames: list[str]) -> BenthicSample | None:
    province = row.get("Province", "").strip().upper()
    if province != "ON":
        return None

    visit_id = row.get("SiteVisitID", "").strip()
    if not visit_id:
        logger.warning("CABIN row %d: missing SiteVisitID, skipping", row_num)
        return None

    year_str = row.get("VisitYear", "") or row.get("Year", "")
    year = _parse_int(year_str)
    if year is None:
        logger.warning("CABIN row %d: missing year, skipping", row_num)
        return None

    site_code = row.get("Site", "").strip() or visit_id
    site_name = row.get("SiteName", "").strip() or None
    lat = _parse_float(row.get("Latitude", ""))
    lng = _parse_float(row.get("Longitude", ""))
    julian_day = _parse_int(row.get("JulianDay", ""))
    stream_order = _parse_int(row.get("StreamOrder", ""))
    local_basin = row.get("LocalBasin", "").strip() or None

    subsample_str = row.get("SubSample", "0").strip()
    subsample = float(subsample_str) if subsample_str else 0.0

    # Identify taxon columns: normalized name not in metadata set
    norm_names = {_normalize_col(h) for h in raw_fieldnames}
    taxon_cols = [c for c in norm_names if c not in _META_COLS]

    ept_richness = 0
    ept_raw = 0.0
    total_raw = 0.0
    total_taxa = 0

    for col in taxon_cols:
        count_str = row.get(col, "").strip()
        if not count_str:
            continue
        try:
            count = float(count_str)
        except ValueError:
            continue
        if count > 0:
            total_taxa += 1
            total_raw += count
            if _is_ept(col):
                ept_richness += 1
                ept_raw += count

    if total_raw == 0:
        logger.warning("CABIN row %d (%s): zero total abundance, skipping", row_num, visit_id)
        return None

    # Scale by SubSample to normalize across sites; skip division when SubSample == 0
    if subsample > 0:
        ept_count = ept_raw / subsample * _SCALE_TARGET
        total_count = total_raw / subsample * _SCALE_TARGET
    else:
        ept_count = ept_raw
        total_count = total_raw

    ept_proportion = ept_count / total_count

    return BenthicSample(
        site_visit_id=visit_id,
        site_code=site_code,
        site_name=site_name,
        lat=lat,
        lng=lng,
        jurisdiction="CA-ON",
        sampled_year=year,
        sampled_julian_day=julian_day,
        stream_order=stream_order,
        local_basin=local_basin,
        ept_richness=ept_richness,
        ept_count=round(ept_count, 4),
        total_count=round(total_count, 4),
        ept_proportion=round(ept_proportion, 4),
        total_taxa_richness=total_taxa,
        habitat_quality=_habitat_quality(ept_proportion),
    )
