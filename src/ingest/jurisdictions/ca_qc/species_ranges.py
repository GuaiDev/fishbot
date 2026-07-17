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

The GeoJSON's coordinates are in EPSG:32198 (NAD83 / Quebec Lambert), a
projected metre-based CRS, not WGS84 lon/lat — its "crs" property declares
this. Centroids are reprojected to EPSG:4326 via pyproj before being stored;
skipping this step (an earlier version of this adapter did) produces
centroid values like (390200, -812965) that look superficially like
coordinates but are hundreds/thousands of km off representing anything real.
pyproj ships its own bundled PROJ data in the wheel — no system GDAL/fiona
required, unlike reading the source .gdb directly.

Cache TTL: 365 days.
"""

import json
import logging
import re
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
    """Parse a GeoJSON FeatureCollection into species_ranges rows.

    Real property names, verified against the 2026 release (118 features,
    one polygon/multipolygon per species, no duplicates): NOM_FRANCA (French
    common name), NOM_ANGLA (English common name), NOM_SCIENT (scientific
    name), FAMILLE (family). There is no conservation-status field in this
    file at all (no COSEWIC/SARA column of any name) — sara_status and
    cosewic_status are left None rather than fabricated; an earlier version
    of this parser looked for STATUT_COSSEPAC/COSEWIC_STATUS, which don't
    exist here, so every row's status ended up None anyway, but for the
    wrong reason (silently missing key, not "field doesn't exist").
    """
    import datetime

    now = datetime.datetime.utcnow().isoformat()
    rows: list[dict] = []
    seen: set[str] = set()
    to_wgs84 = _build_transformer(data)

    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}

        common_en = (props.get("NOM_ANGLA") or "").strip()
        common_fr = (props.get("NOM_FRANCA") or "").strip()
        sci = (props.get("NOM_SCIENT") or "").strip()
        family = (props.get("FAMILLE") or "").strip()

        species_key = sci or common_en or common_fr
        if not species_key or species_key in seen:
            continue
        seen.add(species_key)

        clat, clng = _centroid(geom, to_wgs84)

        rows.append(
            {
                "species": common_en or common_fr or sci,
                "scientific_name": sci or None,
                "native_to_ontario": 0,
                "native_to_great_lakes": 0,
                "introduced": 0,
                "extirpated_from_ontario": 0,
                "general_range": (
                    f"Quebec — centroid ({round(clat, 3) if clat is not None else '?'}, "
                    f"{round(clng, 3) if clng is not None else '?'})"
                ),
                "habitat_notes": f"Family: {family}" if family else None,
                "jurisdictions_present": '["CA-QC"]',
                "sara_status": None,
                "ontario_status": None,
                "cosewic_status": None,
                "fishing_notes": None,
                "last_updated": now,
            }
        )

    return rows


def _build_transformer(data: dict):
    """Build a pyproj Transformer from the GeoJSON's declared CRS to WGS84.

    Returns None if the CRS is already WGS84 (or unspecified — the GeoJSON
    spec's default) so callers can skip the transform. Returns None and logs
    a warning if pyproj isn't installed, in which case centroids are left
    in the source projected CRS (wrong units, but callers get a clear signal
    via the warning rather than a silent corruption).
    """
    crs_name = ((data.get("crs") or {}).get("properties") or {}).get("name", "")
    match = re.search(r"(\d{4,5})", crs_name)
    epsg = match.group(1) if match else "4326"
    if epsg == "4326":
        return None

    try:
        from pyproj import Transformer
    except ImportError:
        logger.warning(
            "QC species ranges: pyproj not installed — cannot reproject from EPSG:%s "
            "to WGS84. Install with: uv add pyproj. Centroids will be in the wrong "
            "(projected, metre-based) units.",
            epsg,
        )
        return None

    logger.info("QC species ranges: reprojecting centroids from EPSG:%s to WGS84", epsg)
    return Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)


def _centroid(geom: dict, to_wgs84) -> tuple[float | None, float | None]:
    """Rough (lat, lng) centroid from a Point/Polygon/MultiPolygon geometry,
    sampling up to 100 points of the outer ring, reprojected to WGS84 via
    `to_wgs84` if the source CRS isn't already WGS84 (see _build_transformer).

    MultiPolygon coordinates are nested one level deeper than Polygon
    (list-of-polygons, each a list-of-rings) — indexing straight into
    coordinates[0] the same way as Polygon silently picks a ring's worth of
    coordinate pairs as if they were points, corrupting the centroid. This
    takes coordinates[0][0] for MultiPolygon specifically.
    """
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None, None

    if gtype == "Point":
        if len(coords) >= 2:
            x, y = coords[0], coords[1]
        else:
            return None, None
        ring = None
    elif gtype == "Polygon":
        ring = coords[0] if coords else None
        x = y = None
    elif gtype == "MultiPolygon":
        ring = coords[0][0] if coords and coords[0] else None
        x = y = None
    else:
        return None, None

    if ring is not None:
        if not ring:
            return None, None
        pts = ring[:100]
        x = sum(p[0] for p in pts) / len(pts)
        y = sum(p[1] for p in pts) / len(pts)

    if x is None or y is None:
        return None, None

    if to_wgs84 is not None:
        x, y = to_wgs84.transform(x, y)
    return y, x
