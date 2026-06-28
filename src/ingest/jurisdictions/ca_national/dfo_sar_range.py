"""DFO Species at Risk — Distribution/Range (national).

Downloads the DFO SAR species range GDB zip from the DFO EDH catalogue and
extracts freshwater fish range polygons for all Canadian provinces.

Source:
  https://api-proxy.edh-cde.dfo-mpo.gc.ca/catalogue/records/
  e0fabad5-9379-4077-87b9-5705f28c490b/attachments/Distribution_SAR_EN_2026.gdb.zip

Requirements:
  fiona >= 1.9 (requires GDAL).
  Install with: uv add fiona
  Without fiona this module returns 0 records with a clear warning.

Table: species_ranges (same schema as Ontario's ranges, source='DFO_SAR_RANGE')

Cache TTL: 365 days (annual GDB release).
"""

import logging
import time
import zipfile
from io import BytesIO
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_GDB_URL = (
    "https://api-proxy.edh-cde.dfo-mpo.gc.ca/catalogue/records/"
    "e0fabad5-9379-4077-87b9-5705f28c490b/attachments/Distribution_SAR_EN_2026.gdb.zip"
)
_GDB_ZIP_PATH = Path("data/raw/dfo_sar_range.gdb.zip")
_GDB_PATH = Path("data/raw/dfo_sar_range.gdb")
_CACHE_TTL_SECONDS = 365 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

# Province name → ISO 3166-2 jurisdiction code
_PROVINCE_TO_CODE: dict[str, str] = {
    "ontario": "CA-ON",
    "british columbia": "CA-BC",
    "alberta": "CA-AB",
    "quebec": "CA-QC",
    "québec": "CA-QC",
    "manitoba": "CA-MB",
    "saskatchewan": "CA-SK",
    "nova scotia": "CA-NS",
    "new brunswick": "CA-NB",
    "prince edward island": "CA-PE",
    "newfoundland": "CA-NL",
    "northwest territories": "CA-NT",
    "yukon": "CA-YT",
    "nunavut": "CA-NU",
}

# Taxonomic groups that include freshwater fish
_FRESHWATER_GROUPS = frozenset({
    "Fish",
    "Fishes",
    "Freshwater fish",
    "Poissons d'eau douce",
})


def fetch_sar_ranges() -> list[dict]:
    """Download and parse DFO SAR range GDB. Returns rows for species_ranges table.

    Returns empty list if fiona is not installed or the download fails.
    """
    try:
        import fiona  # type: ignore
    except ImportError:
        logger.warning(
            "DFO SAR range: fiona not installed — cannot parse GDB files. "
            "Install with: uv add fiona  (requires GDAL). Returning 0 records."
        )
        return []

    _download_gdb_if_stale()
    if not _GDB_PATH.exists():
        logger.error("DFO SAR range: GDB directory not found at %s", _GDB_PATH)
        return []

    rows: list[dict] = []
    try:
        layers = fiona.listlayers(str(_GDB_PATH))
        logger.info("DFO SAR range: GDB layers: %s", layers)

        for layer in layers:
            with fiona.open(str(_GDB_PATH), layer=layer) as src:
                for feat in src:
                    props = dict(feat.get("properties") or {})
                    taxon_group = (
                        props.get("TAXON_GROUP_EN") or props.get("TAXONOMIC_GROUP") or ""
                    ).strip()
                    if taxon_group.lower() not in {g.lower() for g in _FRESHWATER_GROUPS}:
                        continue

                    species_sci = (
                        props.get("SCIENTIFIC_NAME") or props.get("NomScientifique") or ""
                    ).strip()
                    common_name = (
                        props.get("COMMON_NAME_EN") or props.get("COMMON_NAME") or ""
                    ).strip()
                    sara_status = (
                        props.get("SARA_STATUS_EN") or props.get("STATUS_EN") or ""
                    ).strip()

                    # Determine jurisdiction from province field or geometry
                    province_raw = (props.get("PROVINCE_EN") or "").strip().lower()
                    jur = _PROVINCE_TO_CODE.get(province_raw, "CA")

                    if not species_sci:
                        continue

                    rows.append({
                        "species": common_name or species_sci,
                        "scientific_name": species_sci,
                        "native_to_ontario": 1 if jur == "CA-ON" else 0,
                        "native_to_great_lakes": 0,
                        "introduced": 0,
                        "extirpated_from_ontario": 0,
                        "general_range": f"DFO SAR range: {province_raw}",
                        "habitat_notes": taxon_group or None,
                        "jurisdictions_present": f'["{jur}"]',
                        "sara_status": sara_status or None,
                        "ontario_status": None,
                        "cosewic_status": None,
                        "fishing_notes": None,
                        "last_updated": "2026-01-01T00:00:00",
                    })

    except Exception as exc:
        logger.error("DFO SAR range: GDB parse failed: %s", exc)
        return []

    logger.info("DFO SAR range: %d freshwater fish range records extracted", len(rows))
    return rows


def _download_gdb_if_stale() -> None:
    """Download the GDB zip and extract it unless cached."""
    _GDB_ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)

    if _GDB_PATH.exists():
        age = time.time() - _GDB_PATH.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            logger.info("DFO SAR range: GDB cache fresh, skipping download")
            return

    logger.info("DFO SAR range: downloading GDB zip from DFO EDH …")
    try:
        response = httpx.get(
            _GDB_URL,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            timeout=300,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.error("DFO SAR range: download failed: %s", exc)
        return

    _GDB_ZIP_PATH.write_bytes(response.content)
    logger.info("DFO SAR range: downloaded %.1f MB", len(response.content) / 1_048_576)

    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        gdb_names = [n for n in zf.namelist() if ".gdb/" in n or n.endswith(".gdb")]
        if gdb_names:
            zf.extractall(_GDB_ZIP_PATH.parent)
            logger.info("DFO SAR range: extracted GDB to %s", _GDB_ZIP_PATH.parent)
        else:
            logger.error("DFO SAR range: no .gdb found in zip — contents: %s", zf.namelist()[:10])
