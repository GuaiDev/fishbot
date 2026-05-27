"""SDM feature matrix builder for OHN stream segments.

Joins all Phase 1 habitat data layers onto stream segments.
Output: one row per segment with 17 features.

Feature source note:
  Features 6-7 (thermal_regime, summer_mean_temp_c) come from
  stream_temperature_summaries (HYDAT-derived), not PWQMN, because
  that is where the thermal regime classification lives.
  Features 8-10 come from water_quality_readings (PWQMN), aggregated
  to per-station medians. Both use nearest upstream station within 15km
  network distance.
"""

import logging
import re
import time
from collections import Counter, deque
from datetime import date
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

from src.storage.database import DB_PATH, get_db

logger = logging.getLogger(__name__)

_PARQUET_PATH = Path("data/processed/sdm_feature_matrix.parquet")
_SOURCE_TABLES = [
    "stream_segments",
    "water_quality_readings",
    "stream_temperature_summaries",
    "benthic_samples",
    "geology_units",
    "stocking_records",
    "observations",
    "gbif_observations",
]

_WQ_MAX_KM = 15.0
_THERMAL_MAX_KM = 15.0
_EPT_MAX_KM = 15.0
_BARRIER_MAX_KM = 20.0
_CATCHMENT_MAX_KM = 100.0
_OBS_MAX_KM = 50.0
_STOCKING_RADIUS_DEG = 0.018  # ~2km
_OBS_DENSITY_DEG = 0.225  # ~25km
_MAX_SNAP_DEG = 0.02
_STOCKING_YEARS = 5

_COORD_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")

_HABITAT_COLS = [
    "substrate_category",
    "upstream_catchment_geology",
    "thermal_regime",
    "summer_mean_temp_c",
    "do_median_mgl",
    "ph_median",
    "conductivity_median_us_cm",
    "ept_quality",
    "ept_proportion",
    "barrier_count_upstream",
]


# ── public API ────────────────────────────────────────────────────────────────


def build_feature_matrix(db=None) -> pd.DataFrame:
    """Build or load cached SDM feature matrix. One row per OHN stream segment."""
    if db is None:
        db = get_db()

    if _is_cache_valid():
        logger.info("Loading feature matrix from cache: %s", _PARQUET_PATH)
        return pd.read_parquet(_PARQUET_PATH)

    t0 = time.time()
    logger.info("Building SDM feature matrix from scratch...")

    from src.services.hydrology import HydrologyService

    G = HydrologyService(db).get_graph()
    snap_fn = _make_snap_fn(G)

    segments = list(db["stream_segments"].rows)

    centroids = _segment_centroids(segments)
    strahler = _compute_strahler_order(G)

    geology_rows = list(db["geology_units"].rows)
    local_substrate = _assign_geology(centroids, geology_rows)
    upstream_catchment = _upstream_catchment_geology(G, local_substrate)

    thermal_rows = list(db["stream_temperature_summaries"].rows)
    thermal_map = _assign_from_upstream_stations(G, snap_fn, thermal_rows, _THERMAL_MAX_KM)

    wq_rows = list(db["water_quality_readings"].rows)
    wq_agg = _aggregate_wq_by_station(wq_rows)
    wq_map = _assign_from_upstream_stations(G, snap_fn, wq_agg, _WQ_MAX_KM)

    benthic_rows = list(db["benthic_samples"].rows)
    ept_map = _assign_from_upstream_stations(G, snap_fn, benthic_rows, _EPT_MAX_KM)

    barrier_rows = list(db["barriers"].rows)
    barrier_counts = _count_upstream_barriers(G, snap_fn, barrier_rows)

    obs_rows = list(db["observations"].rows)
    gbif_rows = list(db["gbif_observations"].rows)
    all_obs_pts: list[tuple[float, float]] = (
        [(r["lat"], r["lng"]) for r in obs_rows if r.get("lat") and r.get("lng")]
        + [(r["lat"], r["lng"]) for r in gbif_rows if r.get("lat") and r.get("lng")]
    )
    seg_start_nodes = {r["ogf_id"]: r["start_node"] for r in segments}
    seg_end_nodes = {r["ogf_id"]: r["end_node"] for r in segments}
    obs_distances = _nearest_observation_distance(
        G, snap_fn, all_obs_pts, seg_start_nodes, seg_end_nodes
    )
    obs_density = _observation_density(centroids, all_obs_pts)

    stocking_rows = list(db["stocking_records"].rows)
    stocking_map = _assign_stocking(centroids, stocking_rows)

    rows = []
    for seg in segments:
        oid = seg["ogf_id"]
        lat, lng = centroids.get(oid, (None, None))
        thermal = thermal_map.get(oid, {})
        wq = wq_map.get(oid, {})
        ept = ept_map.get(oid, {})
        stocking = stocking_map.get(oid, {})

        rows.append(
            {
                "ogf_id": oid,
                "centroid_lat": lat,
                "centroid_lng": lng,
                "stream_order": strahler.get(oid),
                "length_m": seg.get("length_m"),
                "flow_verified": bool(seg.get("flow_verified", 0)),
                "substrate_category": local_substrate.get(oid),
                "upstream_catchment_geology": upstream_catchment.get(oid),
                "thermal_regime": thermal.get("thermal_regime", "unknown"),
                "summer_mean_temp_c": thermal.get("summer_mean_c"),
                "do_median_mgl": wq.get("do_median_mgl"),
                "ph_median": wq.get("ph_median"),
                "conductivity_median_us_cm": wq.get("conductivity_median_us_cm"),
                "ept_quality": ept.get("habitat_quality", "unknown"),
                "ept_proportion": ept.get("ept_proportion"),
                "barrier_count_upstream": barrier_counts.get(oid, 0),
                "distance_to_nearest_observation_km": obs_distances.get(oid),
                "observation_density_25km": obs_density.get(oid, 0),
                "is_stocked_within_5yr": stocking.get("is_stocked", False),
                "nearest_stocked_species": stocking.get("species"),
            }
        )

    df = pd.DataFrame(rows)
    _PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_PARQUET_PATH, index=False)

    elapsed = time.time() - t0
    logger.info("Feature matrix: %d segments built in %.1fs", len(df), elapsed)
    return df


