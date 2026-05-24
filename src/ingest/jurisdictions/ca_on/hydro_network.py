"""Ontario Hydro Network (OHN) ingestion — watercourse segments and barriers.

Source: LIO Open Data MapServer (LIO_Open01)
  Layer 26: OHN Watercourse (stream segments with flow direction)
  Layer 6:  OHN Hydrographic Point (Falls, Rapids, Rocks, Sea Lamprey Barrier)

Fetch is scoped to a bounding box derived from lat/lon/radius_km. The full
province has millions of segments; the Toronto 50km bbox has ~36,000 — manageable
in ~8 pages at 5,000 records per page.

Cache TTL: 30 days. Each paginated request cached separately by URL + params hash.
Geometry stored as WKT using Shapely. No SpatiaLite dependency required.
"""

import hashlib
import json
import logging
import math
import time
from pathlib import Path

import httpx
from shapely.geometry import LineString, Point

from src.models.hydrology import HydroBarrier, StreamSegment

_SERVICE_BASE = (
    "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services"
    "/LIO_OPEN_DATA/LIO_Open01/MapServer"
)
_WATERCOURSE_LAYER = 26
_HYDRO_POINT_LAYER = 6
_PAGE_SIZE = 5000
_CACHE_DIR = Path("data/cache/ohn")
_CACHE_TTL_SECONDS = 2_592_000  # 30 days
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"
# Barriers more than this far from any segment are discarded (degrees; ~200m at 43°N)
_MAX_SNAP_DIST_DEG = 0.002

logger = logging.getLogger(__name__)


def fetch_watercourses(lat: float, lon: float, radius_km: float = 50.0) -> list[StreamSegment]:
    """Fetch OHN watercourse segments within radius_km of lat/lon. Cached 30 days."""
    min_lon, min_lat, max_lon, max_lat = _bbox(lat, lon, radius_km)
    bbox_str = f"{min_lon:.5f},{min_lat:.5f},{max_lon:.5f},{max_lat:.5f}"

    segments: list[StreamSegment] = []
    offset = 0

    while True:
        params = {
            "geometry": bbox_str,
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": (
                "OGF_ID,WATERCOURSE_TYPE,OFFICIAL_NAME_LABEL,"
                "FLOW_DIRECTION_VERIFIED_IND,PERMANENCY,"
                "FLOW_CLASSIFICATION,SYSTEM_CALCULATED_LENGTH"
            ),
            "returnGeometry": "true",
            "outSR": "4326",
            "resultOffset": offset,
            "resultRecordCount": _PAGE_SIZE,
            "f": "json",
        }
        url = f"{_SERVICE_BASE}/{_WATERCOURSE_LAYER}/query"
        data = _cached_get(url, params)

        features = data.get("features", [])
        logger.debug("OHN watercourse page offset=%d: %d features", offset, len(features))

        for feat in features:
            seg = _parse_segment(feat)
            if seg is not None:
                segments.append(seg)

        # This MapServer returns variable page sizes and does not reliably set
        # exceededTransferLimit. Stop only when the server returns 0 features.
        if not features:
            break
        offset += _PAGE_SIZE

    logger.info("OHN watercourse fetch complete: %d segments", len(segments))
    return segments


