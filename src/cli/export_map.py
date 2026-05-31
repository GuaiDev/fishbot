"""Export map data for the Leaflet UI.

Reads untapped_potential.parquet + sdm_feature_matrix.parquet, runs SDM predictions
on the filtered set, and writes data/processed/map_data.json as a GeoJSON
FeatureCollection of segment centroids.

Only segments within 100 km of home (Oakville, ON) are included, capped at 50 000.
"""

import json
import logging
import math
import os
from pathlib import Path

import joblib
import pandas as pd

logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

HOME_LAT = 43.4675
HOME_LNG = -79.6877
HOME_RADIUS_KM = 100.0
MAX_SEGMENTS = 50_000

_UNTAPPED_PATH = Path("data/processed/untapped_potential.parquet")
_FEATURE_MATRIX_PATH = Path("data/processed/sdm_feature_matrix.parquet")
_MODELS_DIR = Path("data/processed/sdm_models")
_OUTPUT_PATH = Path("data/processed/map_data.json")
_HTML_TEMPLATE = Path("src/map/index.html")
_HTML_OUTPUT = Path("data/processed/map_index.html")

# Feature columns expected by models in data/processed/sdm_models/ (sdm_training.py pipeline).
# The CalibratedClassifierCV pipeline handles its own preprocessing — we pass a
# DataFrame indexed by ogf_id with exactly these columns.
ALL_FEATURES = [
    "stream_order",
    "length_m",
    "flow_verified",
    "summer_mean_temp_c",
    "do_median_mgl",
    "ph_median",
    "conductivity_median_us_cm",
    "ept_proportion",
    "barrier_count_upstream",
    "distance_to_nearest_observation_km",
    "observation_density_25km",
    "is_stocked_within_5yr",
    "pwqmn_coverage",
    "is_confluence_segment",
    "distance_to_nearest_confluence_km",
    "nearest_waterbody_distance_m",
    "connected_to_waterbody",
    "substrate_category",
    "thermal_regime",
    "ept_quality",
]

COMMON_NAMES = {
    "Semotilus atromaculatus": "Creek Chub",
    "Lepomis gibbosus": "Pumpkinseed",
    "Perca flavescens": "Yellow Perch",
    "Ameiurus nebulosus": "Brown Bullhead",
    "Catostomus commersonii": "White Sucker",
    "Culaea inconstans": "Brook Stickleback",
    "Etheostoma caeruleum": "Rainbow Darter",
    "Ambloplites rupestris": "Rock Bass",
    "Micropterus nigricans": "Smallmouth Bass",
    "Lepomis macrochirus": "Bluegill",
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "_")


def _load_model(slug: str):
    """Return the CalibratedClassifierCV model or None."""
    path = _MODELS_DIR / f"{slug}.joblib"
    if not path.exists():
        return None
    bundle = joblib.load(path)
    return bundle.get("model")


def _run_predictions(features_df: pd.DataFrame) -> pd.DataFrame:
    """Run all available models and return top-2 species per segment.

    Models in data/processed/sdm_models/ are CalibratedClassifierCV pipelines
    that expect a DataFrame indexed by ogf_id with ALL_FEATURES columns.

    Returns a DataFrame indexed by ogf_id with columns top1_species, top1_prob,
    top2_species, top2_prob.
    """
    # Build X once — index by ogf_id, fill any missing columns with 0.
    available = [c for c in ALL_FEATURES if c in features_df.columns]
    missing = [c for c in ALL_FEATURES if c not in features_df.columns]
    if missing:
        logger.warning("Feature matrix missing columns (will fill 0): %s", missing)

    X = features_df.set_index("ogf_id")[available].copy()
    for col in missing:
        X[col] = 0
    X = X[ALL_FEATURES]  # enforce column order

    all_preds: dict[str, pd.Series] = {}

    for slug_path in sorted(_MODELS_DIR.glob("*.joblib")):
        slug = slug_path.stem
        sci = next((k for k in COMMON_NAMES if _slugify(k) == slug), None)
        common = (
            COMMON_NAMES.get(sci, slug.replace("_", " ").title())
            if sci
            else slug.replace("_", " ").title()
        )
        model = _load_model(slug)
        if model is None:
            continue
        try:
            proba = model.predict_proba(X)[:, 1]
            all_preds[common] = pd.Series(proba, index=X.index)
        except Exception as exc:
            logger.warning("Prediction failed for %s: %s", common, exc)

    if not all_preds:
        return pd.DataFrame(
            {"top1_species": "", "top1_prob": 0.0, "top2_species": "", "top2_prob": 0.0},
            index=features_df["ogf_id"],
        )

    pred_df = pd.DataFrame(all_preds)  # rows=ogf_id, cols=species

    n_species = pred_df.shape[1]
    sorted_idx = pred_df.values.argsort(axis=1)
    top1_idx = sorted_idx[:, -1]
    top2_idx = sorted_idx[:, -2] if n_species >= 2 else sorted_idx[:, -1]
    cols = pred_df.columns.tolist()

    return pd.DataFrame(
        {
            "ogf_id": pred_df.index,
            "top1_species": [cols[i] for i in top1_idx],
            "top1_prob": [
                round(float(pred_df.values[r, top1_idx[r]]), 3) for r in range(len(pred_df))
            ],
            "top2_species": [cols[i] for i in top2_idx],
            "top2_prob": [
                round(float(pred_df.values[r, top2_idx[r]]), 3) for r in range(len(pred_df))
            ],
        }
    ).set_index("ogf_id")


