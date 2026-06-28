"""CABIN benthic macroinvertebrate ingestion — all Canadian provinces.

Downloads two CSV files from cabin-rcba.ec.gc.ca (Environment and Climate
Change Canada) with a 30-day cache:

  cabin_study_data_mda02_1987-present.csv   (~4 MB)   — site visit metadata
  cabin_benthic_data_mda02_1987-present.csv (~95 MB)  — long-format taxon counts

The benthic file has one row per taxon per site visit. Province filtering is
done via the study file (Province field); all Canadian provinces are ingested
with jurisdiction codes derived from the Province abbreviation. Province is
blank in benthic rows so the study file is authoritative.

EPT (Ephemeroptera, Plecoptera, Trichoptera) proportion is a standard proxy
for benthic habitat quality: high-EPT reaches have clean, well-oxygenated
substrate; low-EPT reaches are degraded or impaired.

Both files are UTF-16 LE with BOM. The encoding is detected at runtime so
UTF-8 test fixtures work without changes.
"""

import csv
import logging
import time
from pathlib import Path

import httpx

from src.models.benthic_sample import BenthicSample

_STUDY_URL = "https://cabin-rcba.ec.gc.ca/Cabin/opendata/cabin_study_data_mda02_1987-present.csv"
_BENTHIC_URL = (
    "https://cabin-rcba.ec.gc.ca/Cabin/opendata/cabin_benthic_data_mda02_1987-present.csv"
)
_STUDY_PATH = Path("data/raw/cabin_study_mda02.csv")
_BENTHIC_PATH = Path("data/raw/cabin_benthic_mda02.csv")
_TTL = 30 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

logger = logging.getLogger(__name__)

# EPT family names — presence indicates clean-water habitat
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

# Order-level EPT names used when the row lacks family-level resolution
_EPT_ORDERS: frozenset[str] = frozenset({"Ephemeroptera", "Plecoptera", "Trichoptera"})


def _normalize_col(col: str) -> str:
    """Strip bilingual French suffix from a CABIN column header.

    'SiteVisitID/IdentifiantdeVisite' → 'SiteVisitID'
    'Order/Ordre'                      → 'Order'
    'Latitude'                         → 'Latitude'
    """
    if "/" in col:
        return col.split("/")[0].strip()
    return col.strip()


def _is_ept_taxon(order: str, family: str) -> bool:
    """True if the taxon is an EPT order or belongs to an EPT family."""
    if family in _EPT_FAMILIES:
        return True
    if order in _EPT_ORDERS and not family:
        return True
    return False


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


