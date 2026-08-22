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

# Confirmed by walking the LIO service directory (scripts/find_fmz_layer.py):
# 'Fisheries Management Zone' is layer 14 of LIO_Open07. The first attempt
# pointed at LIO_Open06 — reused from the crown-land adapter without checking —
# which holds Greenbelt and land-use planning layers. The layer id is still
# resolved at runtime rather than hardcoded, so an upstream renumbering within
# this service surfaces as a loud discovery failure instead of silent zero rows.
_SERVICE_ROOT = (
    "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest"
    "/services/LIO_OPEN_DATA/LIO_Open07/MapServer"
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
        payload = _query_layer(layer_id)
        if payload is None:
            return []
        cache.write_text(json.dumps(payload), encoding="utf-8")

    return _parse_features(payload)


def _query_layer(layer_id: int) -> dict | None:
    """Query the layer, trying Esri JSON first.

    MapServer endpoints of this vintage do not all support f=geojson; the one
    here answers HTTP 200 with an HTML error page, which surfaced as an opaque
    JSONDecodeError. Esri JSON (f=json) is universally supported, so it is
    tried first and GeoJSON kept as a fallback.

    `maxAllowableOffset` asks the server to generalise the geometry before
    sending it. Zone edges do not need metre precision for a containment test,
    and full-resolution provincial polygons are a very large download.
    """
    url = f"{_SERVICE_ROOT}/{layer_id}/query"
    base = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": str(_SIMPLIFY_TOLERANCE),
    }

    for fmt in ("json", "geojson"):
        r = httpx.get(
            url, params={**base, "f": fmt}, timeout=300,
            headers={"User-Agent": _USER_AGENT},
        )
        r.raise_for_status()
        try:
            payload = r.json()
        except ValueError:
            head = " ".join(r.text[:200].split())
            logger.warning("FMZ query with f=%s returned non-JSON: %s", fmt, head)
            continue

        if isinstance(payload, dict) and payload.get("error"):
            logger.warning("FMZ query with f=%s returned an error: %s", fmt, payload["error"])
            continue
        if payload.get("features"):
            if payload.get("exceededTransferLimit"):
                logger.warning(
                    "FMZ query hit the server transfer limit — some zones may be missing"
                )
            logger.info("FMZ layer returned %d features via f=%s",
                        len(payload["features"]), fmt)
            return payload
        logger.warning("FMZ query with f=%s returned no features", fmt)

    logger.error(
        "FMZ layer %s returned nothing usable in either Esri JSON or GeoJSON", layer_id
    )
    return None


def _esri_rings_to_geometry(rings: list):
    """Build a shapely geometry from Esri JSON rings.

    Esri encodes exterior rings clockwise and holes counter-clockwise, using
    signed area. GeoJSON has no such convention, which is why the two formats
    need separate handling rather than one loose parser.
    """
    from shapely.geometry import MultiPolygon, Polygon

    shells, holes = [], []
    for ring in rings:
        if len(ring) < 4:
            continue
        # Shoelace: negative area == clockwise == exterior in Esri JSON.
        area = sum(
            (ring[i][0] * ring[i + 1][1]) - (ring[i + 1][0] * ring[i][1])
            for i in range(len(ring) - 1)
        )
        (shells if area < 0 else holes).append(ring)

    if not shells:
        # Some publishers ignore the winding convention entirely.
        shells, holes = rings, []

    polys = []
    for shell in shells:
        inner = [
            h for h in holes if Polygon(shell).contains(Polygon(h).representative_point())
        ]
        polys.append(Polygon(shell, inner))
    return polys[0] if len(polys) == 1 else MultiPolygon(polys)


def _parse_features(payload: dict) -> list[dict]:
    """Turn an Esri JSON or GeoJSON feature collection into storage rows."""
    rows: list[dict] = []
    for feat in payload.get("features", []):
        # Esri JSON uses "attributes"; GeoJSON uses "properties".
        raw_props = feat.get("properties") or feat.get("attributes") or {}
        props = {k.lower(): v for k, v in raw_props.items()}
        zone = _zone_number(props)
        geom = feat.get("geometry")
        if zone is None or not geom:
            continue
        try:
            poly = (
                _esri_rings_to_geometry(geom["rings"])
                if isinstance(geom, dict) and "rings" in geom
                else shape(geom)
            )
            if not poly.is_valid:
                poly = poly.buffer(0)
            simple = poly.simplify(_SIMPLIFY_TOLERANCE, preserve_topology=True)
        except Exception:  # noqa: BLE001
            logger.warning("FMZ %s: unusable geometry, skipped", zone)
            continue

        minx, miny, maxx, maxy = simple.bounds
        rows.append({
            "zone": zone,
            "zone_name": (
                props.get("fmz_name")
                or props.get("name")
                or props.get("location_descr")
                or f"FMZ {zone}"
            ),
            "jurisdiction": "CA-ON",
            "geom_wkt": wkt_dumps(simple, rounding_precision=6),
            "bbox_minx": minx, "bbox_miny": miny,
            "bbox_maxx": maxx, "bbox_maxy": maxy,
        })
    return rows


# Known field name first, then a structural fallback. LIO calls it
# FISHERIES_MANAGEMENT_ZONE_ID — none of the short names guessed initially
# ("fmz", "zone", "fmz_id"…) matched, so every feature parsed to None and the
# layer looked empty despite fetching 20 polygons correctly. Matching on shape
# rather than an exact label is the same lesson as the PWQMN discovery bug.
_ZONE_FIELD_EXACT = "fisheries_management_zone_id"


def _zone_number(props: dict) -> int | None:
    """Pull the zone number out of whatever the layer calls that field.

    Tries the documented field, then any field whose name mentions a zone and
    whose value is a plausible FMZ number. The 1-20 range check keeps
    identifiers like OGF_ID (211300004) and OBJECTID (1281) out.
    """
    ordered = [_ZONE_FIELD_EXACT, "fmz", "fmz_id", "zone", "zone_id", "fmz_number"]
    ordered += sorted(
        k for k in props
        if k not in ordered and ("zone" in k or "fmz" in k)
    )
    for key in ordered:
        v = props.get(key)
        if v is None:
            continue
        try:
            n = int(str(v).strip())
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 20:
            return n
    return None
