"""Untapped potential scoring — combines habitat, pressure, and access.

Formula per segment:
  untapped_score = habitat_score × (1 - observation_pressure) × access_modifier
                   × structural_bonus × remoteness_multiplier

Where:
  habitat_score        = mean SDM presence probability across species (0–1),
                         with a floor of 0.35 for zero-observation segments
                         that have stream_order≥3 and coarse/mixed substrate
  observation_pressure = normalised observation_density_25km (0–1)
  access_modifier      = access_score (easy_access), (1-access+0.1) (adventure),
                         or 1.0 (balanced)
  structural_bonus     = confluence and waterbody proximity multiplier (1.0–2.0)
  remoteness_multiplier = 1.5 if obs_density==0, 1.25 if 1–4, 1.0 if 5+

Result cached to data/processed/untapped_potential.parquet.
"""

import logging
import os
from pathlib import Path

import pandas as pd

from src.services.accessibility import (
    compute_access_scores,
    load_cached_crown_flags,
    load_cached_scores,
)

logger = logging.getLogger(__name__)

_PARQUET_PATH = Path("data/processed/untapped_potential.parquet")
_FEATURE_MATRIX_PATH = Path("data/processed/sdm_feature_matrix.parquet")
_KM_PER_DEGREE = 111.0


def compute_untapped_potential(
    db,
    feature_matrix: pd.DataFrame | None = None,
    species: str | None = None,
    force_recompute_access: bool = False,
    mode: str = "balanced",
) -> pd.DataFrame:
    """Compute untapped potential for all segments.

    mode options:
      "balanced"     — habitat × (1-pressure) × remoteness  (default — access ignored)
      "easy_access"  — habitat × (1-pressure) × access × remoteness  (road-accessible)
      "adventure"    — habitat × (1-pressure) × (1-access+0.1) × remoteness  (remote)

    All three scores are always computed and stored as separate columns
    (untapped_score_balanced, untapped_score_easy, untapped_score_adventure).
    The `mode` parameter determines which becomes the primary `untapped_score`
    used for sorting and agent-facing queries.

    Caches result to data/processed/untapped_potential.parquet.
    """
    if feature_matrix is None:
        if not _FEATURE_MATRIX_PATH.exists():
            raise FileNotFoundError("Feature matrix not found. Run `make build-features` first.")
        feature_matrix = pd.read_parquet(_FEATURE_MATRIX_PATH)

    # Exclude Virtual Flow segments — OHN connectivity segments through lakes,
    # not fishable stream reaches.
    if "watercourse_type" in feature_matrix.columns:
        feature_matrix = feature_matrix[
            feature_matrix["watercourse_type"] != "Virtual Flow"
        ].copy()
    elif "stream_segments" in db.table_names():
        vf_ids = {
            r["ogf_id"]
            for r in db["stream_segments"].rows_where("watercourse_type = 'Virtual Flow'")
        }
        feature_matrix = feature_matrix[~feature_matrix["ogf_id"].isin(vf_ids)].copy()

    # --- access scores ---
    access_scores = None
    if not force_recompute_access:
        access_scores = load_cached_scores()

    if access_scores is None:
        logger.info("Computing access scores (not cached)...")
        access_scores = compute_access_scores(db, feature_matrix)

    # --- habitat scores ---
    habitat_scores = _load_habitat_scores(db, species)

    # --- observation pressure ---
    pressure = _compute_pressure(feature_matrix)

    # --- merge onto feature matrix ---
    base = feature_matrix[["ogf_id", "centroid_lat", "centroid_lng", "stream_order"]].copy()

    if "watercourse_name" in feature_matrix.columns:
        base["watercourse_name"] = feature_matrix["watercourse_name"].fillna("")
    else:
        base["watercourse_name"] = ""

    if "watercourse_type" in feature_matrix.columns:
        base["watercourse_type"] = feature_matrix["watercourse_type"].fillna("")
    else:
        base["watercourse_type"] = ""

    if "observation_density_25km" in feature_matrix.columns:
        base["observation_density_25km"] = (
            feature_matrix["observation_density_25km"].fillna(0).astype(int)
        )
    else:
        base["observation_density_25km"] = 0

    # Phase 3a structural features — pass through from feature matrix if present
    _struct_cols = [
        "is_confluence_segment",
        "distance_to_nearest_confluence_km",
        "nearest_waterbody_distance_m",
        "connected_to_waterbody",
    ]
    for col in _struct_cols:
        if col in feature_matrix.columns:
            base[col] = feature_matrix[col].values
        elif col in ("is_confluence_segment", "connected_to_waterbody"):
            base[col] = False
        else:
            base[col] = float("nan")

    # Substrate category — needed for habitat floor correction
    if "substrate_category" in feature_matrix.columns:
        base["substrate_category"] = feature_matrix["substrate_category"].fillna("").values
    else:
        base["substrate_category"] = ""

    base = base.set_index("ogf_id")

    base["habitat_score"] = habitat_scores.reindex(base.index).fillna(0.0)
    base["access_score"] = access_scores.reindex(base.index).fillna(0.5)
    base["observation_pressure"] = pressure.reindex(base.index).fillna(0.0)

    # Sampling bias correction: the SDM was trained on presence records biased toward
    # accessible locations. Remote segments with good environmental features score low
    # not because habitat is poor but because they have sparse training data.
    # Floor habitat_score at 0.35 for zero-observation segments with order≥3 and
    # coarse/mixed substrate — the minimum "probably decent" signal.
    _COARSE_SUBSTRATES = {"coarse", "mixed"}
    remote_good_env = (
        (base["observation_density_25km"] == 0)
        & (base["stream_order"] >= 3)
        & (base["substrate_category"].str.lower().isin(_COARSE_SUBSTRATES))
    )
    base.loc[remote_good_env, "habitat_score"] = (
        base.loc[remote_good_env, "habitat_score"].clip(lower=0.35)
    )
    n_floored = int(remote_good_env.sum())
    logger.info(
        "Habitat floor applied to %d remote segments with coarse/mixed substrate", n_floored
    )

    # Compute all three mode scores so the map can toggle between them
    _h = base["habitat_score"]
    _p = base["observation_pressure"]
    _a = base["access_score"]
    _struct = _structural_bonus(base)
    _remote = _remoteness_multiplier(base["observation_density_25km"])

    base["untapped_score_balanced"] = _h * (1.0 - _p) * _struct * _remote
    base["untapped_score_easy"] = _h * (1.0 - _p) * _a * _struct * _remote
    base["untapped_score_adventure"] = _h * (1.0 - _p) * (1.0 - _a + 0.1) * _struct * _remote

    if mode == "adventure":
        base["untapped_score"] = base["untapped_score_adventure"]
    elif mode == "easy_access":
        base["untapped_score"] = base["untapped_score_easy"]
    else:  # balanced (default)
        base["untapped_score"] = base["untapped_score_balanced"]

    result = base.reset_index().sort_values("untapped_score", ascending=False)

    _PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(_PARQUET_PATH, index=False)
    logger.info("Untapped potential written to %s", _PARQUET_PATH)

    return result


