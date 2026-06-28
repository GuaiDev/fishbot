"""DFO Species at Risk — Critical Habitat (national).

Fetches DFO SAR critical habitat polygons from the ESRI REST MapServer
and stores freshwater fish entries in the species_ranges table.

Source:
  https://egisp.dfo-mpo.gc.ca/arcgis/rest/services/open_data_donnees_ouvertes/
  CritHab_HabEss_2025/MapServer/0

Pagination: geometry bbox filter + resultOffset, same pattern as OHN hydro_network.py.
No fiona / GDAL required.

Table: species_ranges (shared schema — source='DFO_SAR')

Cache TTL: 30 days.
"""

import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from src.jurisdictions.geo import jurisdiction_for_coords

_SERVICE_URL = (
    "https://egisp.dfo-mpo.gc.ca/arcgis/rest/services/"
    "open_data_donnees_ouvertes/CritHab_HabEss_2025/MapServer/0/query"
)
_PAGE_SIZE = 1000
_CACHE_DIR = Path("data/cache/dfo_sar_range")
_CACHE_TTL_SECONDS = 30 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

# Canada bounding box (WGS84)
_CANADA_BBOX = (-141.0, 42.0, -52.0, 84.0)

# Sub-tile size in degrees. ~5° ≈ 350–550 km; keeps per-tile counts well under PAGE_SIZE.
_TILE_DEG = 5.0

logger = logging.getLogger(__name__)


def fetch_sar_ranges() -> list[dict]:
    """Fetch DFO SAR critical habitat via ESRI REST. Returns rows for species_ranges table."""
    base_params = {
        "where": "1=1",
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": _PAGE_SIZE,
        "f": "json",
    }

    min_lon, min_lat, max_lon, max_lat = _CANADA_BBOX
    tiles = _grid_tiles(min_lon, min_lat, max_lon, max_lat)
    logger.info("DFO SAR range: fetching %d tiles across Canada bbox", len(tiles))

    seen: dict[str, dict] = {}
    for t_bbox in tiles:
        for feat in _fetch_tile(base_params, *t_bbox):
            attrs = feat.get("attributes") or {}
            key = _feature_key(attrs)
            if key and key not in seen:
                seen[key] = feat

    logger.info("DFO SAR range: %d unique features fetched", len(seen))

    rows: list[dict] = []
    for feat in seen.values():
        row = _parse_feature(feat)
        if row:
            rows.append(row)

    logger.info("DFO SAR range: %d records extracted", len(rows))
    return rows


def _parse_feature(feat: dict) -> dict | None:
    attrs = feat.get("attributes") or {}
    geom = feat.get("geometry") or {}

    common = (
        attrs.get("COMMON_NAME_E") or attrs.get("COMMON_NAME_EN") or
        attrs.get("COMMON_NAME") or ""
    ).strip()
    sci = (
        attrs.get("SCIENTIFIC_NAME") or attrs.get("SCIENTIFICNAME") or ""
    ).strip()
    if not sci and not common:
        return None

    sara_status = (
        attrs.get("SARA_SCHEDULE_E") or attrs.get("SARA_STATUS_E") or
        attrs.get("SCHEDULE") or ""
    ).strip()

    clat, clng = _centroid_from_geometry(geom)
    jur = "CA"
    if clat is not None and clng is not None:
        jur = jurisdiction_for_coords(clat, clng) or "CA"

    return {
        "species": common or sci,
        "scientific_name": sci or None,
        "native_to_ontario": 1 if jur == "CA-ON" else 0,
        "native_to_great_lakes": 0,
        "introduced": 0,
        "extirpated_from_ontario": 0,
        "general_range": f"DFO SAR critical habitat — {jur}",
        "habitat_notes": "critical habitat",
        "jurisdictions_present": f'["{jur}"]',
        "sara_status": sara_status or None,
        "ontario_status": None,
        "cosewic_status": None,
        "fishing_notes": None,
        "last_updated": "2025-01-01T00:00:00",
    }


def _centroid_from_geometry(geom: dict) -> tuple[float | None, float | None]:
    """Return (lat, lng) centroid from an ESRI JSON geometry, or (None, None)."""
    if not geom:
        return None, None

    # Point
    if "x" in geom and "y" in geom:
        try:
            return float(geom["y"]), float(geom["x"])
        except (TypeError, ValueError):
            return None, None

    # Polygon / Multipolygon — use first ring
    rings = geom.get("rings", [])
    if rings and rings[0]:
        pts = rings[0][:100]
        try:
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            return sum(ys) / len(ys), sum(xs) / len(xs)
        except (TypeError, ValueError, ZeroDivisionError):
            return None, None

    return None, None


def _feature_key(attrs: dict) -> str | None:
    sci = (attrs.get("SCIENTIFIC_NAME") or attrs.get("SCIENTIFICNAME") or "").strip()
    obj_id = attrs.get("OBJECTID") or attrs.get("FID")
    if obj_id is not None:
        return f"{sci}_{obj_id}"
    return sci or None


# ── tiling + pagination ────────────────────────────────────────────────────────


def _grid_tiles(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> list[tuple[float, float, float, float]]:
    tiles: list[tuple[float, float, float, float]] = []
    lat = min_lat
    while lat < max_lat:
        t_max_lat = min(lat + _TILE_DEG, max_lat)
        lon = min_lon
        while lon < max_lon:
            t_max_lon = min(lon + _TILE_DEG, max_lon)
            tiles.append((lon, lat, t_max_lon, t_max_lat))
            lon = t_max_lon
        lat = t_max_lat
    return tiles


def _fetch_tile(
    base_params: dict,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> list[dict]:
    """Paginate a single bbox tile with resultOffset."""
    bbox_str = f"{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"
    features: list[dict] = []
    offset = 0

    while True:
        params = {**base_params, "geometry": bbox_str, "resultOffset": offset}
        try:
            data = _cached_get(_SERVICE_URL, params)
        except Exception as exc:
            logger.warning("DFO SAR range: tile fetch failed at offset %d: %s", offset, exc)
            break

        page = data.get("features", [])
        features.extend(page)

        if not page or len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    return features


# ── HTTP + file cache ──────────────────────────────────────────────────────────


def _cached_get(url: str, params: dict) -> dict:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw_key = url + str(sorted(params.items()))
    key = hashlib.sha256(raw_key.encode()).hexdigest()[:16]
    cache_file = _CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            return json.loads(cache_file.read_text())

    response = httpx.get(
        url,
        params=params,
        headers={"User-Agent": _USER_AGENT},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"ESRI error: {data['error']}")
    cache_file.write_text(json.dumps(data))
    return data