# ── main export ───────────────────────────────────────────────────────────────


def export_map_data(output_path: Path = _OUTPUT_PATH) -> dict:
    """Build and write map_data.json. Returns summary stats."""
    logger.info("Loading untapped potential...")
    untapped = pd.read_parquet(_UNTAPPED_PATH)

    # Filter to home radius
    dists = [
        _haversine_km(HOME_LAT, HOME_LNG, row.centroid_lat, row.centroid_lng)
        for row in untapped.itertuples()
    ]
    untapped = untapped.copy()
    untapped["_dist_km"] = dists
    untapped = untapped[untapped["_dist_km"] <= HOME_RADIUS_KM].drop(columns=["_dist_km"])

    # Sort by untapped_score descending, cap at MAX_SEGMENTS
    untapped = untapped.sort_values("untapped_score", ascending=False).head(MAX_SEGMENTS)

    logger.info("Loading feature matrix for SDM predictions...")
    features = pd.read_parquet(_FEATURE_MATRIX_PATH)
    features_filtered = features[features["ogf_id"].isin(untapped["ogf_id"])].copy()

    logger.info("Running SDM predictions on %d segments...", len(features_filtered))
    predictions = _run_predictions(features_filtered)

    # Build GeoJSON features
    geojson_features = []
    for row in untapped.itertuples():
        ogf_id = row.ogf_id
        pred = predictions.loc[ogf_id] if ogf_id in predictions.index else None

        lat = float(row.centroid_lat)
        lng = float(row.centroid_lng)

        props = {
            "ogf_id": int(ogf_id) if ogf_id == ogf_id else None,
            "untapped_score": round(float(row.untapped_score), 4),
            "habitat_score": round(float(row.habitat_score), 4),
            "access_score": round(float(row.access_score), 4),
            "stream_order": int(row.stream_order) if row.stream_order == row.stream_order else None,
            "watercourse_name": str(row.watercourse_name)
            if row.watercourse_name and str(row.watercourse_name) != "nan"
            else None,
            "nearest_named_stream": None,  # not in parquet; placeholder
            "is_confluence_segment": bool(row.is_confluence_segment),
            "connected_to_waterbody": bool(row.connected_to_waterbody),
            "observation_pressure": round(float(row.observation_pressure), 4),
            "top1_species": pred["top1_species"] if pred is not None else None,
            "top1_prob": pred["top1_prob"] if pred is not None else None,
            "top2_species": pred["top2_species"] if pred is not None else None,
            "top2_prob": pred["top2_prob"] if pred is not None else None,
            "google_maps_url": f"https://www.google.com/maps/@{lat},{lng},16z/data=!3m1!1e3",
            "swoop_url": f"https://maps.ontario.ca/swoop/#13/{lat}/{lng}",
        }

        geojson_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": props,
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "features": geojson_features,
        "metadata": {
            "home_lat": HOME_LAT,
            "home_lng": HOME_LNG,
            "radius_km": HOME_RADIUS_KM,
            "segment_count": len(geojson_features),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(geojson, separators=(",", ":")))

    size_mb = output_path.stat().st_size / 1_048_576
    logger.info("Wrote %d features to %s (%.1f MB)", len(geojson_features), output_path, size_mb)

    # Inject Mapbox token into a ready-to-open HTML copy
    mapbox_token = os.environ.get("MAPBOX_TOKEN", "")
    if not mapbox_token and Path(".env").exists():
        for line in Path(".env").read_text().splitlines():
            if line.startswith("MAPBOX_TOKEN="):
                mapbox_token = line.split("=", 1)[1].strip()
                break

    html_out: Path | None = None
    if mapbox_token and _HTML_TEMPLATE.exists():
        html_content = _HTML_TEMPLATE.read_text().replace("%%MAPBOX_TOKEN%%", mapbox_token)
        _HTML_OUTPUT.write_text(html_content)
        html_out = _HTML_OUTPUT
        logger.info("HTML ready at %s", _HTML_OUTPUT)
    else:
        logger.warning("No MAPBOX_TOKEN found — HTML not written. Set MAPBOX_TOKEN in .env.")

    return {
        "segments": len(geojson_features),
        "size_mb": round(size_mb, 1),
        "path": str(output_path),
        "html": str(html_out) if html_out else None,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stats = export_map_data()
    print(f"\nExported {stats['segments']:,} segments → {stats['path']} ({stats['size_mb']} MB)")
    if stats.get("html"):
        print(f"Open in browser: {stats['html']}")
