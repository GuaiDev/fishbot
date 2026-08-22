"""Ontario Fisheries Management Zone boundaries — ESRI REST ingest.

Replaces a hand-drawn table of overlapping lat/lng rectangles that resolved
zones by first match. That approach could not be made correct: the boxes
overlapped, so the answer depended on list order, and several were mislabelled
outright — the box commented "GTA lake shore" returned zone 5 (Rainy River,
1,500 km away) and the box numbered 20 covered James Bay when FMZ 20 is Lake
Ontario. Regulations are legally consequential; a confident wrong zone is worse
than no answer.

Real polygons, point-in-polygon lookup. Cache TTL 90 days — zone boundaries
change on the order of years.
"""

import json
import logging
import time
from pathlib import Path

import httpx
from shapely.geometry import shape
from shapely.wkt import dumps as wkt_dumps

_REST_URL = (
    "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest"
    "/services/LIO_OPEN_DATA/LIO_Open06/MapServer/query"
)
# The FMZ layer is published on Ontario GeoHub. The layer id is resolved at
# runtime from the service directory rather than hardcoded, so a renumbering
# upstream surfaces as a loud discovery failure instead of silent zero rows.
_SERVICE_ROOT = (
    "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest"
    "/services/LIO_OPEN_DATA/LIO_Open06/MapServer"
)
_LAYER_NAME_HINTS = ("fisheries management zone", "fmz")

_CACHE_DIR = Path("data/cache/fmz")
_CACHE_TTL_SECONDS = 90 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"
_SIMPLIFY_TOLERANCE = 0.002  # ~200m; zone edges do not need metre precision

logger = logging.getLogger(__name__)


def _discover_layer_id() -> int | None:
    """Find the FMZ layer id in the service directory."""
    from src.ingest.discovery import check_resource_discovery

    r = httpx.get(f"{_SERVICE_ROOT}?f=json", timeout=60, headers={"User-Agent": _USER_AGENT})
    r.raise_for_status()
    layers = r.json().get("layers", [])
    matches = [
        lyr for lyr in layers
        if any(h in str(lyr.get("name", "")).lower() for h in _LAYER_NAME_HINTS)
    ]
    check_resource_discovery(
        source="Ontario FMZ boundaries",
        matched=len(matches),
        candidates=[str(lyr.get("name", "")) for lyr in layers],
        matcher=f"layer name containing one of {_LAYER_NAME_HINTS}",
    )
    return int(matches[0]["id"]) if matches else None


def fetch_fmz_boundaries() -> list[dict]:
    """Download every FMZ polygon. Returns rows ready for storage."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _CACHE_DIR / "fmz_boundaries.json"

    if cache.exists() and time.time() - cache.stat().st_mtime < _CACHE_TTL_SECONDS:
        logger.info("FMZ boundary cache is fresh, using it")
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        layer_id = _discover_layer_id()
        if layer_id is None:
            logger.error("FMZ layer not found in the service directory")
            return []
        url = f"{_SERVICE_ROOT}/{layer_id}/query"
        r = httpx.get(
            url,
            params={
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
            },
            timeout=180,
            headers={"User-Agent": _USER_AGENT},
        )
        r.raise_for_status()
        payload = r.json()
        cache.write_text(json.dumps(payload), encoding="utf-8")

    return _parse_features(payload)


def _parse_features(payload: dict) -> list[dict]:
    """Turn a GeoJSON FeatureCollection into storage rows."""
    rows: list[dict] = []
    for feat in payload.get("features", []):
        props = {k.lower(): v for k, v in (feat.get("properties") or {}).items()}
        zone = _zone_number(props)
        geom = feat.get("geometry")
        if zone is None or not geom:
            continue
        try:
            poly = shape(geom)
            if not poly.is_valid:
                poly = poly.buffer(0)
            simple = poly.simplify(_SIMPLIFY_TOLERANCE, preserve_topology=True)
        except Exception:  # noqa: BLE001
            logger.warning("FMZ %s: unusable geometry, skipped", zone)
            continue

        minx, miny, maxx, maxy = simple.bounds
        rows.append({
            "zone": zone,
            "zone_name": props.get("fmz_name") or props.get("name") or f"FMZ {zone}",
            "jurisdiction": "CA-ON",
            "geom_wkt": wkt_dumps(simple, rounding_precision=6),
            "bbox_minx": minx, "bbox_miny": miny,
            "bbox_maxx": maxx, "bbox_maxy": maxy,
        })
    return rows


def _zone_number(props: dict) -> int | None:
    """Pull the zone number out of whatever the layer calls that field."""
    for key in ("fmz", "fmz_id", "zone", "zone_id", "fmz_number", "objectid_1"):
        v = props.get(key)
        if v is None:
            continue
        try:
            n = int(str(v).strip())
        except ValueError:
            continue
        if 1 <= n <= 20:
            return n
    return None