def load_cached_untapped() -> pd.DataFrame | None:
    """Load cached untapped potential parquet, or None if not computed."""
    if not _PARQUET_PATH.exists():
        return None
    return pd.read_parquet(_PARQUET_PATH)


def find_untapped_water_for_agent(
    db,
    lat: float,
    lng: float,
    radius_km: float = 50.0,
    species: str | None = None,
    min_stream_order: int = 3,
    limit: int = 10,
    exclude_likely_culverted: bool = True,
) -> str:
    """Agent-facing function. Returns top untapped segments near lat/lng as JSON."""
    import json

    df = load_cached_untapped()
    if df is None:
        return json.dumps(
            {
                "error": "Untapped potential not computed yet.",
                "setup": "Run `make compute-untapped` to generate scores.",
            }
        )

    # Species filter: recompute habitat scores on-the-fly
    if species:
        habitat = _load_habitat_scores(db, species)
        if len(habitat) == 0:
            return json.dumps(
                {
                    "error": f"No SDM predictions found for species '{species}'.",
                    "note": "Run `make train-sdm` to train models, then `make compute-untapped`.",
                }
            )
        df = df.copy()
        df["habitat_score"] = df["ogf_id"].map(habitat).fillna(0.0)
        df["untapped_score"] = (
            df["habitat_score"] * (1.0 - df["observation_pressure"]) * df["access_score"]
        )
        df = df.sort_values("untapped_score", ascending=False)

    # Culverted stream heuristic: two-tier filter for urban/suburban areas
    culverted_filtered = False
    if exclude_likely_culverted and "observation_density_25km" in df.columns:
        # Tier 1: dense urban core — order-3 streams almost certainly engineered
        tier1 = (df["stream_order"] <= 3) & (df["observation_density_25km"] > 150)
        # Tier 2: suburban fringe — small streams in moderately developed areas
        tier2 = (df["stream_order"] <= 2) & (df["observation_density_25km"] > 50)
        mask = tier1 | tier2
        if mask.any():
            df = df[~mask].copy()
            culverted_filtered = True

    # Spatial filter
    deg = radius_km / _KM_PER_DEGREE
    df = df[
        (df["centroid_lat"].between(lat - deg, lat + deg))
        & (df["centroid_lng"].between(lng - deg, lng + deg))
    ]

    # Stream order filter
    if "stream_order" in df.columns:
        df = df[df["stream_order"] >= min_stream_order]

    df = df[df["untapped_score"] > 0.0]

    # 500m deduplication: skip segments whose centroid is within 500m of an
    # already-selected result.  Fetch extra candidates to fill the limit.
    top = _deduplicate_by_distance(df, limit=limit, min_dist_km=0.5)

    if top.empty:
        return json.dumps(
            {
                "result": (
                    f"No untapped water found within {radius_km}km with sufficient data. "
                    "Try a larger radius or run `make compute-untapped` to refresh scores."
                ),
            }
        )

    # Preload spatial data and env once
    named_seg_cache = _load_named_segments(db)
    crown_dict = _load_crown_dict()
    from dotenv import load_dotenv

    load_dotenv()
    mapbox_token = os.getenv("MAPBOX_TOKEN")

    # Build enriched segment records
    segments = []
    for _, row in top.iterrows():
        seg_lat = float(row["centroid_lat"])
        seg_lng = float(row["centroid_lng"])
        seg_name = str(row["watercourse_name"]) if row.get("watercourse_name") else None

        named_stream = _nearest_named_stream_from_cache(
            named_seg_cache, seg_lat, seg_lng, radius_km=10.0
        )
        road_access = _nearest_road_access(db, seg_lat, seg_lng, radius_km=2.0)
        osm_access = _nearest_osm_access(db, seg_lat, seg_lng, radius_km=1.0)
        top_species = _top_species_at(db, int(row["ogf_id"]))
        maps_urls = _build_maps_urls(seg_lat, seg_lng, mapbox_token)

        seg_type = str(row["watercourse_type"]) if row.get("watercourse_type") else None
        is_crown = bool(crown_dict.get(int(row["ogf_id"]), False))
        access_score_val = float(row["access_score"])
        is_conf = bool(row.get("is_confluence_segment", False))
        wb_conn = bool(row.get("connected_to_waterbody", False))
        wb_m_raw = row.get("nearest_waterbody_distance_m")
        wb_m = float(wb_m_raw) if wb_m_raw is not None and not pd.isna(wb_m_raw) else None
        conf_dist_raw = row.get("distance_to_nearest_confluence_km")
        conf_dist = (
            float(conf_dist_raw)
            if conf_dist_raw is not None and not pd.isna(conf_dist_raw)
            else None
        )

        segments.append(
            {
                "ogf_id": int(row["ogf_id"]),
                "watercourse_name": seg_name or None,
                "watercourse_type": seg_type,
                "centroid_lat": round(seg_lat, 5),
                "centroid_lng": round(seg_lng, 5),
                "stream_order": int(row["stream_order"])
                if not pd.isna(row["stream_order"])
                else None,
                "habitat_score": round(float(row["habitat_score"]), 3),
                "access_score": round(access_score_val, 3),
                "observation_pressure": round(float(row["observation_pressure"]), 3),
                "untapped_score": round(float(row["untapped_score"]), 4),
                "is_crown_land": is_crown,
                "access_note": _access_note(is_crown, access_score_val),
                "is_confluence": is_conf,
                "connected_to_waterbody": wb_conn,
                "nearest_waterbody_m": round(wb_m, 1) if wb_m is not None else None,
                "structural_note": _structural_note(is_conf, wb_conn, wb_m, conf_dist),
                "nearest_named_stream": named_stream,
                "nearest_road_access": road_access,
                "nearest_osm_access": osm_access,
                "maps_urls": maps_urls,
                "exploration_note": _exploration_note(
                    seg_name,
                    named_stream,
                    road_access,
                    osm_access,
                    float(row["habitat_score"]),
                    float(row["observation_pressure"]),
                    top_species,
                    species,
                    is_confluence=is_conf,
                    connected_to_waterbody=wb_conn,
                    nearest_waterbody_m=wb_m,
                ),
            }
        )

    output: dict = {
        "maps_note": (
            "Coordinates are stream segment midpoints. "
            "Open maps_urls.mapbox_satellite for a pre-rendered satellite image with pin — "
            "verify access and stream character before visiting."
        ),
        "segments": segments,
        "search_params": {
            "lat": lat,
            "lng": lng,
            "radius_km": radius_km,
            "species": species,
            "min_stream_order": min_stream_order,
        },
        "model_note": (
            "habitat_score is RF model-predicted habitat suitability — "
            "not confirmed presence. "
            "observation_pressure reflects iNaturalist + GBIF report density "
            "— high pressure may mean popular water, not high fish abundance. "
            "access_score reflects road proximity, park type, and tagged access points."
        ),
        "count": len(segments),
    }
    if culverted_filtered:
        output["filter_note"] = (
            "Low-order urban streams filtered (likely culverted). "
            "Use min_stream_order=2 to include them."
        )
    return json.dumps(output, indent=2)


