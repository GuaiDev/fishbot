"""SDM feature matrix builder for OHN stream segments.

Joins all Phase 1 habitat data layers onto stream segments.
Output: one row per segment with 16 features.

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
from collections import deque
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
_OBS_MAX_KM = 50.0
_STOCKING_RADIUS_DEG = 0.018  # ~2km
_OBS_DENSITY_DEG = 0.225  # ~25km
_MAX_SNAP_DEG = 0.02
_STOCKING_YEARS = 5

_COORD_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")

_HABITAT_COLS = [
    "substrate_category",
    "thermal_regime",
    "summer_mean_temp_c",
    "do_median_mgl",
    "ph_median",
    "conductivity_median_us_cm",
    "ept_quality",
    "ept_proportion",
    "barrier_count_upstream",
    # pwqmn_coverage is intentionally excluded: it's always bool (never null),
    # so including it would inflate coverage_fraction meaninglessly.
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

    # Pre-compute node position arrays once for all spatial subgraph filtering
    nodes_list = list(G.nodes())
    node_lats = np.array([float(n.split(",")[1]) for n in nodes_list])
    node_lngs = np.array([float(n.split(",")[0]) for n in nodes_list])

    segments = list(db["stream_segments"].rows)
    logger.info("Segments: %d total", len(segments))
    # Build name and type lookups for feature matrix columns
    seg_name_map: dict[int, str] = {r["ogf_id"]: (r.get("name") or "") for r in segments}
    seg_type_map: dict[int, str] = {
        r["ogf_id"]: (r.get("watercourse_type") or "") for r in segments
    }

    t = time.time()
    logger.info("Computing centroids and Strahler order...")
    centroids = _segment_centroids(segments)
    strahler = _compute_strahler_order(G)
    logger.info("  centroids + Strahler: %.1fs", time.time() - t)

    t = time.time()
    geology_rows = list(db["geology_units"].rows)
    logger.info("Assigning local geology substrate (%d units)...", len(geology_rows))
    local_substrate = _assign_geology(centroids, geology_rows)
    logger.info("  geology local: %.1fs", time.time() - t)

    thermal_rows = list(db["stream_temperature_summaries"].rows)
    thermal_src_pts = [
        (float(r["lat"]), float(r["lng"])) for r in thermal_rows if r.get("lat") and r.get("lng")
    ]
    G_thermal = _subgraph_near_sources(
        G, nodes_list, node_lats, node_lngs, thermal_src_pts, _THERMAL_MAX_KM
    )
    t = time.time()
    logger.info(
        "Computing thermal features... (%d stations, %d/%d graph nodes)",
        len(thermal_rows),
        G_thermal.number_of_nodes(),
        G.number_of_nodes(),
    )
    thermal_map = _assign_from_upstream_stations(G_thermal, snap_fn, thermal_rows, _THERMAL_MAX_KM)
    logger.info("  thermal: %.1fs", time.time() - t)

    wq_rows = list(db["water_quality_readings"].rows)
    wq_agg = _aggregate_wq_by_station(wq_rows)
    wq_src_pts = [
        (float(r["lat"]), float(r["lng"])) for r in wq_agg if r.get("lat") and r.get("lng")
    ]
    G_wq = _subgraph_near_sources(G, nodes_list, node_lats, node_lngs, wq_src_pts, _WQ_MAX_KM)
    t = time.time()
    logger.info(
        "Computing water quality features... (%d stations, %d/%d graph nodes)",
        len(wq_agg),
        G_wq.number_of_nodes(),
        G.number_of_nodes(),
    )
    wq_map = _assign_from_upstream_stations(G_wq, snap_fn, wq_agg, _WQ_MAX_KM)
    logger.info("  WQ: %.1fs", time.time() - t)

    benthic_rows = list(db["benthic_samples"].rows)
    ept_src_pts = [
        (float(r["lat"]), float(r["lng"])) for r in benthic_rows if r.get("lat") and r.get("lng")
    ]
    G_ept = _subgraph_near_sources(G, nodes_list, node_lats, node_lngs, ept_src_pts, _EPT_MAX_KM)
    t = time.time()
    logger.info(
        "Computing EPT/benthic features... (%d sites, %d/%d graph nodes)",
        len(benthic_rows),
        G_ept.number_of_nodes(),
        G.number_of_nodes(),
    )
    ept_map = _assign_from_upstream_stations(G_ept, snap_fn, benthic_rows, _EPT_MAX_KM)
    logger.info("  EPT: %.1fs", time.time() - t)

    # Filter to only barriers that were snapped to a segment during ingest —
    # unsnapped barriers are too far from the network to affect any segment's count.
    barrier_rows = list(db["barriers"].rows)
    snapped_barriers = [r for r in barrier_rows if r.get("nearest_segment_ogf_id")]
    barrier_src_pts = []
    for r in snapped_barriers:
        coords = _COORD_RE.findall(r.get("geom_wkt", ""))
        if coords:
            barrier_src_pts.append((float(coords[0][1]), float(coords[0][0])))
    G_barriers = _subgraph_near_sources(
        G, nodes_list, node_lats, node_lngs, barrier_src_pts, _BARRIER_MAX_KM
    )
    t = time.time()
    logger.info(
        "Counting upstream barriers... (%d/%d barriers snapped, %d/%d graph nodes)",
        len(snapped_barriers),
        len(barrier_rows),
        G_barriers.number_of_nodes(),
        G.number_of_nodes(),
    )
    barrier_counts = _count_upstream_barriers(G_barriers, snap_fn, snapped_barriers)
    logger.info("  barriers: %.1fs", time.time() - t)

    obs_rows = list(db["observations"].rows)
    gbif_rows = list(db["gbif_observations"].rows)
    all_obs_pts: list[tuple[float, float]] = [
        (r["lat"], r["lng"]) for r in obs_rows if r.get("lat") and r.get("lng")
    ] + [(r["lat"], r["lng"]) for r in gbif_rows if r.get("lat") and r.get("lng")]
    t = time.time()
    logger.info("Computing observation distances... (%d obs)", len(all_obs_pts))
    obs_distances = _nearest_observation_distance(centroids, all_obs_pts)
    obs_density = _observation_density(centroids, all_obs_pts)
    logger.info("  observations: %.1fs", time.time() - t)

    t = time.time()
    logger.info("Assigning stocking events...")
    stocking_rows = list(db["stocking_records"].rows)
    stocking_map = _assign_stocking(centroids, stocking_rows)
    logger.info("  stocking: %.1fs", time.time() - t)

    t = time.time()
    logger.info("Computing confluence features...")
    is_confluence, confluence_distances = _compute_confluence_features(G, centroids)
    logger.info(
        "  confluence: %d confluence segments, %.1fs",
        sum(is_confluence.values()),
        time.time() - t,
    )

    t = time.time()
    logger.info("Computing waterbody proximity features...")
    wb_distances = _compute_waterbody_proximity(db, centroids)
    n_connected = sum(1 for v in wb_distances.values() if v is not None and v <= 200.0)
    logger.info(
        "  waterbody proximity: %d segments within 200m of water body, %.1fs",
        n_connected,
        time.time() - t,
    )

    rows = []
    for seg in segments:
        oid = seg["ogf_id"]
        lat, lng = centroids.get(oid, (None, None))
        thermal = thermal_map.get(oid, {})
        wq = wq_map.get(oid, {})
        ept = ept_map.get(oid, {})
        stocking = stocking_map.get(oid, {})

        wb_dist = wb_distances.get(oid)
        rows.append(
            {
                "ogf_id": oid,
                "centroid_lat": lat,
                "centroid_lng": lng,
                "watercourse_name": seg_name_map.get(oid, ""),
                "watercourse_type": seg_type_map.get(oid, ""),
                "stream_order": strahler.get(oid),
                "length_m": seg.get("length_m"),
                "flow_verified": bool(seg.get("flow_verified", 0)),
                "substrate_category": local_substrate.get(oid),
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
                # True = segment has a PWQMN thermal station within 15km network
                # distance; False = outside monitoring coverage (correlates with
                # Canadian Shield / northern Ontario)
                "pwqmn_coverage": oid in thermal_map,
                # Phase 3a structural features
                "is_confluence_segment": is_confluence.get(oid, False),
                "distance_to_nearest_confluence_km": confluence_distances.get(oid),
                "nearest_waterbody_distance_m": wb_dist,
                "connected_to_waterbody": wb_dist is not None and wb_dist <= 200.0,
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


# ── spatial subgraph helper ───────────────────────────────────────────────────


def _subgraph_near_sources(
    G: nx.DiGraph,
    nodes_list: list[str],
    node_lats: np.ndarray,
    node_lngs: np.ndarray,
    source_pts: list[tuple[float, float]],
    buffer_km: float,
) -> nx.DiGraph:
    """Return G.subgraph() restricted to nodes within bbox(source_pts) + buffer_km.

    Avoids running BFS across the full 300k-node graph when source points only
    cover a fraction of it (e.g. CABIN sites in southern Ontario only).
    """
    if not source_pts:
        return G

    src_lats = [p[0] for p in source_pts]
    src_lngs = [p[1] for p in source_pts]
    lat_buf = buffer_km / 111.0
    lng_buf = buffer_km / 80.5  # approx at 43°N
    mask = (
        (node_lats >= min(src_lats) - lat_buf)
        & (node_lats <= max(src_lats) + lat_buf)
        & (node_lngs >= min(src_lngs) - lng_buf)
        & (node_lngs <= max(src_lngs) + lng_buf)
    )
    included = {nodes_list[i] for i in np.where(mask)[0]}
    return G.subgraph(included)


# ── feature helpers ───────────────────────────────────────────────────────────


def _segment_centroids(segments: list[dict]) -> dict[int, tuple[float, float]]:
    """True midpoint of each LINESTRING WKT via Shapely; fallback to average for POINTs."""
    from shapely.wkt import loads as wkt_loads

    result: dict[int, tuple[float, float]] = {}
    for seg in segments:
        geom_wkt = seg.get("geom_wkt", "")
        if not geom_wkt:
            continue
        try:
            geom = wkt_loads(geom_wkt)
            if geom.geom_type == "Point":
                result[seg["ogf_id"]] = (geom.y, geom.x)
            else:
                mid = geom.interpolate(0.5, normalized=True)
                result[seg["ogf_id"]] = (mid.y, mid.x)
        except Exception:
            coords = _COORD_RE.findall(geom_wkt)
            if coords:
                lngs = [float(c[0]) for c in coords]
                lats = [float(c[1]) for c in coords]
                result[seg["ogf_id"]] = (sum(lats) / len(lats), sum(lngs) / len(lngs))
    return result


def _compute_strahler_order(G: nx.DiGraph) -> dict[int, int]:
    """Strahler stream order per segment (ogf_id).

    Deduplicates bidirectional edges from unverified-flow segments, then uses
    nx.condensation to break cycles (braided channels / OHN data errors) before
    computing topological order.  Nodes in cycles are treated as order-1 headwaters.
    """
    seen_ogf: set[int] = set()
    dag = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        ogf_id = data.get("ogf_id")
        if ogf_id is None or ogf_id in seen_ogf:
            continue
        seen_ogf.add(ogf_id)
        dag.add_edge(u, v, **data)

    # Map each ogf_id to its upstream node so we can look up order later
    ogf_upstream: dict[int, str] = {
        data["ogf_id"]: u for u, v, data in dag.edges(data=True) if "ogf_id" in data
    }

    # Condense SCCs → guaranteed DAG even when OHN has topological cycles
    cond = nx.condensation(dag)

    # Build original-node → condensed-node mapping from 'members' attribute
    node_to_cond: dict[str, int] = {}
    for cond_id in cond.nodes():
        for orig in cond.nodes[cond_id]["members"]:
            node_to_cond[orig] = cond_id

    # Compute Strahler on the condensed DAG (guaranteed cycle-free)
    topo = list(nx.topological_sort(cond))
    cond_order: dict[int, int] = {}
    for cond_node in topo:
        preds = list(cond.predecessors(cond_node))
        if not preds:
            cond_order[cond_node] = 1
        else:
            incoming = [cond_order.get(p, 1) for p in preds]
            max_o = max(incoming)
            cond_order[cond_node] = max_o + 1 if incoming.count(max_o) >= 2 else max_o

    return {
        ogf_id: cond_order.get(node_to_cond.get(u_node, -1), 1)
        for ogf_id, u_node in ogf_upstream.items()
    }


def _assign_geology(
    centroids: dict[int, tuple[float, float]],
    geology_rows: list[dict],
) -> dict[int, str]:
    """Nearest geology unit substrate_class for each segment centroid."""
    if not geology_rows or not centroids:
        return {}

    from scipy.spatial import cKDTree

    classes = [r["substrate_class"] for r in geology_rows]
    # Scale to km before building tree so lat/lng axes are comparable
    geo_coords = np.array(
        [[r["centroid_lat"] * 111.0, r["centroid_lng"] * 80.5] for r in geology_rows]
    )
    tree = cKDTree(geo_coords)

    ogf_ids = list(centroids.keys())
    seg_coords = np.array([[centroids[k][0] * 111.0, centroids[k][1] * 80.5] for k in ogf_ids])
    _, indices = tree.query(seg_coords)

    return {ogf_ids[i]: classes[indices[i]] for i in range(len(ogf_ids))}


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
        if node is None or node not in G:
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
        if node is None or node not in G:
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
    centroids: dict[int, tuple[float, float]],
    obs_latlngs: list[tuple[float, float]],
    max_km: float = _OBS_MAX_KM,
) -> dict[int, float | None]:
    """Euclidean-distance proxy from each segment centroid to nearest observation.

    Uses Euclidean (not network) distance — fast at 300km scale and sufficient
    for a pressure/sampling proxy. Network distance would be more accurate but
    is too slow across the full 300km extent with 50k source points.
    """
    if not obs_latlngs or not centroids:
        return {}

    from scipy.spatial import cKDTree

    # Scale to km so lat/lng axes are comparable (43°N: 1°lat≈111km, 1°lng≈80.5km)
    obs_arr = np.array([[lat * 111.0, lng * 80.5] for lat, lng in obs_latlngs])
    tree = cKDTree(obs_arr)

    ogf_ids = list(centroids.keys())
    seg_arr = np.array([[centroids[k][0] * 111.0, centroids[k][1] * 80.5] for k in ogf_ids])
    dists_km, _ = tree.query(seg_arr)

    return {
        ogf_ids[i]: float(dists_km[i]) if dists_km[i] <= max_km else None
        for i in range(len(ogf_ids))
    }


def _observation_density(
    centroids: dict[int, tuple[float, float]],
    obs_pts: list[tuple[float, float]],
    radius_deg: float = _OBS_DENSITY_DEG,
) -> dict[int, int]:
    """Count observations within radius_deg of each segment centroid (Euclidean)."""
    if not obs_pts:
        return {ogf_id: 0 for ogf_id in centroids}

    from scipy.spatial import cKDTree

    obs_coords = np.array([[lng, lat] for lat, lng in obs_pts])
    tree = cKDTree(obs_coords)

    ogf_ids = list(centroids.keys())
    seg_coords = np.array([[centroids[k][1], centroids[k][0]] for k in ogf_ids])
    counts = tree.query_ball_point(seg_coords, r=radius_deg, return_length=True)

    return dict(zip(ogf_ids, counts))


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


def _compute_confluence_features(
    G: nx.DiGraph,
    centroids: dict[int, tuple[float, float]],
) -> tuple[dict[int, bool], dict[int, float | None]]:
    """Detect confluence segments and compute distance to nearest confluence node.

    A confluence node has total degree >= 3 (multiple tributaries meeting).
    Uses a deduplicated DAG to avoid inflating degree from bidirectional edges.
    """
    from scipy.spatial import cKDTree

    # Deduplicate by ogf_id (same as _compute_strahler_order) to avoid counting
    # bidirectional unverified-flow edges twice at each node.
    seen_ogf: set[int] = set()
    dag = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        ogf_id = data.get("ogf_id")
        if ogf_id is None or ogf_id in seen_ogf:
            continue
        seen_ogf.add(ogf_id)
        dag.add_edge(u, v, **data)

    confluence_nodes = {
        n for n in dag.nodes() if dag.in_degree(n) + dag.out_degree(n) >= 3
    }

    # Map each ogf_id to its endpoint nodes
    ogf_to_nodes: dict[int, set[str]] = {}
    for u, v, data in dag.edges(data=True):
        ogf_id = data.get("ogf_id")
        if ogf_id is None:
            continue
        s = ogf_to_nodes.setdefault(ogf_id, set())
        s.add(u)
        s.add(v)

    is_confluence = {
        ogf_id: bool(nodes & confluence_nodes)
        for ogf_id, nodes in ogf_to_nodes.items()
    }

    if not confluence_nodes:
        return is_confluence, {ogf_id: None for ogf_id in centroids}

    # Parse confluence node coordinates ("lng,lat" format)
    conf_lats, conf_lngs = [], []
    for node in confluence_nodes:
        parts = node.split(",")
        conf_lngs.append(float(parts[0]))
        conf_lats.append(float(parts[1]))

    # Scale to km so the KDTree distance is in km
    conf_coords = np.array(
        [[lat * 111.0, lng * 80.5] for lat, lng in zip(conf_lats, conf_lngs)]
    )
    tree = cKDTree(conf_coords)

    ogf_ids = list(centroids.keys())
    seg_coords = np.array([[centroids[k][0] * 111.0, centroids[k][1] * 80.5] for k in ogf_ids])
    dists_km, _ = tree.query(seg_coords)

    confluence_distances: dict[int, float | None] = {
        ogf_ids[i]: float(dists_km[i]) for i in range(len(ogf_ids))
    }
    return is_confluence, confluence_distances


_WATERBODY_TYPES = frozenset({"pond", "lake", "reservoir", "basin", "water", "wetland"})
_WATERBODY_MAX_M = 500.0


def _compute_waterbody_proximity(
    db: Any,
    centroids: dict[int, tuple[float, float]],
) -> dict[int, float | None]:
    """Distance in metres from each segment midpoint to nearest mapped water body.

    Returns None for segments with no water body within _WATERBODY_MAX_M metres.
    """
    if "water_features" not in db.table_names():
        return {ogf_id: None for ogf_id in centroids}

    from scipy.spatial import cKDTree

    wb_rows = [
        r
        for r in db["water_features"].rows
        if r.get("feature_type") in _WATERBODY_TYPES
        and r.get("lat") is not None
        and r.get("lng") is not None
    ]
    if not wb_rows:
        return {ogf_id: None for ogf_id in centroids}

    wb_coords = np.array([[r["lat"] * 111.0, r["lng"] * 80.5] for r in wb_rows])
    tree = cKDTree(wb_coords)

    ogf_ids = list(centroids.keys())
    seg_coords = np.array([[centroids[k][0] * 111.0, centroids[k][1] * 80.5] for k in ogf_ids])

    max_km = _WATERBODY_MAX_M / 1000.0
    dists_km, _ = tree.query(seg_coords, distance_upper_bound=max_km * 1.05)

    result: dict[int, float | None] = {}
    for i, ogf_id in enumerate(ogf_ids):
        dist_km = dists_km[i]
        result[ogf_id] = float(dist_km * 1000.0) if dist_km <= max_km else None
    return result
