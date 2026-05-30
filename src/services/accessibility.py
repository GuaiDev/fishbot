"""Access score computation for OHN stream segments.

Score formula (start at 1.0, apply modifiers):

  Park type  : Recreational +0.3, Waterway +0.2, Natural Environment +0.1,
               Cultural Heritage 0.0, Nature Reserve -0.3, Wilderness -0.4,
               No park 0.0 (Crown land is generally accessible)
  Road prox  : within 200m +0.2, within 500m +0.1, >1km -0.2
               (uses access_type='road' or 'parking' as road proxy)
  Building   : within 500m +0.1  (access_type='building')
  Boat launch: within 1km +0.2   (access_type='boat_launch')
  Fishing    : within 500m +0.3  (access_type='fishing_spot')
  Park/CA AP : within 500m +0.1  (access_type in park/conservation_area/public_land)
  Parking    : within 500m +0.1  (access_type='parking')

Raw score clamped to [0.0, 2.0], then normalized to [0, 1] across all segments.
Result cached to data/processed/access_scores.parquet.

Coverage limitation: access scores are only meaningful within the OSM ingestion
radius (~55km of home). Segments outside this radius receive a neutral baseline
score (~0.27 in the current Ontario-wide dataset) and are not meaningfully
differentiated by access. find_untapped_water results within the OSM coverage
area have the most reliable access discrimination.
"""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

logger = logging.getLogger(__name__)

_PARQUET_PATH = Path("data/processed/access_scores.parquet")
_DEG_TO_KM = 111.0  # approximate — accurate enough for sub-km threshold checks

_PARK_MODIFIERS = {
    "Recreational": 0.3,
    "Waterway": 0.2,
    "Natural Environment": 0.1,
    "Cultural Heritage": 0.0,
    "Nature Reserve": -0.3,
    "Wilderness": -0.4,
}


def compute_access_scores(db: Any, feature_matrix: pd.DataFrame) -> pd.Series:
    """Compute normalised access score [0, 1] for each segment.

    Returns pd.Series indexed by ogf_id.
    Result is also cached to data/processed/access_scores.parquet.
    """
    logger.info("Loading spatial data for access scoring...")
    park_tree, park_data = _build_park_index(db)
    access_by_type = _load_access_points(db)

    coords = feature_matrix[["centroid_lat", "centroid_lng"]].values
    ogf_ids = feature_matrix["ogf_id"].values

    logger.info("Computing park containment for %d segments...", len(coords))
    park_modifiers = _vectorized_park_modifier(park_tree, park_data, coords)

    logger.info("Computing proximity modifiers...")
    road_mod = _road_proximity_modifier(access_by_type, coords)
    building_mod = _distance_modifier(access_by_type.get("building", []), coords, 0.5, 0.1)
    boat_mod = _distance_modifier(access_by_type.get("boat_launch", []), coords, 1.0, 0.2)
    fishing_mod = _distance_modifier(access_by_type.get("fishing_spot", []), coords, 0.5, 0.3)
    park_ap_mod = _distance_modifier(
        access_by_type.get("park", [])
        + access_by_type.get("conservation_area", [])
        + access_by_type.get("public_land", []),
        coords,
        0.5,
        0.1,
    )
    parking_mod = _distance_modifier(access_by_type.get("parking", []), coords, 0.5, 0.1)

    raw = (
        1.0
        + park_modifiers
        + road_mod
        + building_mod
        + boat_mod
        + fishing_mod
        + park_ap_mod
        + parking_mod
    )
    raw = np.clip(raw, 0.0, 2.0)

    # Normalize distribution to [0, 1]
    lo, hi = raw.min(), raw.max()
    if hi > lo:
        normalized = (raw - lo) / (hi - lo)
    else:
        normalized = np.full_like(raw, 0.5)

    result = pd.Series(normalized.astype(np.float32), index=ogf_ids, name="access_score")

    _PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_frame().to_parquet(_PARQUET_PATH)
    logger.info("Access scores written to %s", _PARQUET_PATH)

    return result


def load_cached_scores() -> pd.Series | None:
    """Load access scores from parquet cache, or None if not computed yet."""
    if not _PARQUET_PATH.exists():
        return None
    df = pd.read_parquet(_PARQUET_PATH)
    return df["access_score"]


# ── spatial helpers ───────────────────────────────────────────────────────────