def coverage_fraction(df: pd.DataFrame) -> float:
    """Fraction of segments with no null/unknown in habitat features 4-13."""
    str_cols = [c for c in _HABITAT_COLS if df[c].dtype == object]
    num_cols = [c for c in _HABITAT_COLS if df[c].dtype != object]
    str_ok = (df[str_cols].notna() & (df[str_cols] != "unknown")).all(axis=1)
    num_ok = df[num_cols].notna().all(axis=1)
    return float((str_ok & num_ok).mean())


# ── cache helpers ─────────────────────────────────────────────────────────────


def _is_cache_valid() -> bool:
    if not _PARQUET_PATH.exists():
        return False
    if not DB_PATH.exists():
        return False
    return _PARQUET_PATH.stat().st_mtime >= DB_PATH.stat().st_mtime


# ── node snap ────────────────────────────────────────────────────────────────


def _make_snap_fn(G: nx.DiGraph):
    """Return a vectorized nearest-node snap function for the graph."""
    nodes = list(G.nodes())
    if not nodes:
        return lambda lat, lng: None

    node_lats = np.empty(len(nodes))
    node_lngs = np.empty(len(nodes))
    for i, node in enumerate(nodes):
        parts = node.split(",")
        node_lngs[i] = float(parts[0])
        node_lats[i] = float(parts[1])

    def snap_fn(lat: float, lng: float) -> str | None:
        dists = np.sqrt((node_lats - lat) ** 2 + (node_lngs - lng) ** 2)
        idx = int(np.argmin(dists))
        if dists[idx] > _MAX_SNAP_DEG:
            return None
        return nodes[idx]

    return snap_fn


# ── feature helpers ───────────────────────────────────────────────────────────


def _segment_centroids(segments: list[dict]) -> dict[int, tuple[float, float]]:
    """Average of all coordinate pairs in each segment's LINESTRING WKT."""
    result: dict[int, tuple[float, float]] = {}
    for seg in segments:
        coords = _COORD_RE.findall(seg.get("geom_wkt", ""))
        if not coords:
            continue
        lngs = [float(c[0]) for c in coords]
        lats = [float(c[1]) for c in coords]
        result[seg["ogf_id"]] = (sum(lats) / len(lats), sum(lngs) / len(lngs))
    return result


def _compute_strahler_order(G: nx.DiGraph) -> dict[int, int]:
    """Strahler stream order per segment (ogf_id).

    Deduplicates bidirectional edges from unverified-flow segments before
    computing topological order. Falls back to order=1 on cycles.
    """
    seen_ogf: set[int] = set()
    dag = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        ogf_id = data.get("ogf_id")
        if ogf_id is None or ogf_id in seen_ogf:
            continue
        seen_ogf.add(ogf_id)
        dag.add_edge(u, v, **data)

    try:
        topo = list(nx.topological_sort(dag))
    except nx.NetworkXUnfeasible:
        return {data["ogf_id"]: 1 for _, _, data in dag.edges(data=True) if "ogf_id" in data}

    node_order: dict[str, int] = {}
    for node in topo:
        preds = list(dag.predecessors(node))
        if not preds:
            node_order[node] = 1
        else:
            incoming = [node_order.get(p, 1) for p in preds]
            max_o = max(incoming)
            node_order[node] = max_o + 1 if incoming.count(max_o) >= 2 else max_o

    return {
        data["ogf_id"]: node_order.get(u, 1)
        for u, v, data in dag.edges(data=True)
        if "ogf_id" in data
    }


