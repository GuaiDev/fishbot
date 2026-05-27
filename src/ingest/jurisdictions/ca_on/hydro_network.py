"""Ontario Hydro Network (OHN) ingestion — watercourse segments and barriers.

Source: LIO Open Data MapServer (LIO_Open01)
  Layer 26: OHN Watercourse (stream segments with flow direction)
  Layer 6:  OHN Hydrographic Point (Falls, Rapids, Rocks, Sea Lamprey Barrier)

Fetch is scoped to a bounding box derived from lat/lon/radius_km. The default
300km radius around Toronto covers southern Ontario (~500k segments expected).

The ArcGIS MapServer applies scale-dependent spatial sampling for large bboxes:
a 300km bbox returns a spatially thinned subset rather than paginating completely.
To avoid this, the outer bbox is pre-tiled into _TILE_DEG × _TILE_DEG sub-tiles
before querying. Each sub-tile is small enough (~55km) that the service returns
complete, unsampled results.

Within each sub-tile, pagination uses resultOffset. If any single-tile page
returns exactly _PAGE_SIZE records the sub-tile is split into 4 quadrants
recursively. Features are deduplicated by OGF_ID across all tiles.

Geometry simplification: segments whose centroid is more than 75km from the
query centre are stored as POINT(lng lat) rather than the full LINESTRING.
This halves storage for distant segments while preserving graph topology
(start_node / end_node are always kept from the original line endpoints).

Cache TTL: 30 days. Each paginated request is cached separately by URL + params.
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
    "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open01/MapServer"
)
_WATERCOURSE_LAYER = 26
_HYDRO_POINT_LAYER = 6
_PAGE_SIZE = 5000
_CACHE_DIR = Path("data/cache/ohn")
_CACHE_TTL_SECONDS = 2_592_000  # 30 days
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"
# Barriers more than this far from any segment are discarded (degrees; ~200m at 43°N)
_MAX_SNAP_DIST_DEG = 0.002
# Segments beyond this distance from the query centre get simplified to POINT WKT
_SIMPLIFY_BEYOND_KM = 75.0
# Maximum recursion depth for bbox tiling within a single grid tile
_MAX_TILE_DEPTH = 5
# Pre-tile the outer bbox into sub-tiles of this degree width/height.
# ~0.5° ≈ 55km lat × 40km lon at 43°N — safely below the ArcGIS scale-sampling threshold.
_TILE_DEG = 0.5

logger = logging.getLogger(__name__)


def fetch_watercourses(lat: float, lon: float, radius_km: float = 300.0) -> list[StreamSegment]:
    """Fetch OHN watercourse segments within radius_km of lat/lon. Cached 30 days."""
    min_lon, min_lat, max_lon, max_lat = _bbox(lat, lon, radius_km)
    base_params = {
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": (
            "OGF_ID,WATERCOURSE_TYPE,OFFICIAL_NAME_LABEL,"
            "FLOW_DIRECTION_VERIFIED_IND,PERMANENCY,"
            "FLOW_CLASSIFICATION,SYSTEM_CALCULATED_LENGTH"
        ),
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": _PAGE_SIZE,
        "f": "json",
    }
    url = f"{_SERVICE_BASE}/{_WATERCOURSE_LAYER}/query"

    seen: dict[int, dict] = {}
    tiles = list(_grid_tiles(min_lon, min_lat, max_lon, max_lat))
    logger.info("OHN watercourse: fetching %d sub-tiles for %.0fkm radius", len(tiles), radius_km)
    for i, (t_min_lon, t_min_lat, t_max_lon, t_max_lat) in enumerate(tiles, 1):
        for feat in _fetch_tile(url, base_params, t_min_lon, t_min_lat, t_max_lon, t_max_lat):
            ogf_id = feat.get("attributes", {}).get("OGF_ID")
            if ogf_id is not None and ogf_id not in seen:
                seen[ogf_id] = feat
        if i % 50 == 0:
            logger.info(
                "OHN watercourse: processed %d/%d tiles (%d features so far)",
                i, len(tiles), len(seen),
            )

    segments: list[StreamSegment] = []
    for feat in seen.values():
        seg = _parse_segment(feat, home_lat=lat, home_lon=lon)
        if seg is not None:
            segments.append(seg)

    logger.info("OHN watercourse fetch complete: %d segments", len(segments))
    return segments


def fetch_barriers(
    lat: float,
    lon: float,
    radius_km: float = 300.0,
    segments: list[StreamSegment] | None = None,
) -> list[HydroBarrier]:
    """Fetch OHN hydrographic barrier points within radius_km of lat/lon.

    If segments is provided, each barrier is snapped to its nearest segment
    (within _MAX_SNAP_DIST_DEG). Barriers that can't be snapped are still
    included with nearest_segment_ogf_id=None.
    """
    min_lon, min_lat, max_lon, max_lat = _bbox(lat, lon, radius_km)
    base_params = {
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OGF_ID,HYDROGRAPHIC_POINT_TYPE",
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": _PAGE_SIZE,
        "f": "json",
    }
    url = f"{_SERVICE_BASE}/{_HYDRO_POINT_LAYER}/query"

    seen: dict[int, dict] = {}
    for t_bbox in _grid_tiles(min_lon, min_lat, max_lon, max_lat):
        for feat in _fetch_tile(url, base_params, *t_bbox):
            ogf_id = feat.get("attributes", {}).get("OGF_ID")
            if ogf_id is not None and ogf_id not in seen:
                seen[ogf_id] = feat

    # Build spatial index once for all segment snapping
    snap_index = _build_snap_index(segments) if segments else None

    barriers: list[HydroBarrier] = []
    for feat in seen.values():
        barrier = _parse_barrier(feat, segments, snap_index)
        if barrier is not None:
            barriers.append(barrier)

    logger.info("OHN barrier fetch complete: %d points", len(barriers))
    return barriers


# ── grid tiling ───────────────────────────────────────────────────────────────


def _grid_tiles(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> list[tuple[float, float, float, float]]:
    """Split a bbox into sub-tiles of _TILE_DEG × _TILE_DEG.

    Returns a list of (min_lon, min_lat, max_lon, max_lat) tuples.
    """
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


# ── tiled pagination ──────────────────────────────────────────────────────────


def _fetch_tile(
    url: str,
    base_params: dict,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    depth: int = 0,
) -> list[dict]:
    """Paginate a single bbox tile, recursively splitting into quadrants if a
    server record cap is suspected (total results = exact multiple of _PAGE_SIZE).
    """
    if depth > _MAX_TILE_DEPTH:
        logger.warning(
            "OHN: max tiling depth %d reached for bbox %.3f,%.3f,%.3f,%.3f — may be incomplete",
            _MAX_TILE_DEPTH, min_lon, min_lat, max_lon, max_lat,
        )
        return []

    bbox_str = f"{min_lon:.5f},{min_lat:.5f},{max_lon:.5f},{max_lat:.5f}"
    features: list[dict] = []
    offset = 0

    while True:
        params = {**base_params, "geometry": bbox_str, "resultOffset": offset}
        data = _cached_get(url, params)
        page = data.get("features", [])
        features.extend(page)
        logger.debug("OHN tile depth=%d offset=%d: %d features", depth, offset, len(page))

        if not page or len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    # Exact multiple of _PAGE_SIZE → server may have capped results; tile to confirm
    if features and len(features) % _PAGE_SIZE == 0:
        logger.info(
            "OHN: possible record cap at %d features (depth=%d) — splitting into quadrants",
            len(features), depth,
        )
        mid_lon = (min_lon + max_lon) / 2
        mid_lat = (min_lat + max_lat) / 2
        quadrants = [
            (min_lon, min_lat, mid_lon, mid_lat),
            (mid_lon, min_lat, max_lon, mid_lat),
            (min_lon, mid_lat, mid_lon, max_lat),
            (mid_lon, mid_lat, max_lon, max_lat),
        ]
        seen: set = set()
        tiled: list[dict] = []
        for q in quadrants:
            for feat in _fetch_tile(url, base_params, *q, depth=depth + 1):
                ogf_id = feat.get("attributes", {}).get("OGF_ID")
                if ogf_id not in seen:
                    seen.add(ogf_id)
                    tiled.append(feat)
        return tiled

    return features


# ── internal parsers ──────────────────────────────────────────────────────────


def _parse_segment(
    feat: dict,
    home_lat: float | None = None,
    home_lon: float | None = None,
) -> StreamSegment | None:
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

    # Simplify distant segments to centroid POINT to halve storage while
    # preserving topology (start_node / end_node are kept from original endpoints)
    if home_lat is not None and home_lon is not None:
        c = line.centroid
        dist_km = _haversine_km(home_lat, home_lon, c.y, c.x)
        geom_wkt = Point(c.x, c.y).wkt if dist_km > _SIMPLIFY_BEYOND_KM else line.wkt
    else:
        geom_wkt = line.wkt

    try:
        return StreamSegment(
            ogf_id=int(attrs["OGF_ID"]),
            watercourse_type=attrs.get("WATERCOURSE_TYPE") or "Stream",
            name=attrs.get("OFFICIAL_NAME_LABEL") or None,
            flow_verified=attrs.get("FLOW_DIRECTION_VERIFIED_IND") == "Yes",
            permanency=attrs.get("PERMANENCY") or "Permanent",
            flow_classification=attrs.get("FLOW_CLASSIFICATION") or None,
            length_m=float(attrs.get("SYSTEM_CALCULATED_LENGTH") or 0.0),
            geom_wkt=geom_wkt,
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
    snap_index: tuple | None = None,
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
    nearest_ogf_id, snap_dist_m = _snap_to_nearest_segment(point, segments, snap_index)

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


def _build_snap_index(
    segments: list[StreamSegment],
) -> tuple[object, list[int]] | None:
    """Build a Shapely STRtree spatial index over segment geometries.

    Returns (tree, ogf_ids) where ogf_ids[i] is the OGF_ID of tree geometry i.
    Returns None if segments is empty.
    """
    from shapely.strtree import STRtree
    from shapely.wkt import loads as wkt_loads

    geoms = []
    ogf_ids: list[int] = []
    for seg in segments:
        try:
            geoms.append(wkt_loads(seg.geom_wkt))
            ogf_ids.append(seg.ogf_id)
        except Exception:
            continue
    if not geoms:
        return None
    return STRtree(geoms), ogf_ids


def _snap_to_nearest_segment(
    point: Point,
    segments: list[StreamSegment] | None,
    _index: tuple | None = None,
) -> tuple[int | None, float | None]:
    """Return (ogf_id, distance_m) of nearest segment, or (None, None) if too far.

    If _index is provided it must be (STRtree, ogf_ids) from _build_snap_index —
    this avoids rebuilding the index for every barrier point.
    """
    if not segments:
        return None, None

    if _index is not None:
        tree, ogf_ids = _index
    else:
        result = _build_snap_index(segments)
        if result is None:
            return None, None
        tree, ogf_ids = result

    idx = tree.nearest(point)
    if idx is None:
        return None, None

    from shapely.wkt import loads as wkt_loads
    geom = wkt_loads(segments[idx].geom_wkt)
    min_dist = point.distance(geom)

    if min_dist > _MAX_SNAP_DIST_DEG:
        return None, None

    snap_dist_m = round(min_dist * 111_000, 1)
    return ogf_ids[idx], snap_dist_m


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


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))