def _build_park_index(db: Any) -> tuple[STRtree | None, list[dict]]:
    """Build Shapely STRtree over provincial park polygons."""
    if "provincial_parks" not in db.table_names():
        return None, []

    rows = list(db["provincial_parks"].rows)
    if not rows:
        return None, []

    polygons = []
    park_data = []
    for row in rows:
        try:
            rings = json.loads(row["polygon_json"])
            if not rings or not rings[0]:
                continue
            # GeoJSON ring format: [[lng, lat], ...] — swap to (lng, lat) for Shapely
            outer = [(pt[0], pt[1]) for pt in rings[0]]
            if len(outer) < 4:
                continue
            poly = Polygon(outer)
            if not poly.is_valid:
                poly = poly.buffer(0)
            polygons.append(poly)
            park_data.append({"park_type": row["park_type"]})
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue

    if not polygons:
        return None, []

    tree = STRtree(polygons)
    return tree, park_data


def _vectorized_park_modifier(
    tree: STRtree | None,
    park_data: list[dict],
    coords: np.ndarray,
) -> np.ndarray:
    """Return park modifier array for all segment centroids."""
    result = np.zeros(len(coords), dtype=np.float32)
    if tree is None or not park_data:
        return result

    # Build Shapely Point array (lng, lat order for Shapely)
    points = np.array(
        [Point(float(lng), float(lat)) for lat, lng in coords],
        dtype=object,
    )

    # STRtree.query with 'within' predicate: returns (point_idx, park_idx) pairs
    # Shapely 2.x: query(geometry_array, predicate) -> shape (2, n) array
    hits = tree.query(points, predicate="within")
    if hits.size == 0:
        return result

    # hits[0] = indices into points array, hits[1] = indices into park_data
    for pt_idx, park_idx in zip(hits[0], hits[1]):
        park_type = park_data[park_idx]["park_type"]
        result[pt_idx] = _PARK_MODIFIERS.get(park_type, 0.0)

    return result


def _load_access_points(db: Any) -> dict[str, list[tuple[float, float]]]:
    """Load access points from DB, grouped by access_type."""
    if "access_points" not in db.table_names():
        return {}

    by_type: dict[str, list[tuple[float, float]]] = {}
    for row in db["access_points"].rows:
        atype = row.get("access_type") or ""
        lat = row.get("lat")
        lng = row.get("lng")
        if lat is None or lng is None:
            continue
        by_type.setdefault(atype, []).append((float(lat), float(lng)))
    return by_type


def _road_proximity_modifier(
    access_by_type: dict[str, list[tuple[float, float]]],
    coords: np.ndarray,
) -> np.ndarray:
    """Road proximity: use access_type='road' entries, fall back to 'parking' as proxy.

    +0.2 if within 200m, +0.1 if within 500m, -0.2 if nothing within 1km.
    Returns 0.0 for segments outside the ingest area (no data available).
    """
    # Combine road entries and parking as proxy (parking requires road access)
    road_pts = access_by_type.get("road", []) + access_by_type.get("parking", [])
    if not road_pts:
        return np.zeros(len(coords), dtype=np.float32)

    road_arr = np.array(road_pts)
    tree = cKDTree(road_arr)

    # Query nearest road/parking point for every segment.
    # Upper bound ~33km: far enough to penalise remote-in-coverage segments,
    # returns inf for segments genuinely outside the ingest area (→ neutral 0.0).
    dists, _ = tree.query(coords, workers=-1, distance_upper_bound=0.30)

    dists_km = dists * _DEG_TO_KM
    mod = np.where(
        dists_km <= 0.2,
        0.2,
        np.where(
            dists_km <= 0.5,
            0.1,
            np.where(
                dists_km <= 1.0,
                0.0,
                np.where(
                    dists_km <= 30.0,
                    -0.2,
                    0.0,  # inf or >30km → outside ingest coverage → neutral
                ),
            ),
        ),
    )
    return mod.astype(np.float32)


def _distance_modifier(
    pts: list[tuple[float, float]],
    coords: np.ndarray,
    threshold_km: float,
    bonus: float,
) -> np.ndarray:
    """Return bonus array: +bonus for segments with any point in pts within threshold_km."""
    if not pts:
        return np.zeros(len(coords), dtype=np.float32)

    arr = np.array(pts)
    tree = cKDTree(arr)
    threshold_deg = threshold_km / _DEG_TO_KM
    dists, _ = tree.query(coords, workers=-1, distance_upper_bound=threshold_deg * 1.05)
    dists_km = dists * _DEG_TO_KM
    return np.where(dists_km <= threshold_km, bonus, 0.0).astype(np.float32)