def _assign_geology(
    centroids: dict[int, tuple[float, float]],
    geology_rows: list[dict],
) -> dict[int, str]:
    """Nearest geology unit substrate_class for each segment centroid."""
    if not geology_rows or not centroids:
        return {}

    geo_lats = np.array([r["centroid_lat"] for r in geology_rows])
    geo_lngs = np.array([r["centroid_lng"] for r in geology_rows])
    classes = [r["substrate_class"] for r in geology_rows]

    result: dict[int, str] = {}
    for ogf_id, (lat, lng) in centroids.items():
        dists = np.sqrt((geo_lats - lat) ** 2 + (geo_lngs - lng) ** 2)
        result[ogf_id] = classes[int(np.argmin(dists))]
    return result


def _upstream_catchment_geology(
    G: nx.DiGraph,
    local_substrate: dict[int, str],
) -> dict[int, str]:
    """Majority substrate_class within 100km upstream of each segment."""
    node_cache: dict[str, str] = {}
    result: dict[int, str] = {}

    for u, v, data in G.edges(data=True):
        ogf_id = data.get("ogf_id")
        if ogf_id is None:
            continue

        if u not in node_cache:
            visited: set[str] = {u}
            queue: deque[tuple[str, float]] = deque([(u, 0.0)])
            substrates: list[str] = []

            while queue:
                current, dist = queue.popleft()
                for pred in G.predecessors(current):
                    if pred in visited:
                        continue
                    edge = G[pred][current]
                    new_dist = dist + edge.get("length_m", 0.0) / 1000.0
                    if new_dist <= _CATCHMENT_MAX_KM:
                        visited.add(pred)
                        up_id = edge.get("ogf_id")
                        if up_id and up_id in local_substrate:
                            substrates.append(local_substrate[up_id])
                        queue.append((pred, new_dist))

            node_cache[u] = (
                Counter(substrates).most_common(1)[0][0]
                if substrates
                else local_substrate.get(ogf_id, "unknown")
            )

        result[ogf_id] = node_cache[u]

    return result


def _aggregate_wq_by_station(wq_rows: list[dict]) -> list[dict]:
    """Aggregate WQ readings to per-station medians."""
    if not wq_rows:
        return []
    df = pd.DataFrame(wq_rows)
    agg = (
        df.groupby("station_id")
        .agg(
            lat=("lat", "first"),
            lng=("lng", "first"),
            do_median_mgl=("do_mgl", "median"),
            ph_median=("ph", "median"),
            conductivity_median_us_cm=("conductivity_us_cm", "median"),
        )
        .reset_index()
    )
    return agg.to_dict("records")


def _assign_from_upstream_stations(
    G: nx.DiGraph,
    snap_fn: Any,
    station_rows: list[dict],
    max_km: float,
) -> dict[int, dict]:
    """For each segment, return the row of its nearest upstream station within max_km.

    A station is upstream of a segment if the segment is reachable by BFS
    following successors (downstream) from the station's snap node.
    """
    seg_to: dict[int, tuple[float, dict]] = {}

    for row in station_rows:
        lat = row.get("lat")
        lng = row.get("lng")
        if lat is None or lng is None:
            continue
        node = snap_fn(float(lat), float(lng))
        if node is None:
            continue

        visited: set[str] = {node}
        queue: deque[tuple[str, float]] = deque([(node, 0.0)])

        while queue:
            current, dist = queue.popleft()
            for nbr in G.successors(current):
                if nbr in visited:
                    continue
                edge = G[current][nbr]
                new_dist = dist + edge.get("length_m", 0.0) / 1000.0
                if new_dist <= max_km:
                    visited.add(nbr)
                    ogf_id = edge.get("ogf_id")
                    if ogf_id is not None:
                        existing = seg_to.get(ogf_id)
                        if existing is None or new_dist < existing[0]:
                            seg_to[ogf_id] = (new_dist, row)
                    queue.append((nbr, new_dist))

    return {ogf_id: row for ogf_id, (_, row) in seg_to.items()}


