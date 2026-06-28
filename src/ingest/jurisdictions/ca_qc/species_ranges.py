"""Quebec freshwater fish species ranges — MELCCFP GeoJSON.

Downloads species distribution GeoJSON from the Données Québec open data
portal (Ministère de l'Environnement, de la Lutte contre les changements
climatiques, de la Faune et des Parcs — MELCCFP).

Source:
  Dataset: "Aires de répartition — faune"
  Portal:  https://www.donneesquebec.ca/recherche/dataset/aires-de-repartition-faune
  GeoJSON: individual files per species group; freshwater fish file discovered
           from the package API.

Table: species_ranges (shared schema — source='MELCCFP')
  Note: jurisdiction_present for all records is 'CA-QC'. The native_to_ontario
  flag is set 0 for all QC-source records (override with ON data if needed).

Cache TTL: 365 days.
"""

import json
import logging
import time
from pathlib import Path

import httpx

_PACKAGE_URL = "https://www.donneesquebec.ca/recherche/api/3/action/package_show"
_PACKAGE_ID = "aires-de-repartition-faune"
_CACHE_DIR = Path("data/cache/qc_species_ranges")
_CACHE_TTL_SECONDS = 365 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

# Keywords to identify freshwater fish resource within the package
_FISH_KEYWORDS = frozenset({"poisson", "fish", "ichty", "freshwater"})

logger = logging.getLogger(__name__)


def fetch_species_ranges() -> list[dict]:
    """Download and parse QC freshwater fish range GeoJSON.

    Returns list of row dicts for species_ranges table.
    """
    geojson_url = _find_fish_geojson_url()
    if not geojson_url:
        logger.warning(
            "QC species ranges: could not find freshwater fish GeoJSON in MELCCFP package. "
            "Check https://www.donneesquebec.ca/recherche/dataset/aires-de-repartition-faune "
            "for the current resource URL and update _find_fish_geojson_url()."
        )
        return []

    data = _download_geojson(geojson_url)
    if not data:
        return []

    rows = _parse_geojson(data)
    logger.info("QC species ranges: %d species range records extracted", len(rows))
    return rows


def _find_fish_geojson_url() -> str | None:
    """Query Données Québec CKAN API to find the freshwater fish GeoJSON URL."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / "package_meta.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            pkg = json.loads(cache_file.read_text())
        else:
            pkg = None
    else:
        pkg = None

    if pkg is None:
        try:
            resp = httpx.get(
                _PACKAGE_URL,
                params={"id": _PACKAGE_ID},
                headers={"User-Agent": _USER_AGENT},
                timeout=30,
            )
            resp.raise_for_status()
            pkg = resp.json().get("result", {})
            cache_file.write_text(json.dumps(pkg))
        except Exception as exc:
            logger.error("QC species ranges: CKAN package fetch failed: %s", exc)
            return None

    for resource in pkg.get("resources", []):
        name_lower = (resource.get("name") or "").lower()
        fmt = (resource.get("format") or "").lower()
        is_geojson = fmt in ("geojson", "json")
        has_fish_kw = any(kw in name_lower for kw in _FISH_KEYWORDS)
        if is_geojson and has_fish_kw:
            url = resource.get("url") or ""
            if url:
                logger.info("QC species ranges: found GeoJSON resource: %s", url)
                return url

    return None


def _download_geojson(url: str) -> dict | None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    import hashlib
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    cache_file = _CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            return json.loads(cache_file.read_text())

    try:
        resp = httpx.get(
            url,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        cache_file.write_text(json.dumps(data))
        return data
    except Exception as exc:
        logger.error("QC species ranges: GeoJSON download failed from %s: %s", url, exc)
        return None


def _parse_geojson(data: dict) -> list[dict]:
    """Parse a GeoJSON FeatureCollection into species_ranges rows."""
    import datetime

    now = datetime.datetime.utcnow().isoformat()
    rows: list[dict] = []
    seen: set[str] = set()

    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}

        # Field names vary by MELCCFP release — try common variants
        common = (
            props.get("NOM_COMMUN_FR") or props.get("NOM_COMMUN") or
            props.get("NomCommun") or props.get("common_name") or ""
        ).strip()
        sci = (
            props.get("NOM_SCIENTIFIQUE") or props.get("NomScientifique") or
            props.get("scientific_name") or ""
        ).strip()
        sara = (
            props.get("STATUT_COSSEPAC") or props.get("COSEWIC_STATUS") or
            props.get("statut_cossepac") or ""
        ).strip()

        species_key = sci or common
        if not species_key or species_key in seen:
            continue
        seen.add(species_key)

        # Centroid from geometry
        clat = clng = None
        if geom.get("type") == "Point":
            coords = geom.get("coordinates", [])
            if len(coords) >= 2:
                clng, clat = coords[0], coords[1]
        elif geom.get("type") in ("Polygon", "MultiPolygon"):
            # Rough centroid from first ring
            rings = geom.get("coordinates", [[]])
            pts = rings[0] if isinstance(rings[0][0], list) else rings
            if pts:
                xs = [p[0] for p in pts[:100]]
                ys = [p[1] for p in pts[:100]]
                clng = sum(xs) / len(xs)
                clat = sum(ys) / len(ys)

        rows.append({
            "species": common or sci,
            "scientific_name": sci or None,
            "native_to_ontario": 0,
            "native_to_great_lakes": 0,
            "introduced": 0,
            "extirpated_from_ontario": 0,
            "general_range": (
                f"Quebec — centroid ({round(clat, 3) if clat else '?'}, "
                f"{round(clng, 3) if clng else '?'})"
            ),
            "habitat_notes": None,
            "jurisdictions_present": '["CA-QC"]',
            "sara_status": sara or None,
            "ontario_status": None,
            "cosewic_status": sara or None,
            "fishing_notes": None,
            "last_updated": now,
        })

    return rows