def fetch_barriers(
    lat: float,
    lon: float,
    radius_km: float = 50.0,
    segments: list[StreamSegment] | None = None,
) -> list[HydroBarrier]:
    """Fetch OHN hydrographic barrier points within radius_km of lat/lon.

    If segments is provided, each barrier is snapped to its nearest segment
    (within _MAX_SNAP_DIST_DEG). Barriers that can't be snapped are still
    included with nearest_segment_ogf_id=None.
    """
    min_lon, min_lat, max_lon, max_lat = _bbox(lat, lon, radius_km)
    bbox_str = f"{min_lon:.5f},{min_lat:.5f},{max_lon:.5f},{max_lat:.5f}"

    params = {
        "geometry": bbox_str,
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OGF_ID,HYDROGRAPHIC_POINT_TYPE",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }
    url = f"{_SERVICE_BASE}/{_HYDRO_POINT_LAYER}/query"
    data = _cached_get(url, params)

    barriers: list[HydroBarrier] = []
    for feat in data.get("features", []):
        barrier = _parse_barrier(feat, segments)
        if barrier is not None:
            barriers.append(barrier)

    logger.info("OHN barrier fetch complete: %d points", len(barriers))
    return barriers


# ── internal parsers ──────────────────────────────────────────────────────────

def _parse_segment(feat: dict) -> StreamSegment | None:
    attrs = feat.get("attributes", {})
    geom = feat.get("geometry", {})
    paths = geom.get("paths", [])

    if not paths or not paths[0] or len(paths[0]) < 2:
        return None

    coords = paths[0]
    try:
        line = LineString(coords)
    except Exception:
        return None

    start = coords[0]
    end = coords[-1]

    try:
        return StreamSegment(
            ogf_id=int(attrs["OGF_ID"]),
            watercourse_type=attrs.get("WATERCOURSE_TYPE") or "Stream",
            name=attrs.get("OFFICIAL_NAME_LABEL") or None,
            flow_verified=attrs.get("FLOW_DIRECTION_VERIFIED_IND") == "Yes",
            permanency=attrs.get("PERMANENCY") or "Permanent",
            flow_classification=attrs.get("FLOW_CLASSIFICATION") or None,
            length_m=float(attrs.get("SYSTEM_CALCULATED_LENGTH") or 0.0),
            geom_wkt=line.wkt,
            start_node=f"{round(start[0], 5)},{round(start[1], 5)}",
            end_node=f"{round(end[0], 5)},{round(end[1], 5)}",
            jurisdiction="CA-ON",
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Skipping segment OGF_ID=%s: %s", attrs.get("OGF_ID"), exc)
        return None


def _parse_barrier(
    feat: dict,
    segments: list[StreamSegment] | None,
) -> HydroBarrier | None:
    attrs = feat.get("attributes", {})
    geom = feat.get("geometry", {})

    barrier_type = attrs.get("HYDROGRAPHIC_POINT_TYPE")
    if not barrier_type:
        return None

    lon = geom.get("x")
    lat = geom.get("y")
    if lon is None or lat is None:
        return None

    point = Point(lon, lat)
    nearest_ogf_id, snap_dist_m = _snap_to_nearest_segment(point, segments)

    try:
        return HydroBarrier(
            ogf_id=int(attrs["OGF_ID"]),
            barrier_type=barrier_type,
            geom_wkt=point.wkt,
            nearest_segment_ogf_id=nearest_ogf_id,
            snap_distance_m=snap_dist_m,
            jurisdiction="CA-ON",
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Skipping barrier OGF_ID=%s: %s", attrs.get("OGF_ID"), exc)
        return None


def _snap_to_nearest_segment(
    point: Point,
    segments: list[StreamSegment] | None,
) -> tuple[int | None, float | None]:
    """Return (ogf_id, distance_m) of nearest segment, or (None, None) if too far."""
    if not segments:
        return None, None

    from shapely.wkt import loads as wkt_loads

    min_dist = float("inf")
    nearest_ogf_id: int | None = None

    for seg in segments:
        try:
            line = wkt_loads(seg.geom_wkt)
        except Exception:
            continue
        dist = point.distance(line)
        if dist < min_dist:
            min_dist = dist
            nearest_ogf_id = seg.ogf_id

    if min_dist > _MAX_SNAP_DIST_DEG:
        return None, None

    # Rough degrees-to-metres at ~43°N: 1° lat ≈ 111,000m; use lat scale
    snap_dist_m = round(min_dist * 111_000, 1)
    return nearest_ogf_id, snap_dist_m


# ── HTTP + cache ──────────────────────────────────────────────────────────────

def _cached_get(url: str, params: dict) -> dict:
    """GET with 30-day file cache keyed by URL + sorted params."""
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
    cache_file.write_text(json.dumps(data))
    return data


# ── geometry helpers ──────────────────────────────────────────────────────────

def _bbox(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return (min_lon, min_lat, max_lon, max_lat) bounding box for a circle."""
    lat_deg = radius_km / 111.0
    lon_deg = radius_km / (111.320 * math.cos(math.radians(lat)))
    return (lon - lon_deg, lat - lat_deg, lon + lon_deg, lat + lat_deg)