def _count_upstream_barriers(
    G: nx.DiGraph,
    snap_fn: Any,
    barrier_rows: list[dict],
    max_km: float = _BARRIER_MAX_KM,
) -> dict[int, int]:
    """Count how many barriers lie within max_km upstream of each segment."""
    counts: dict[int, int] = {}

    for row in barrier_rows:
        coords = _COORD_RE.findall(row.get("geom_wkt", ""))
        if not coords:
            continue
        lng, lat = float(coords[0][0]), float(coords[0][1])
        node = snap_fn(lat, lng)
        if node is None:
            continue

        visited: set[str] = {node}
        queue: deque[tuple[str, float]] = deque([(node, 0.0)])

        while queue:
            current, dist = queue.popleft()
            for nbr in G.successors(current):
                if nbr in visited:
                    continue
                edge = G[current][nbr]
                new_dist = dist + edge.get("length_m", 0.0) / 1000.0
                if new_dist <= max_km:
                    visited.add(nbr)
                    ogf_id = edge.get("ogf_id")
                    if ogf_id is not None:
                        counts[ogf_id] = counts.get(ogf_id, 0) + 1
                    queue.append((nbr, new_dist))

    return counts


def _nearest_observation_distance(
    G: nx.DiGraph,
    snap_fn: Any,
    obs_latlngs: list[tuple[float, float]],
    seg_start_nodes: dict[int, str],
    seg_end_nodes: dict[int, str],
    max_km: float = _OBS_MAX_KM,
) -> dict[int, float | None]:
    """Multi-source Dijkstra: O(V+E) distance from every segment to nearest observation.

    Seeds the graph frontier simultaneously from all observation snap-nodes.
    Each node records distance when first reached — equivalent to running
    Dijkstra from every observation independently but in one O(V+E) pass.
    """
    sources: set[str] = set()
    for lat, lng in obs_latlngs:
        node = snap_fn(lat, lng)
        if node:
            sources.add(node)

    if not sources:
        return {}

    node_dists: dict[str, float] = dict(
        nx.multi_source_dijkstra_path_length(
            G.to_undirected(),
            sources,
            cutoff=max_km * 1000.0,
            weight="length_m",
        )
    )

    result: dict[int, float | None] = {}
    for ogf_id, start in seg_start_nodes.items():
        end = seg_end_nodes.get(ogf_id)
        candidates = [
            node_dists[n] / 1000.0 for n in (start, end) if n and n in node_dists
        ]
        result[ogf_id] = min(candidates) if candidates else None

    return result


def _observation_density(
    centroids: dict[int, tuple[float, float]],
    obs_pts: list[tuple[float, float]],
    radius_deg: float = _OBS_DENSITY_DEG,
) -> dict[int, int]:
    """Count observations within radius_deg of each segment centroid (Euclidean)."""
    if not obs_pts:
        return {ogf_id: 0 for ogf_id in centroids}

    cell = 0.5
    from collections import defaultdict

    grid: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    for lat, lng in obs_pts:
        grid[(round(lat / cell), round(lng / cell))].append((lat, lng))

    cells_r = int(radius_deg / cell) + 1
    result: dict[int, int] = {}
    for ogf_id, (lat, lng) in centroids.items():
        clat, clng = round(lat / cell), round(lng / cell)
        count = 0
        for dlat in range(-cells_r, cells_r + 1):
            for dlng in range(-cells_r, cells_r + 1):
                for plat, plng in grid.get((clat + dlat, clng + dlng), []):
                    if abs(plat - lat) <= radius_deg and abs(plng - lng) <= radius_deg:
                        count += 1
        result[ogf_id] = count
    return result


def _assign_stocking(
    centroids: dict[int, tuple[float, float]],
    stocking_rows: list[dict],
    radius_deg: float = _STOCKING_RADIUS_DEG,
) -> dict[int, dict]:
    """Mark segments with stocking events within radius in the last 5 years."""
    cutoff_year = date.today().year - _STOCKING_YEARS
    recent = [
        r
        for r in stocking_rows
        if r.get("lat") and r.get("lng") and (r.get("year") or 0) >= cutoff_year
    ]
    if not recent:
        return {}

    stock_lats = np.array([r["lat"] for r in recent])
    stock_lngs = np.array([r["lng"] for r in recent])

    result: dict[int, dict] = {}
    for ogf_id, (lat, lng) in centroids.items():
        dists = np.sqrt((stock_lats - lat) ** 2 + (stock_lngs - lng) ** 2)
        within = np.where(dists <= radius_deg)[0]
        if len(within) > 0:
            nearest = within[int(np.argmin(dists[within]))]
            result[ogf_id] = {
                "is_stocked": True,
                "species": recent[nearest].get("species"),
            }
    return result
