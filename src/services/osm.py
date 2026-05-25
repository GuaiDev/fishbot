"""OSM service — bridges the Overpass ingest layer to the agent.

Uses importlib because src/ingest/global/ contains a Python keyword ('global')
that blocks normal import syntax.
"""

import importlib
import json
import math
import warnings

import httpx

from src.storage.database import get_db
from src.storage.osm_features import upsert_access_points, upsert_water_features

_osm = importlib.import_module("src.ingest.global.osm")

_NON_FISHABLE_TYPES = frozenset({"ditch", "drain"})
_MIN_FISHABLE_AREA_M2 = 50.0
_MAX_RESULTS = 15
_DATA_STATUS = (
    "OSM shows what water exists and where. "
    "Current ranking is by convenience only (distance + size). "
    "Habitat suitability and species predictions are not yet available — "
    "Phase 2 will replace this ranking with a model-based untapped potential score."
)


def get_nearby_water_for_agent(
    lat: float,
    lng: float,
    radius_km: float = 25,
    feature_type: str | None = None,
    not_in_trip_log: bool = False,
) -> str:
    """Return JSON with fishable water bodies near a location, ranked by convenience."""
    features = _osm.fetch_water_features(lat, lng, radius_km)

    if feature_type:
        features = [f for f in features if f.feature_type == feature_type]

    # Drop ditches, drains, and polygon features too small to fish
    features = [
        f
        for f in features
        if f.feature_type not in _NON_FISHABLE_TYPES
        and not (f.area_m2 is not None and f.area_m2 < _MIN_FISHABLE_AREA_M2)
    ]

    if not_in_trip_log:
        db = get_db()
        visited: set[str] = set()
        for row in db["trips"].rows_where("location_name IS NOT NULL"):
            name = row.get("location_name")
            if name:
                visited.add(name.lower())
        # Bidirectional substring: exclude if the water body name appears in any trip
        # location, or any trip location appears in the water body name.
        features = [
            f
            for f in features
            if not f.name or not any(f.name.lower() in v or v in f.name.lower() for v in visited)
        ]

    if not features:
        return json.dumps(
            {
                "water_bodies": [],
                "data_status": _DATA_STATUS,
                "note": f"No fishable water features found within {radius_km:.0f}km.",
            }
        )

    # Build result dicts with raw values for scoring
    results = []
    for f in features:
        dist = _haversine_km(lat, lng, f.lat, f.lng)
        if f.name:
            display_name = f.name
        elif f.area_m2 is not None:
            area_ha = f.area_m2 / 10_000
            display_name = f"unnamed {f.feature_type} (~{area_ha:.1f} ha)"
        else:
            display_name = f"unnamed {f.feature_type}"

        results.append(
            {
                "osm_id": f.osm_id,
                "display_name": display_name,
                "name": f.name,
                "feature_type": f.feature_type,
                "distance_km": round(dist, 2),
                "jurisdiction": f.jurisdiction,
                "area_m2": f.area_m2,
                "_dist": dist,
                "_area": f.area_m2 or 0.0,
            }
        )

    # Composite convenience score: 60% distance (closer = better) +
    # 40% inverted size (larger = more water to explore, NOT a quality signal).
    max_dist = max(r["_dist"] for r in results) or 1.0
    max_area = max(r["_area"] for r in results) or 1.0
    for r in results:
        dist_score = r["_dist"] / max_dist
        size_score = r["_area"] / max_area
        r["_score"] = 0.6 * dist_score + 0.4 * (1.0 - size_score)

    results.sort(key=lambda x: x["_score"])
    results = results[:_MAX_RESULTS]

    for r in results:
        del r["_dist"]
        del r["_area"]
        del r["_score"]

    return json.dumps({"water_bodies": results, "data_status": _DATA_STATUS})


def get_access_points_for_agent(
    lat: float,
    lng: float,
    radius_km: float = 25,
    access_type: str | None = None,
) -> str:
    """Return JSON with nearby access points."""
    points = _osm.fetch_access_points(lat, lng, radius_km)

    if access_type:
        points = [p for p in points if p.access_type == access_type]

    if not points:
        return json.dumps(
            {
                "access_points": [],
                "note": f"No access points found within {radius_km:.0f}km.",
            }
        )

    results = []
    for p in points:
        dist = _haversine_km(lat, lng, p.lat, p.lng)
        results.append(
            {
                "osm_id": p.osm_id,
                "name": p.name or f"unnamed {p.access_type.replace('_', ' ')}",
                "access_type": p.access_type,
                "distance_km": round(dist, 2),
                "jurisdiction": p.jurisdiction,
            }
        )

    results.sort(key=lambda x: x["distance_km"])
    return json.dumps({"access_points": results[:_MAX_RESULTS]})


def fetch_and_store(lat: float, lng: float) -> tuple[int, int]:
    """Fetch and upsert OSM features. Called by the ingest CLI.

    Returns (0, 0) if all Overpass endpoints are unavailable so that make ingest
    can continue with the other data sources rather than crashing.
    """
    try:
        features = _osm.fetch_water_features(lat, lng, radius_km=50)
        points = _osm.fetch_access_points(lat, lng, radius_km=25)
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        warnings.warn(f"OSM ingest failed after all retries — skipping: {e}", stacklevel=2)
        return 0, 0

    db = get_db()
    upsert_water_features(db, features)
    upsert_access_points(db, points)

    return len(features), len(points)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
