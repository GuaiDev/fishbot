"""Random Forest species distribution model — training pipeline."""

import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from src.models.sdm_result import SDMModelMeta
from src.services.sdm_features import build_feature_matrix
from src.storage.database import get_db

logger = logging.getLogger(__name__)

_MODELS_DIR = Path("data/models")
_MIN_PRESENCE = 5
_PSEUDO_ABSENCE_RATIO = 10
_PSEUDO_ABSENCE_CAP = 10_000
_SNAP_RADIUS_DEG = 0.09  # ~10 km — max snap distance for precise obs
_OBSCURED_RADIUS_DEG = 0.198  # ~22 km — iNat obscuration radius
_EXCLUSION_RADIUS_DEG = 0.045  # ~5 km — pseudo-absence buffer around presences
_MAX_GBIF_UNCERTAINTY_M = 5_000  # skip GBIF records with uncertainty > 5 km
_RAINBOW_TROUT = "Oncorhynchus mykiss"

_NUMERICAL_COLS = [
    "stream_order",
    "length_m",
    "flow_verified",
    "summer_mean_temp_c",
    "do_median_mgl",
    "ph_median",
    "conductivity_median_us_cm",
    "ept_proportion",
    "barrier_count_upstream",
]
_CATEGORICAL_COLS = ["substrate_category", "thermal_regime", "ept_quality"]

# Canonical order used by the ColumnTransformer (cat first, then num).
# sdm_predict imports this constant — do not reorder without updating both.
FEATURE_COLS = _NUMERICAL_COLS + _CATEGORICAL_COLS


# ── public API ────────────────────────────────────────────────────────────────


def train_species_model(
    species: str,
    db=None,
    features_df: pd.DataFrame | None = None,
    models_dir: Path | None = None,
) -> SDMModelMeta | None:
    """Train and persist a Random Forest SDM for one species.

    Returns SDMModelMeta on success, None if there is insufficient data.
    """
    if db is None:
        db = get_db()
    if features_df is None:
        features_df = build_feature_matrix(db)
    mdir = models_dir or _MODELS_DIR
    mdir.mkdir(parents=True, exist_ok=True)

    # Collect + snap presence points
    points = _get_presence_points(species, db)
    if len(points) < _MIN_PRESENCE:
        logger.debug("%s: %d raw presence points — skipping", species, len(points))
        return None

    weight_map = _snap_to_segments(points, features_df)

    # Rainbow Trout: exclude stocked-site presences (stocking confound)
    if species.lower() == _RAINBOW_TROUT.lower():
        stocked_ids = set(features_df.loc[features_df["is_stocked_within_5yr"], "ogf_id"])
        weight_map = {oid: w for oid, w in weight_map.items() if oid not in stocked_ids}

    if len(weight_map) < _MIN_PRESENCE:
        logger.debug(
            "%s: %d snapped presences after filtering — skipping", species, len(weight_map)
        )
        return None

    # Build presence training rows
    pres_df = features_df[features_df["ogf_id"].isin(weight_map.keys())].copy()
    pres_weights = np.array([weight_map[oid] for oid in pres_df["ogf_id"]])

    # Generate pseudo-absences
    n_target = min(len(weight_map) * _PSEUDO_ABSENCE_RATIO, _PSEUDO_ABSENCE_CAP)
    absence_ids = _generate_pseudo_absences(features_df, set(weight_map.keys()), n_target)
    if not absence_ids:
        logger.warning("%s: no pseudo-absences generated", species)
        return None
    abs_df = features_df[features_df["ogf_id"].isin(absence_ids)].copy()
    abs_weights = np.ones(len(abs_df))

    # Assemble training data
    X = pd.concat([pres_df[FEATURE_COLS], abs_df[FEATURE_COLS]], ignore_index=True)
    y = np.concatenate([np.ones(len(pres_df)), np.zeros(len(abs_df))])
    sample_weights = np.concatenate([pres_weights, abs_weights])

    # Fit preprocessor + classifier
    preprocessor = _build_preprocessor()
    X_tr = preprocessor.fit_transform(X)

    clf = RandomForestClassifier(
        n_estimators=200,
        oob_score=True,
        class_weight="balanced",
        n_jobs=-1,
        random_state=42,
    )
    clf.fit(X_tr, y, sample_weight=sample_weights)

    # Feature importances: ColumnTransformer outputs cat columns first, then num
    feat_order = _CATEGORICAL_COLS + _NUMERICAL_COLS
    importances = dict(zip(feat_order, clf.feature_importances_.tolist()))

    # Persist model bundle
    slug = slugify(species)
    model_path = mdir / f"{slug}.joblib"
    joblib.dump(
        {"preprocessor": preprocessor, "clf": clf, "feature_cols": FEATURE_COLS},
        model_path,
    )

    oob = float(clf.oob_score_) if hasattr(clf, "oob_score_") else None
    meta = SDMModelMeta(
        species=species,
        species_slug=slug,
        n_presence=len(pres_df),
        n_pseudo_absence=len(abs_df),
        oob_score=oob,
        feature_names=FEATURE_COLS,
        feature_importances=importances,
        training_date=datetime.now(),
        model_path=str(model_path),
        confidence_tier=_confidence_tier(len(pres_df)),
    )
    meta_path = mdir / f"{slug}_meta.json"
    meta_path.write_text(meta.model_dump_json(indent=2))

    logger.info(
        "Trained %s: %d presence, %d absence, OOB=%.3f, tier=%s",
        species,
        len(pres_df),
        len(abs_df),
        oob or 0.0,
        meta.confidence_tier,
    )
    return meta