def find_exploration_targets(
    db,
    lat: float,
    lng: float,
    radius_km: float = 50.0,
    species: str | None = None,
    mode: str = "balanced",
    min_stream_order: int = 3,
    limit: int = 5,
    enable_vision: bool = True,
    previously_shown_ogf_ids: list[int] | None = None,
) -> str:
    """Agent-facing exploration tool with mode-based scoring and rich enrichment.

    Returns top stream segments with nearby confirmed species, connectivity notes,
    habitat summary, and regulation zone.
    """
    import json

    df = load_cached_untapped()
    if df is None:
        return json.dumps(
            {
                "error": "Untapped potential not computed.",
                "setup": "Run `make compute-untapped` to generate scores.",
            }
        )

    # Species filter: recompute habitat scores on-the-fly
    if species:
        habitat = _load_habitat_scores(db, species)
        if len(habitat) == 0:
            return json.dumps(
                {
                    "error": f"No SDM predictions found for species '{species}'.",
                    "note": "Run `make train-sdm` to train models, then `make compute-untapped`.",
                }
            )
        df = df.copy()
        df["habitat_score"] = df["ogf_id"].map(habitat).fillna(0.0)

    # Recompute score from stored components based on mode
    df = df.copy()
    df["score"] = _compute_mode_score(df, mode)

    # Penalise seen-before segments: dismissed + visited trips + explicit list
    all_seen: set[int] = set(_get_seen_ogf_ids(db))
    if previously_shown_ogf_ids:
        all_seen.update(previously_shown_ogf_ids)
    if all_seen:
        seen_mask = df["ogf_id"].isin(all_seen)
        df.loc[seen_mask, "score"] = df.loc[seen_mask, "score"] * 0.3

    df = df.sort_values("score", ascending=False)

    # Spatial filter
    deg = radius_km / _KM_PER_DEGREE
    df = df[
        (df["centroid_lat"].between(lat - deg, lat + deg))
        & (df["centroid_lng"].between(lng - deg, lng + deg))
    ]

    # Stream order filter
    if "stream_order" in df.columns:
        df = df[df["stream_order"] >= min_stream_order]

    df = df[df["score"] > 0.0]

    top = _deduplicate_by_distance(df, limit=limit, min_dist_km=0.5)

    if top.empty:
        return json.dumps(
            {
                "result": (
                    f"No targets found within {radius_km}km with mode='{mode}'. "
                    "Try a larger radius or different mode."
                )
            }
        )

    # Vision pre-screening: verify open water, detect culverts and blocked access
    candidates = top.to_dict("records")
    if enable_vision:
        from src.services.vision_screening import screen_candidates

        candidates = screen_candidates(candidates, max_screens=10)
        if not candidates:
            return json.dumps(
                {
                    "result": (
                        f"No targets found within {radius_km}km after satellite vision screening. "
                        "Try a larger radius or run with enable_vision=False to skip screening."
                    )
                }
            )

    named_seg_cache = _load_named_segments(db)
    habitat_features = _load_habitat_features([int(c["ogf_id"]) for c in candidates])
    crown_dict = _load_crown_dict()

    from dotenv import load_dotenv

    load_dotenv()
    mapbox_token = os.getenv("MAPBOX_TOKEN")

    from src.services.regulations import _estimate_fmz

    segments = []
    for row in candidates:
        seg_lat = float(row["centroid_lat"])
        seg_lng = float(row["centroid_lng"])
        seg_name = str(row["watercourse_name"]) if row.get("watercourse_name") else None

        named_stream_10km = _nearest_named_stream_from_cache(
            named_seg_cache, seg_lat, seg_lng, radius_km=10.0
        )
        named_stream_3km = _nearest_named_stream_from_cache(
            named_seg_cache, seg_lat, seg_lng, radius_km=3.0
        )
        road_access = _nearest_road_access(db, seg_lat, seg_lng, radius_km=2.0)
        osm_access = _nearest_osm_access(db, seg_lat, seg_lng, radius_km=1.0)
        top_sp = _top_species_at(db, int(row["ogf_id"]))

        nearby_species = _nearby_confirmed_species(db, seg_lat, seg_lng, radius_km=5.0)
        connectivity_note = _build_connectivity_note(seg_name, named_stream_3km, nearby_species)
        hab_feat = habitat_features.get(int(row["ogf_id"]), {})
        habitat_summary = _habitat_summary(hab_feat)

        fmz = _estimate_fmz(seg_lat, seg_lng)
        regulation_zone = (
            f"FMZ {fmz} — check regulations before keeping fish." if fmz else None
        )
        maps_urls = _build_maps_urls(seg_lat, seg_lng, mapbox_token)
        seg_type = str(row["watercourse_type"]) if row.get("watercourse_type") else None
        is_crown = bool(crown_dict.get(int(row["ogf_id"]), False))
        access_score_val = float(row["access_score"])
        is_conf = bool(row.get("is_confluence_segment") or False)
        wb_conn = bool(row.get("connected_to_waterbody") or False)
        wb_m_raw = row.get("nearest_waterbody_distance_m")
        wb_m = float(wb_m_raw) if wb_m_raw is not None and not pd.isna(wb_m_raw) else None
        conf_dist_raw = row.get("distance_to_nearest_confluence_km")
        conf_dist = (
            float(conf_dist_raw)
            if conf_dist_raw is not None and not pd.isna(conf_dist_raw)
            else None
        )

        vision_screening = row.get(
            "vision_screening", {"screened": False, "verdict": "unverified"}
        )

        expl_note = _exploration_note(
            seg_name,
            named_stream_10km,
            road_access,
            osm_access,
            float(row["habitat_score"]),
            float(row["observation_pressure"]),
            top_sp,
            species,
            is_confluence=is_conf,
            connected_to_waterbody=wb_conn,
            nearest_waterbody_m=wb_m,
        )
        if vision_screening.get("is_culvert_crossing"):
            expl_note += (
                " Culvert crossing detected — check both sides of the road "
                "for outlet pools where fish stack."
            )
        if vision_screening.get("is_golf_course"):
            expl_note += (
                " Golf course detected in imagery — likely private property. "
                "Verify public access before visiting."
            )
        elif vision_screening.get("access_blocked_by_structures"):
            expl_note += (
                " Adjacent structures visible — access may be limited to road allowance only."
            )

        segments.append(
            {
                "ogf_id": int(row["ogf_id"]),
                "watercourse_name": seg_name or None,
                "watercourse_type": seg_type,
                "centroid_lat": round(seg_lat, 5),
                "centroid_lng": round(seg_lng, 5),
                "stream_order": int(row["stream_order"])
                if not pd.isna(row["stream_order"])
                else None,
                "habitat_score": round(float(row["habitat_score"]), 3),
                "access_score": round(access_score_val, 3),
                "observation_pressure": round(float(row["observation_pressure"]), 3),
                "score": round(float(row["score"]), 4),
                "mode": mode,
                "is_crown_land": is_crown,
                "access_note": _access_note(is_crown, access_score_val),
                "is_confluence": is_conf,
                "connected_to_waterbody": wb_conn,
                "nearest_waterbody_m": round(wb_m, 1) if wb_m is not None else None,
                "structural_note": _structural_note(is_conf, wb_conn, wb_m, conf_dist),
                "nearby_confirmed_species": nearby_species,
                "connectivity_note": connectivity_note,
                "habitat_summary": habitat_summary,
                "regulation_zone": regulation_zone,
                "nearest_named_stream": named_stream_10km,
                "nearest_road_access": road_access,
                "nearest_osm_access": osm_access,
                "maps_urls": maps_urls,
                "exploration_note": expl_note,
                "vision_screening": vision_screening,
            }
        )

    return json.dumps(
        {
            "mode": mode,
            "segments": segments,
            "search_params": {
                "lat": lat,
                "lng": lng,
                "radius_km": radius_km,
                "species": species,
                "min_stream_order": min_stream_order,
            },
            "model_note": (
                "habitat_score is RF model-predicted habitat suitability — not confirmed presence. "
                "nearby_confirmed_species comes from iNaturalist + GBIF within 5km — "
                "not necessarily from this specific stream reach. "
                "connectivity_note is inferred from stream proximity, not confirmed by survey data."
            ),
            "count": len(segments),
        },
        indent=2,
    )