def _detect_encoding(path: Path) -> str:
    """Return the file's encoding by inspecting the BOM."""
    with path.open("rb") as f:
        bom = f.read(4)
    if bom[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    if bom[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    return "utf-8"


def _download_if_stale(url: str, path: Path, ttl: int) -> Path:
    """Download url → path unless file exists and is younger than ttl seconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < ttl:
            logger.info("Cache fresh, skipping download: %s", path.name)
            return path
    logger.info("Downloading %s …", url)
    with httpx.stream(
        "GET",
        url,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
        timeout=120,
    ) as r:
        r.raise_for_status()
        with path.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=8192):
                f.write(chunk)
    logger.info("Downloaded %s (%.1f MB)", path.name, path.stat().st_size / 1_048_576)
    return path


def download_study() -> Path:
    """Download the CABIN study metadata CSV. Returns local path."""
    return _download_if_stale(_STUDY_URL, _STUDY_PATH, _TTL)


def download_benthic() -> Path:
    """Download the CABIN benthic taxon counts CSV (streaming). Returns local path."""
    return _download_if_stale(_BENTHIC_URL, _BENTHIC_PATH, _TTL)


# Province abbreviation → ISO 3166-2 jurisdiction code
_PROVINCE_TO_JURISDICTION: dict[str, str] = {
    "ON": "CA-ON",
    "BC": "CA-BC",
    "AB": "CA-AB",
    "QC": "CA-QC",
    "MB": "CA-MB",
    "SK": "CA-SK",
    "NB": "CA-NB",
    "NS": "CA-NS",
    "PE": "CA-PE",
    "NL": "CA-NL",
    "NT": "CA-NT",
    "YT": "CA-YT",
    "NU": "CA-NU",
}


def load_study(path: Path) -> tuple[dict[str, dict], dict[str, str]]:
    """Parse the study CSV.

    Returns:
        study_meta         — {visit_id: {site_code, site_name, lat, lng, year,
                                         julian_day, stream_order, local_basin}}
        visit_jurisdictions — {visit_id: jurisdiction_code} for all Canadian provinces
    """
    study_meta: dict[str, dict] = {}
    visit_jurisdictions: dict[str, str] = {}
    enc = _detect_encoding(path)
    with path.open(newline="", encoding=enc) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            logger.warning("Study CSV %s has no header row", path)
            return study_meta, visit_jurisdictions
        norm = {raw: _normalize_col(raw) for raw in reader.fieldnames}
        for row in reader:
            r = {norm[k]: v.strip() for k, v in row.items() if k}
            visit_id = r.get("SiteVisitID", "").strip()
            if not visit_id:
                continue
            province = r.get("Province", "").strip().upper()
            jur = _PROVINCE_TO_JURISDICTION.get(province)
            if jur:
                visit_jurisdictions[visit_id] = jur
            year = _parse_int(r.get("Year", ""))
            if year is None:
                continue
            study_meta[visit_id] = {
                "site_code": r.get("Site", "").strip() or visit_id,
                "site_name": r.get("SiteName", "").strip() or None,
                "lat": _parse_float(r.get("Latitude", "")),
                "lng": _parse_float(r.get("Longitude", "")),
                "year": year,
                "julian_day": _parse_int(r.get("JulianDay", "")),
                "stream_order": _parse_int(r.get("StreamOrder", "")),
                "local_basin": r.get("LocalBasinName", "").strip() or None,
            }

    by_jur: dict[str, int] = {}
    for jur in visit_jurisdictions.values():
        by_jur[jur] = by_jur.get(jur, 0) + 1
    logger.info(
        "Study file: %d total visits, %d Canadian visits by jurisdiction: %s",
        len(study_meta),
        len(visit_jurisdictions),
        by_jur,
    )
    return study_meta, visit_jurisdictions


def parse_benthic(path: Path, visit_jurisdictions: dict[str, str]) -> dict[str, dict]:
    """Stream the benthic CSV, aggregating taxon counts per visit for all provinces.

    Returns {visit_id: {ept_count, total_count, ept_richness, ept_taxa_seen}}.
    Province is blank in benthic rows — jurisdiction filtering is done via
    visit_jurisdictions (keyed by SiteVisitID from the study file).

    SubSample handling: raw Count values are used for all arithmetic.
    EPT proportion (ept_count / total_count) is invariant to SubSample scaling,
    so no scaling is applied. When SubSample == 0 the Count is used directly,
    which is the same behaviour as the unscaled path.
    """
    agg: dict[str, dict] = {}
    enc = _detect_encoding(path)
    rows_processed = 0
    with path.open(newline="", encoding=enc) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            logger.warning("Benthic CSV %s has no header row", path)
            return agg
        norm = {raw: _normalize_col(raw) for raw in reader.fieldnames}
        for raw_row in reader:
            r = {norm[k]: v.strip() for k, v in raw_row.items() if k}
            visit_id = r.get("SiteVisitID", "").strip()
            if visit_id not in visit_jurisdictions:
                continue
            count_str = r.get("Count", "").strip()
            if not count_str:
                continue
            try:
                count = float(count_str)
            except ValueError:
                continue
            if count <= 0:
                continue

            order = r.get("Order", "").strip()
            family = r.get("Family", "").strip()
            is_ept = _is_ept_taxon(order, family)

            entry = agg.setdefault(
                visit_id,
                {
                    "ept_count": 0.0,
                    "total_count": 0.0,
                    "ept_taxa_seen": set(),
                    "all_taxa_seen": set(),
                },
            )
            taxon_key = family if family else order
            entry["total_count"] += count
            entry["all_taxa_seen"].add(taxon_key)
            if is_ept:
                entry["ept_count"] += count
                entry["ept_taxa_seen"].add(taxon_key)
            rows_processed += 1

    logger.info(
        "Benthic file: %d Canadian rows processed → %d site visits aggregated",
        rows_processed,
        len(agg),
    )
    return agg


def build_samples(
    study_meta: dict[str, dict],
    benthic_agg: dict[str, dict],
    visit_jurisdictions: dict[str, str],
) -> list[BenthicSample]:
    """Join benthic aggregates with study metadata → list[BenthicSample].

    Jurisdiction is derived from visit_jurisdictions (province code from study file).
    """
    records: list[BenthicSample] = []
    for visit_id, counts in benthic_agg.items():
        total = counts["total_count"]
        if total == 0:
            continue
        ept = counts["ept_count"]
        ept_prop = ept / total
        meta = study_meta.get(visit_id, {})
        jur = visit_jurisdictions.get(visit_id, "CA-ON")
        records.append(
            BenthicSample(
                site_visit_id=visit_id,
                site_code=meta.get("site_code", visit_id),
                site_name=meta.get("site_name"),
                lat=meta.get("lat"),
                lng=meta.get("lng"),
                jurisdiction=jur,
                sampled_year=meta.get("year", 0),
                sampled_julian_day=meta.get("julian_day"),
                stream_order=meta.get("stream_order"),
                local_basin=meta.get("local_basin"),
                ept_richness=len(counts["ept_taxa_seen"]),
                ept_count=round(ept, 4),
                total_count=round(total, 4),
                ept_proportion=round(ept_prop, 4),
                total_taxa_richness=len(counts["all_taxa_seen"]),
                habitat_quality=_habitat_quality(ept_prop),
            )
        )

    by_jur: dict[str, int] = {}
    for s in records:
        by_jur[s.jurisdiction] = by_jur.get(s.jurisdiction, 0) + 1
    logger.info("Built %d BenthicSample records by jurisdiction: %s", len(records), by_jur)
    return records