def train_all_models(
    db=None,
    features_df: pd.DataFrame | None = None,
    min_presence: int = _MIN_PRESENCE,
    models_dir: Path | None = None,
) -> list[SDMModelMeta]:
    """Train RF models for every species with enough occurrence data."""
    if db is None:
        db = get_db()
    if features_df is None:
        features_df = build_feature_matrix(db)

    qualifying = _all_qualifying_species(db, min_presence)
    logger.info("Training SDMs for %d qualifying species", len(qualifying))

    results = []
    for species, _ in qualifying:
        meta = train_species_model(species, db=db, features_df=features_df, models_dir=models_dir)
        if meta is not None:
            results.append(meta)
    return results


# ── helpers (exported for tests) ─────────────────────────────────────────────


def slugify(species: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", species.lower()).strip("_")


def _confidence_tier(n_presence: int) -> str:
    if n_presence >= 50:
        return "high"
    if n_presence >= 15:
        return "medium"
    return "low"


def _all_qualifying_species(db, min_presence: int) -> list[tuple[str, int]]:
    """Return (canonical_species, count) pairs where combined count >= min_presence."""
    counts: dict[str, int] = defaultdict(int)
    canonical: dict[str, str] = {}

    for species_name, n in db.execute(
        "SELECT species, COUNT(*) FROM observations WHERE species != '' GROUP BY LOWER(species)"
    ).fetchall():
        key = species_name.lower()
        counts[key] += n
        canonical.setdefault(key, species_name)

    for species_name, n in db.execute(
        "SELECT species, COUNT(*) FROM gbif_observations "
        "WHERE species != '' "
        "AND (coordinate_uncertainty_m IS NULL OR coordinate_uncertainty_m <= ?) "
        "GROUP BY LOWER(species)",
        (_MAX_GBIF_UNCERTAINTY_M,),
    ).fetchall():
        key = species_name.lower()
        counts[key] += n
        canonical.setdefault(key, species_name)

    return [(canonical[k], n) for k, n in counts.items() if n >= min_presence]


def _get_presence_points(species: str, db) -> list[tuple[float, float, bool]]:
    """Return (lat, lng, is_obscured) for all presence records of this species."""
    s_lower = species.lower()
    points: list[tuple[float, float, bool]] = []

    for r in db["observations"].rows_where(
        "LOWER(species) = ?", [s_lower], select="lat, lng, is_obscured"
    ):
        points.append((r["lat"], r["lng"], bool(r["is_obscured"])))

    for r in db["gbif_observations"].rows_where(
        "LOWER(species) = ? AND "
        "(coordinate_uncertainty_m IS NULL OR coordinate_uncertainty_m <= ?)",
        [s_lower, _MAX_GBIF_UNCERTAINTY_M],
        select="lat, lng",
    ):
        points.append((r["lat"], r["lng"], False))

    return points


def _snap_to_segments(
    points: list[tuple[float, float, bool]],
    features_df: pd.DataFrame,
) -> dict[int, float]:
    """Map presence observations to segment IDs with cumulative weights.

    Precise points snap to nearest segment within _SNAP_RADIUS_DEG.
    Obscured points distribute weight 1/n_candidates across all segments
    within _OBSCURED_RADIUS_DEG (iNat soft-label approach).
    """
    coords = features_df[["centroid_lat", "centroid_lng"]].values
    ogf_ids = features_df["ogf_id"].values
    tree = cKDTree(coords)
    weight_map: dict[int, float] = defaultdict(float)

    for lat, lng, is_obscured in points:
        if is_obscured:
            idxs = tree.query_ball_point([lat, lng], _OBSCURED_RADIUS_DEG)
            if not idxs:
                _, idx = tree.query([lat, lng])
                idxs = [idx]
            w = 1.0 / len(idxs)
            for idx in idxs:
                weight_map[int(ogf_ids[idx])] += w
        else:
            dist, idx = tree.query([lat, lng])
            if dist <= _SNAP_RADIUS_DEG:
                weight_map[int(ogf_ids[idx])] += 1.0

    return dict(weight_map)


def _generate_pseudo_absences(
    features_df: pd.DataFrame,
    presence_ogf_ids: set[int],
    n_target: int,
    rng: np.random.Generator | None = None,
) -> list[int]:
    """Sample background pseudo-absences from segments outside the presence buffer."""
    if rng is None:
        rng = np.random.default_rng(42)

    pres_mask = features_df["ogf_id"].isin(presence_ogf_ids)
    pres_coords = features_df.loc[pres_mask, ["centroid_lat", "centroid_lng"]].values
    all_coords = features_df[["centroid_lat", "centroid_lng"]].values
    all_ids = features_df["ogf_id"].values

    if len(pres_coords) > 0:
        dists, _ = cKDTree(pres_coords).query(all_coords, k=1)
        eligible_mask = (dists > _EXCLUSION_RADIUS_DEG) & (~pres_mask.values)
    else:
        eligible_mask = ~pres_mask.values

    eligible_ids = all_ids[eligible_mask]
    if len(eligible_ids) == 0:
        return []

    n_sample = min(n_target, len(eligible_ids))
    return rng.choice(eligible_ids, size=n_sample, replace=False).tolist()


def _build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
                        (
                            "encode",
                            OrdinalEncoder(
                                handle_unknown="use_encoded_value",
                                unknown_value=-1,
                            ),
                        ),
                    ]
                ),
                _CATEGORICAL_COLS,
            ),
            ("num", SimpleImputer(strategy="median"), _NUMERICAL_COLS),
        ],
        remainder="drop",
    )