# ── selection helpers ─────────────────────────────────────────────────────────


def _deduplicate_by_distance(
    df: pd.DataFrame, limit: int, min_dist_km: float
) -> pd.DataFrame:
    """Return up to `limit` rows from df (already sorted best-first) such that
    no two selected centroids are within min_dist_km of each other."""
    selected_rows = []
    selected_coords: list[tuple[float, float]] = []

    # Pull enough candidates from the sorted frame to fill the limit
    candidates = df.head(limit * 20)

    for _, row in candidates.iterrows():
        lat = float(row["centroid_lat"])
        lng = float(row["centroid_lng"])
        # Euclidean degree distance as fast pre-filter (1 deg ≈ 111km)
        threshold_deg = min_dist_km / _KM_PER_DEGREE
        too_close = any(
            abs(lat - s_lat) < threshold_deg and abs(lng - s_lng) < threshold_deg
            and _haversine_km(lat, lng, s_lat, s_lng) < min_dist_km
            for s_lat, s_lng in selected_coords
        )
        if not too_close:
            selected_rows.append(row)
            selected_coords.append((lat, lng))
            if len(selected_rows) == limit:
                break

    if not selected_rows:
        return pd.DataFrame(columns=df.columns)
    return pd.DataFrame(selected_rows)


# ── enrichment helpers ────────────────────────────────────────────────────────

_BEARING_LABELS = [
    "north",
    "northeast",
    "east",
    "southeast",
    "south",
    "southwest",
    "west",
    "northwest",
]


def _bearing_label(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> str:
    import math

    dlat = to_lat - from_lat
    dlng = to_lng - from_lng
    angle = math.degrees(math.atan2(dlng, dlat)) % 360
    idx = int((angle + 22.5) / 45) % 8
    return _BEARING_LABELS[idx]


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math

    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2  # noqa: E501
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


_POINT_RE = __import__("re").compile(r"POINT \((-?\d+\.?\d*) (-?\d+\.?\d*)\)")


def _parse_point(geom_wkt: str) -> tuple[float, float] | None:
    """Parse 'POINT (lng lat)' → (lat, lng) or None."""
    m = _POINT_RE.match(geom_wkt or "")
    if m:
        return float(m.group(2)), float(m.group(1))
    return None


def _load_named_segments(db) -> list[tuple[str, float, float]]:
    """Load all named OHN segments as (name, lat, lng) tuples."""
    if "stream_segments" not in db.table_names():
        return []
    rows = list(db["stream_segments"].rows_where("name IS NOT NULL AND name != ''"))
    result = []
    for r in rows:
        coords = _parse_point(r.get("geom_wkt", ""))
        if coords:
            result.append((r["name"], coords[0], coords[1]))
    return result


def _nearest_named_stream_from_cache(
    cache: list[tuple[str, float, float]], lat: float, lng: float, radius_km: float
) -> str | None:
    """Return 'StreamName (Xkm)' for nearest named segment within radius_km."""
    if not cache:
        return None
    deg = radius_km / _KM_PER_DEGREE
    best_dist = float("inf")
    best_name = None
    for name, r_lat, r_lng in cache:
        if abs(r_lat - lat) > deg or abs(r_lng - lng) > deg:
            continue
        d = _haversine_km(lat, lng, r_lat, r_lng)
        if d < best_dist:
            best_dist = d
            best_name = name
    if best_name is None:
        return None
    return f"{best_name} ({best_dist:.1f}km)"


def _nearest_road_access(db, lat: float, lng: float, radius_km: float) -> str | None:
    """Return 'Road Xm bearing' for nearest road/parking within radius_km."""
    if "access_points" not in db.table_names():
        return None
    deg = radius_km / _KM_PER_DEGREE
    rows = list(
        db["access_points"].rows_where(
            "access_type IN ('road', 'parking') AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
            [lat - deg, lat + deg, lng - deg, lng + deg],
        )
    )
    if not rows:
        return None
    best = min(rows, key=lambda r: _haversine_km(lat, lng, r["lat"], r["lng"]))
    dist_km = _haversine_km(lat, lng, best["lat"], best["lng"])
    bearing = _bearing_label(lat, lng, best["lat"], best["lng"])
    label = "Parking area" if best["access_type"] == "parking" else "Road"
    if dist_km < 1.0:
        return f"{label} {int(dist_km * 1000)}m {bearing}"
    return f"{label} {dist_km:.1f}km {bearing}"


def _nearest_osm_access(db, lat: float, lng: float, radius_km: float) -> str | None:
    """Return description of nearest fishing spot / boat launch / conservation area."""
    if "access_points" not in db.table_names():
        return None
    deg = radius_km / _KM_PER_DEGREE
    rows = list(
        db["access_points"].rows_where(
            "access_type IN ('fishing_spot', 'boat_launch', 'conservation_area', 'park') "
            "AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
            [lat - deg, lat + deg, lng - deg, lng + deg],
        )
    )
    if not rows:
        return None
    best = min(rows, key=lambda r: _haversine_km(lat, lng, r["lat"], r["lng"]))
    dist_km = _haversine_km(lat, lng, best["lat"], best["lng"])
    labels = {
        "fishing_spot": "Fishing spot",
        "boat_launch": "Boat launch",
        "conservation_area": "Conservation area",
        "park": "Park",
    }
    label = labels.get(best["access_type"], best["access_type"].replace("_", " ").title())
    if dist_km < 1.0:
        return f"{label} {int(dist_km * 1000)}m"
    return f"{label} {dist_km:.1f}km"


def _top_species_at(db, ogf_id: int) -> list[str]:
    """Return top 2 species by predicted probability for this segment."""
    if "sdm_predictions" not in db.table_names():
        return []
    rows = list(
        db["sdm_predictions"].rows_where(
            "ogf_id = ? ORDER BY presence_probability DESC LIMIT 2", [ogf_id]
        )
    )
    return [_COMMON_NAMES.get(r["species"], r["species"]) for r in rows]


def _exploration_note(
    seg_name: str | None,
    named_stream: str | None,
    road_access: str | None,
    osm_access: str | None,
    habitat_score: float,
    pressure: float,
    top_species: list[str],
    filter_species: str | None,
    is_confluence: bool = False,
    connected_to_waterbody: bool = False,
    nearest_waterbody_m: float | None = None,
) -> str:
    parts = []

    # Lead with structural features when present
    stream_ref = seg_name or (named_stream.split("(")[0].strip() if named_stream else None)
    if is_confluence and stream_ref:
        parts.append(
            f"Confluence point on {stream_ref} — check the pool below the junction."
        )
    elif is_confluence:
        parts.append("Confluence point — check the pool below the junction.")
    elif connected_to_waterbody and nearest_waterbody_m is not None:
        parts.append(
            f"Creek connects to water body {int(nearest_waterbody_m)}m away "
            "— fish likely stacking at the transition."
        )

    # Water identity (if not already led with structural)
    if not is_confluence and not (connected_to_waterbody and nearest_waterbody_m is not None):
        if seg_name:
            parts.append(f"{seg_name}.")
        elif named_stream:
            parts.append(f"Unnamed tributary near {named_stream.split('(')[0].strip()}.")
        else:
            parts.append("Unnamed stream segment.")

    # Habitat signal
    if filter_species:
        if habitat_score >= 0.6:
            parts.append(f"Strong predicted habitat for {filter_species}.")
        elif habitat_score >= 0.35:
            parts.append(f"Moderate predicted habitat for {filter_species}.")
        else:
            parts.append(f"Low predicted habitat for {filter_species}.")
    elif top_species:
        sp_str = " and ".join(top_species[:2])
        if habitat_score >= 0.6:
            parts.append(f"Strong predicted habitat ({sp_str}).")
        elif habitat_score >= 0.35:
            parts.append(f"Moderate predicted habitat ({sp_str}).")
        else:
            parts.append(f"Low predicted habitat ({sp_str}).")

    # Access
    if road_access:
        parts.append(f"{road_access}.")
    if osm_access:
        parts.append(f"{osm_access} nearby.")

    # Pressure
    if pressure < 0.15:
        parts.append("Very low observation pressure — likely underexplored.")
    elif pressure < 0.35:
        parts.append("Low fishing pressure.")
    elif pressure < 0.6:
        parts.append("Moderate observation pressure.")
    else:
        parts.append("High observation density in this area — popular water.")

    parts.append(
        "Verify before visiting: open mapbox_satellite for a pre-rendered satellite image "
        "with pin, google or bing to explore the surroundings. "
        "In Ontario: swoop_2025 shows 16cm leaf-off aerial imagery — best for confirming "
        "stream channel and bank access."
    )
    return " ".join(parts)


# ── internal ──────────────────────────────────────────────────────────────────


def _load_crown_dict() -> dict[int, bool]:
    """Load is_crown_land flags as a plain dict for O(1) per-segment lookup."""
    flags = load_cached_crown_flags()
    if flags is None:
        return {}
    return {int(k): bool(v) for k, v in flags.items()}


def _access_note(is_crown_land: bool, access_score: float) -> str:
    """Generate a human-readable access note based on crown land status and access score."""
    if is_crown_land:
        return (
            "Crown land — public access generally permitted for fishing. "
            "Verify no specific restrictions."
        )
    if access_score < 0.3:
        return (
            "⚠️ Access not verified — segment may cross private land. "
            "Check Ontario Crown Land map at geohub.lio.gov.on.ca before visiting. "
            "Low road access + private land = trespassing risk."
        )
    return "Road or park access nearby — verify public right of way."


def _remoteness_multiplier(observation_density: pd.Series) -> pd.Series:
    """Bonus for genuinely unexplored water based on observation density in 25km radius.

    0 observations  → 1.5× (zero crowdsourced records = genuinely unexplored)
    1–4 observations → 1.25× (sparse = likely undersampled, not fishless)
    5+ observations  → 1.0× (sufficient sampling, no bonus)
    """
    mult = pd.Series(1.0, index=observation_density.index, dtype=float)
    mult[observation_density == 0] = 1.5
    mult[(observation_density > 0) & (observation_density < 5)] = 1.25
    return mult


def _structural_bonus(df: pd.DataFrame) -> pd.Series:
    """Multiplicative bonus for structural fish congregation features. Capped at 2.0."""
    import numpy as np

    bonus = pd.Series(1.0, index=df.index, dtype=float)

    if "is_confluence_segment" in df.columns:
        is_conf = df["is_confluence_segment"].fillna(False).astype(bool)
        bonus += np.where(is_conf, 0.4, 0.0)

        if "distance_to_nearest_confluence_km" in df.columns:
            dist = df["distance_to_nearest_confluence_km"].fillna(float("inf"))
            near_conf = (~is_conf) & (dist < 0.5)
            bonus += np.where(near_conf, 0.2, 0.0)

    if "connected_to_waterbody" in df.columns:
        is_wb = df["connected_to_waterbody"].fillna(False).astype(bool)
        bonus += np.where(is_wb, 0.3, 0.0)

    return bonus.clip(upper=2.0)


def _structural_note(
    is_confluence: bool,
    connected_to_waterbody: bool,
    nearest_waterbody_m: float | None,
    distance_to_nearest_confluence_km: float | None,
) -> str:
    """One-sentence structural congregation note for a stream segment."""
    if is_confluence:
        return (
            "Confluence point — multiple streams meet here. "
            "High fish congregation probability."
        )
    if connected_to_waterbody and nearest_waterbody_m is not None:
        return (
            f"Stream connects to nearby water body within {int(nearest_waterbody_m)}m "
            "— likely pool or pond where fish stack."
        )
    if distance_to_nearest_confluence_km is not None and distance_to_nearest_confluence_km < 0.5:
        return "Within 500m of a stream confluence — fish often hold in this zone."
    return "No structural features detected from mapped data — verify on satellite view."


def _compute_mode_score(df: pd.DataFrame, mode: str) -> pd.Series:
    """Return untapped scores for each row based on mode, structural bonus, and remoteness."""
    h = df["habitat_score"]
    p = df["observation_pressure"]
    a = df["access_score"]
    if mode == "adventure":
        base = h * (1.0 - p) * (1.0 - a + 0.1)
    elif mode == "balanced":
        base = h * (1.0 - p)
    else:  # easy_access
        base = h * (1.0 - p) * a

    # Default density to 5 (no remoteness bonus) when column is absent
    density = (
        df["observation_density_25km"]
        if "observation_density_25km" in df.columns
        else pd.Series(5, index=df.index, dtype=float)
    )
    return base * _structural_bonus(df) * _remoteness_multiplier(density)


def _nearby_confirmed_species(db, lat: float, lng: float, radius_km: float = 5.0) -> list[str]:
    """Return top 5 species (by record count) from iNat + GBIF within radius_km."""
    from collections import Counter

    deg = radius_km / _KM_PER_DEGREE
    counter: Counter = Counter()
    for table in ("observations", "gbif_observations"):
        if table not in db.table_names():
            continue
        rows = list(
            db[table].rows_where(
                "lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                [lat - deg, lat + deg, lng - deg, lng + deg],
            )
        )
        for r in rows:
            name = r.get("common_name") or r.get("species")
            if name:
                counter[name] += 1
    return [sp for sp, _ in counter.most_common(5)]


def _build_connectivity_note(
    seg_name: str | None,
    named_stream_3km: str | None,
    nearby_species: list[str],
) -> str | None:
    """Generate a note when a named stream within 3km has confirmed nearby species."""
    if named_stream_3km is None or not nearby_species:
        return None
    stream_label = named_stream_3km.split("(")[0].strip()
    sp_str = ", ".join(nearby_species[:3])
    return (
        f"Connected to {stream_label} where {sp_str} have been confirmed — "
        "tributary may hold the same species via natural dispersal."
    )


def _load_habitat_features(ogf_ids: list[int]) -> dict[int, dict]:
    """Load thermal_regime, substrate_category, ept_quality from the feature matrix."""
    if not _FEATURE_MATRIX_PATH.exists():
        return {}
    try:
        fm = pd.read_parquet(
            _FEATURE_MATRIX_PATH,
            columns=["ogf_id", "thermal_regime", "substrate_category", "ept_quality"],
        )
        fm = fm[fm["ogf_id"].isin(set(ogf_ids))]
        return {int(r["ogf_id"]): r.to_dict() for _, r in fm.iterrows()}
    except Exception:
        return {}


def _habitat_summary(feat: dict) -> str:
    """One-sentence habitat description from thermal regime, substrate, and EPT quality."""
    thermal = feat.get("thermal_regime") or ""
    substrate = feat.get("substrate_category") or ""
    ept = feat.get("ept_quality") or ""
    parts = []
    if thermal and thermal not in ("unknown", ""):
        parts.append(f"{thermal} thermal regime")
    if substrate and substrate not in ("unknown", ""):
        parts.append(f"{substrate} substrate")
    if ept and ept not in ("unknown", ""):
        parts.append(f"{ept} EPT quality")
    if not parts:
        return "Habitat features not measured at this location — field verification needed."
    return " · ".join(parts) + "."


def _build_maps_urls(lat: float, lng: float, mapbox_token: str | None) -> dict[str, str]:
    """Return a dict of satellite map links for a coordinate pair."""
    raw: dict[str, str | None] = {
        "mapbox_satellite": (
            f"https://api.mapbox.com/styles/v1/"
            f"mapbox/satellite-v9/static/"
            f"pin-s+ff0000({lng:.5f},{lat:.5f})/"
            f"{lng:.5f},{lat:.5f},16,0/800x500"
            f"?access_token={mapbox_token}"
        )
        if mapbox_token
        else None,
        "google_satellite": f"https://maps.google.com/?q={lat:.5f},{lng:.5f}&t=k&z=18",
        "bing_satellite": f"https://www.bing.com/maps?cp={lat:.5f}~{lng:.5f}&lvl=18&style=a",
        "swoop_2025": (
            f"https://geohub.lio.gov.on.ca/datasets/"
            f"lio::south-western-ontario-"
            f"orthophotography-project-swoop-"
            f"2025-1km-index/"
            f"explore?location={lat:.5f},{lng:.5f},16"
        )
        if (-83 < lng < -76 and 42 < lat < 46)
        else None,
    }
    return {k: v for k, v in raw.items() if v is not None}


def _load_habitat_scores(db, species: str | None) -> pd.Series:
    """Load SDM predictions from DB, averaged per segment across species (or one species)."""
    if "sdm_predictions" not in db.table_names():
        return pd.Series(dtype=float)

    if species:
        # Resolve common → scientific name
        sci = _resolve_species(species)
        rows = list(
            db["sdm_predictions"].rows_where(
                "LOWER(species) = ?", [sci.lower() if sci else species.lower()]
            )
        )
    else:
        rows = list(db["sdm_predictions"].rows)

    if not rows:
        return pd.Series(dtype=float)

    df = pd.DataFrame(rows)
    # Average presence probability across species per segment
    habitat = df.groupby("ogf_id")["presence_probability"].mean()
    return habitat


def _compute_pressure(feature_matrix: pd.DataFrame) -> pd.Series:
    """Normalise observation_density_25km to [0, 1] using log scale.

    Log normalization compresses the urban/rural gap: a 100× density difference
    (rural=5 vs urban=500) becomes ~3× on log scale, giving rural segments more
    credit for their genuinely low pressure instead of treating them as near-zero.
    """
    import numpy as np

    col = feature_matrix.set_index("ogf_id")["observation_density_25km"].fillna(0.0)
    log_density = np.log1p(col)
    log_max = float(log_density.max())
    if log_max > 0:
        return (log_density / log_max).rename("observation_pressure")
    return col.clip(0.0, 1.0).rename("observation_pressure")


# Species name resolution (mirrors sdm_predictions.py)
_COMMON_NAMES = {
    "Semotilus atromaculatus": "Creek Chub",
    "Lepomis gibbosus": "Pumpkinseed",
    "Perca flavescens": "Yellow Perch",
    "Ameiurus nebulosus": "Brown Bullhead",
    "Catostomus commersonii": "White Sucker",
    "Culaea inconstans": "Brook Stickleback",
    "Etheostoma caeruleum": "Rainbow Darter",
    "Ambloplites rupestris": "Rock Bass",
    "Micropterus nigricans": "Smallmouth / Largemouth Bass (pooled)",
}
_COMMON_TO_SCI = {v.lower(): k for k, v in _COMMON_NAMES.items()}
for _k in list(_COMMON_NAMES.keys()):
    _COMMON_TO_SCI[_k.lower()] = _k


def _resolve_species(name: str) -> str:
    return _COMMON_TO_SCI.get(name.lower(), name)


# ── seen-before helpers ───────────────────────────────────────────────────────

_SNAP_RADIUS_KM = 0.5  # 500m — trip location must be this close to snap to a segment


def _snap_trips_to_segments(db) -> list[int]:
    """Snap trip lat/lng locations to the nearest OHN segment centroid within 500m."""
    if "trips" not in db.table_names():
        return []
    trips = list(db["trips"].rows_where("lat IS NOT NULL AND lng IS NOT NULL"))
    if not trips:
        return []
    if not _FEATURE_MATRIX_PATH.exists():
        return []

    import numpy as np
    from scipy.spatial import cKDTree

    try:
        fm = pd.read_parquet(
            _FEATURE_MATRIX_PATH,
            columns=["ogf_id", "centroid_lat", "centroid_lng"],
        )
        fm = fm.dropna(subset=["centroid_lat", "centroid_lng"])
    except Exception:
        return []

    if fm.empty:
        return []

    ogf_ids = fm["ogf_id"].tolist()
    coords = np.array(
        [
            [lat * 111.0, lng * 80.5]
            for lat, lng in zip(fm["centroid_lat"], fm["centroid_lng"])
        ]
    )
    tree = cKDTree(coords)

    seen = []
    for trip in trips:
        q = np.array([[float(trip["lat"]) * 111.0, float(trip["lng"]) * 80.5]])
        dist_km, idx = tree.query(q)
        if dist_km[0] <= _SNAP_RADIUS_KM:
            seen.append(ogf_ids[idx[0]])
    return seen


def _get_seen_ogf_ids(db) -> list[int]:
    """Return ogf_ids that should receive the seen-before score penalty.

    Combines explicitly dismissed segments and trip-log locations snapped to
    the nearest OHN segment.
    """
    seen: set[int] = set()

    if "dismissed_segments" in db.table_names():
        for row in db["dismissed_segments"].rows:
            seen.add(int(row["ogf_id"]))

    seen.update(_snap_trips_to_segments(db))
    return list(seen)
