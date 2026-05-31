"""Phase 2c: Random Forest species distribution models — training pipeline.

Train-flow:
  prepare_species_data  → presence (X, y)
  generate_pseudo_absences → absence ogf_ids (target-group sampling)
  train_species_model   → calibrated RF + spatial block CV AUC
  predict_all_segments  → Series[ogf_id → probability]
"""

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

logger = logging.getLogger(__name__)

_MODELS_DIR = Path("data/processed/sdm_models")
_PARQUET_PATH = Path("data/processed/sdm_feature_matrix.parquet")
_SNAP_RADIUS_DEG = 0.09  # ~10 km — max snap distance for occurrence records
_KM_PER_DEGREE = 111.0
_MAX_GBIF_UNCERTAINTY_M = 5_000
MODEL_VERSION = "2c-v1"

# M. nigricans and M. salmoides are treated as one SDM target (pooled)
_BASS_POOL = frozenset(["Micropterus nigricans", "Micropterus salmoides"])

# Species for which stocking is a genuine training-data confound.
# Stocked fish are planted at accessible put-and-take sites, not selected for
# habitat suitability — training on those presences models stocking logistics,
# not habitat. Non-salmonid species are never stocked at scale in Ontario and
# do not need this filter.
STOCKING_CONFOUND_SPECIES = frozenset(
    [
        "Oncorhynchus mykiss",  # Rainbow Trout — 3.67M stocked, 187 ON sites (2021-25)
        "Salvelinus fontinalis",  # Brook Trout
        "Salmo trutta",  # Brown Trout
        "Oncorhynchus tshawytscha",  # Chinook Salmon
        "Oncorhynchus kisutch",  # Coho Salmon
        "Salvelinus namaycush",  # Lake Trout
    ]
)

_CATEGORICAL_FEATURES = ["substrate_category", "thermal_regime", "ept_quality"]
_NUMERIC_FEATURES = [
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
    # Phase 3a: structural features
    "is_confluence_segment",
    "distance_to_nearest_confluence_km",
    "nearest_waterbody_distance_m",
    "connected_to_waterbody",
]
_ALL_FEATURES = _NUMERIC_FEATURES + _CATEGORICAL_FEATURES

# Eight clean-signal species + pooled Micropterus
SPECIES_TO_TRAIN = [
    "Semotilus atromaculatus",  # Creek Chub
    "Lepomis gibbosus",  # Pumpkinseed
    "Perca flavescens",  # Yellow Perch
    "Ameiurus nebulosus",  # Brown Bullhead
    "Catostomus commersonii",  # White Sucker
    "Culaea inconstans",  # Brook Stickleback
    "Etheostoma caeruleum",  # Rainbow Darter
    "Ambloplites rupestris",  # Rock Bass
    "Micropterus nigricans",  # Smallmouth + Largemouth bass (pooled via _BASS_POOL)
]


# ── public API ────────────────────────────────────────────────────────────────


def prepare_species_data(
    species_name: str,
    db,
    feature_matrix: pd.DataFrame,
    stocking_exclusion: bool = True,
) -> tuple[pd.DataFrame, pd.Series]:
    """Load occurrences, snap to OHN segments, return (X, y) presence rows.

    X is a DataFrame indexed by ogf_id with _ALL_FEATURES columns.
    y is a Series of 1.0 presence labels indexed by ogf_id.

    For Micropterus salmoides/nigricans, pools records from both names.

    Stocking exclusion: only applied when stocking_exclusion=True AND the
    species is in STOCKING_CONFOUND_SPECIES (salmonids with large-scale
    put-and-take stocking programs). For all other species the parameter is
    ignored — stocked sites are valid habitat observations for non-salmonids.
    """
    query_names = list(_BASS_POOL) if species_name in _BASS_POOL else [species_name]

    coords: list[tuple[float, float]] = []
    for name in query_names:
        s_lower = name.lower()
        for r in db["observations"].rows_where("LOWER(species) = ?", [s_lower], select="lat, lng"):
            if r["lat"] is not None and r["lng"] is not None:
                coords.append((float(r["lat"]), float(r["lng"])))
        for r in db["gbif_observations"].rows_where(
            "LOWER(species) = ? AND "
            "(coordinate_uncertainty_m IS NULL OR coordinate_uncertainty_m <= ?)",
            [s_lower, _MAX_GBIF_UNCERTAINTY_M],
            select="lat, lng",
        ):
            if r["lat"] is not None and r["lng"] is not None:
                coords.append((float(r["lat"]), float(r["lng"])))

    empty = pd.DataFrame(columns=_ALL_FEATURES), pd.Series(dtype=float)
    if not coords:
        return empty

    # Snap to nearest segment
    fm_coords = feature_matrix[["centroid_lat", "centroid_lng"]].values
    fm_ids = feature_matrix["ogf_id"].values
    tree = cKDTree(fm_coords)
    dists, idxs = tree.query(np.array(coords), k=1)

    snapped: set[int] = set()
    for dist, idx in zip(dists, idxs):
        if dist <= _SNAP_RADIUS_DEG:
            snapped.add(int(fm_ids[idx]))

    if not snapped:
        return empty

    if stocking_exclusion and species_name in STOCKING_CONFOUND_SPECIES:
        stocked = set(feature_matrix.loc[feature_matrix["is_stocked_within_5yr"], "ogf_id"])
        snapped -= stocked

    if not snapped:
        return empty

    X = _extract_features(feature_matrix[feature_matrix["ogf_id"].isin(snapped)])
    y = pd.Series(np.ones(len(X), dtype=float), index=X.index, name="presence")
    return X, y


def generate_pseudo_absences(
    presence_segments: list[int],
    feature_matrix: pd.DataFrame,
    db,
    ratio: int = 5,
    min_network_distance_km: float = 10.0,
) -> list[int]:
    """Target-group pseudo-absence sampling.

    Samples from segments where any fish was observed in iNat or GBIF but NOT
    the target species. Excludes segments within min_network_distance_km
    (Euclidean proxy) of any confirmed presence.
    """
    all_obs: list[tuple[float, float]] = []
    for row in db.execute(
        "SELECT lat, lng FROM observations WHERE lat IS NOT NULL AND lng IS NOT NULL"
    ).fetchall():
        all_obs.append((float(row[0]), float(row[1])))
    for row in db.execute(
        "SELECT lat, lng FROM gbif_observations "
        "WHERE lat IS NOT NULL AND lng IS NOT NULL "
        "AND (coordinate_uncertainty_m IS NULL OR coordinate_uncertainty_m <= ?)",
        (_MAX_GBIF_UNCERTAINTY_M,),
    ).fetchall():
        all_obs.append((float(row[0]), float(row[1])))

    if not all_obs:
        return []

    fm_coords = feature_matrix[["centroid_lat", "centroid_lng"]].values
    fm_ids = feature_matrix["ogf_id"].values
    tree = cKDTree(fm_coords)

    dists, idxs = tree.query(np.array(all_obs), k=1)
    background: set[int] = set()
    for dist, idx in zip(dists, idxs):
        if dist <= _SNAP_RADIUS_DEG:
            background.add(int(fm_ids[idx]))

    # Exclude target-species presences
    target_set = set(presence_segments)
    candidates = background - target_set
    if not candidates:
        return []

    # Apply minimum-distance buffer around presences (Euclidean proxy)
    pres_mask = feature_matrix["ogf_id"].isin(target_set)
    pres_coords = feature_matrix.loc[pres_mask, ["centroid_lat", "centroid_lng"]].values

    if len(pres_coords) > 0:
        pres_tree = cKDTree(pres_coords)
        cand_mask = feature_matrix["ogf_id"].isin(candidates)
        cand_df = feature_matrix.loc[cand_mask, ["ogf_id", "centroid_lat", "centroid_lng"]]
        min_dist_deg = min_network_distance_km / _KM_PER_DEGREE
        near_dists, _ = pres_tree.query(cand_df[["centroid_lat", "centroid_lng"]].values, k=1)
        eligible_ids = cand_df["ogf_id"].values[near_dists > min_dist_deg]
    else:
        eligible_ids = feature_matrix.loc[
            feature_matrix["ogf_id"].isin(candidates), "ogf_id"
        ].values

    if len(eligible_ids) == 0:
        return []

    n_target = len(presence_segments) * ratio
    n_sample = min(n_target, len(eligible_ids))
    rng = np.random.default_rng(42)
    return rng.choice(eligible_ids, size=n_sample, replace=False).tolist()


def train_species_model(
    species_name: str,
    db,
    feature_matrix: pd.DataFrame,
) -> dict:
    """Train a calibrated Random Forest SDM for one species.

    Returns a dict with:
      species, n_presence, n_pseudo_absence, spatial_cv_auc,
      feature_importances, n_inat, n_gbif, model (CalibratedClassifierCV)
    """
    X_pres, y_pres = prepare_species_data(species_name, db, feature_matrix)
    n_presence = len(X_pres)
    if n_presence < 5:
        raise ValueError(
            f"Insufficient presence data for {species_name}: {n_presence} snapped records"
        )

    presence_ogf_ids = X_pres.index.tolist()
    absence_ogf_ids = generate_pseudo_absences(presence_ogf_ids, feature_matrix, db)
    if not absence_ogf_ids:
        raise ValueError(f"No pseudo-absence segments generated for {species_name}")

    X_abs = _extract_features(feature_matrix[feature_matrix["ogf_id"].isin(absence_ogf_ids)])
    y_abs = pd.Series(np.zeros(len(X_abs), dtype=float), index=X_abs.index)

    X_all = pd.concat([X_pres, X_abs])
    y_all = pd.concat([y_pres, y_abs]).values

    # Spatial block CV for AUC estimate
    spatial_cv_auc = _spatial_block_cv(X_all, y_all, X_all.index.tolist(), feature_matrix)

    # Final calibrated model on all data
    base = _build_base_pipeline()
    calibrated = CalibratedClassifierCV(base, cv=3, method="isotonic")
    calibrated.fit(X_all, y_all)

    # Feature importances from a separate full-data base fit (avoids OHE shape
    # mismatch when CalibratedClassifierCV's cv folds see different category sets)
    base_for_imp = _build_base_pipeline()
    base_for_imp.fit(X_all, y_all)

    n_inat, n_gbif = _count_records(species_name, db)

    return {
        "species": species_name,
        "n_presence": n_presence,
        "n_pseudo_absence": len(absence_ogf_ids),
        "spatial_cv_auc": float(spatial_cv_auc),
        "feature_importances": _importances_from_pipeline(base_for_imp),
        "n_inat": n_inat,
        "n_gbif": n_gbif,
        "model": calibrated,
    }


def predict_all_segments(
    model_result: dict,
    feature_matrix: pd.DataFrame,
) -> pd.Series:
    """Run model on all segments. Returns Series[ogf_id → probability 0.0–1.0]."""
    model = model_result["model"]
    X = feature_matrix.set_index("ogf_id")[_ALL_FEATURES].copy()
    _cast_bool_cols(X)
    proba = model.predict_proba(X)[:, 1]
    return pd.Series(proba, index=X.index, name="presence_probability")


def save_model(model_result: dict, models_dir: Path | None = None) -> Path:
    """Persist a trained model dict to joblib. Returns the saved path."""
    mdir = models_dir or _MODELS_DIR
    mdir.mkdir(parents=True, exist_ok=True)
    slug = model_result["species"].lower().replace(" ", "_")
    path = mdir / f"{slug}.joblib"
    joblib.dump(model_result, path)
    return path


def load_model(species_name: str, models_dir: Path | None = None) -> dict | None:
    """Load a previously saved model dict. Returns None if not found."""
    mdir = models_dir or _MODELS_DIR
    slug = species_name.lower().replace(" ", "_")
    path = mdir / f"{slug}.joblib"
    if not path.exists():
        return None
    return joblib.load(path)


# ── internal helpers ──────────────────────────────────────────────────────────


def _extract_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return feature-only DataFrame indexed by ogf_id with bool cols cast to float."""
    X = df.set_index("ogf_id")[_ALL_FEATURES].copy()
    _cast_bool_cols(X)
    return X


def _cast_bool_cols(df: pd.DataFrame) -> None:
    """Cast bool columns to float in-place so sklearn imputers work correctly."""
    bool_cols = [
        "flow_verified",
        "is_stocked_within_5yr",
        "pwqmn_coverage",
        "is_confluence_segment",
        "connected_to_waterbody",
    ]
    for col in bool_cols:
        if col in df.columns and df[col].dtype == bool:
            df[col] = df[col].astype(float)


def _build_base_pipeline() -> Pipeline:
    num_transformer = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    cat_transformer = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    preprocessor = ColumnTransformer(
        [
            ("num", num_transformer, _NUMERIC_FEATURES),
            ("cat", cat_transformer, _CATEGORICAL_FEATURES),
        ]
    )
    return Pipeline(
        [
            ("preprocessor", preprocessor),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=200,
                    max_features="sqrt",
                    min_samples_leaf=5,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )


def _spatial_block_cv(
    X: pd.DataFrame,
    y: np.ndarray,
    ogf_ids: list[int],
    feature_matrix: pd.DataFrame,
) -> float:
    """4-fold spatial block CV using NW/NE/SW/SE quadrants of the training bounding box."""
    fm_idx = feature_matrix.set_index("ogf_id")[["centroid_lat", "centroid_lng"]]
    try:
        coords = fm_idx.loc[ogf_ids]
    except KeyError:
        return 0.5

    lats = coords["centroid_lat"].values
    lngs = coords["centroid_lng"].values
    lat_mid = (lats.max() + lats.min()) / 2
    lng_mid = (lngs.max() + lngs.min()) / 2

    # 0=NW, 1=NE, 2=SW, 3=SE
    quadrants = np.where(
        lats >= lat_mid,
        np.where(lngs < lng_mid, 0, 1),
        np.where(lngs < lng_mid, 2, 3),
    )

    aucs = []
    for fold in range(4):
        test_mask = quadrants == fold
        train_mask = ~test_mask
        if test_mask.sum() < 5 or train_mask.sum() < 10:
            continue
        if y[test_mask].sum() == 0 or (1.0 - y[test_mask]).sum() == 0:
            continue
        try:
            pipe = _build_base_pipeline()
            pipe.fit(X.iloc[train_mask], y[train_mask])
            proba = pipe.predict_proba(X.iloc[test_mask])[:, 1]
            aucs.append(float(roc_auc_score(y[test_mask], proba)))
        except Exception as exc:
            logger.debug("Spatial CV fold %d failed: %s", fold, exc)

    return float(np.mean(aucs)) if aucs else 0.5


def _importances_from_pipeline(pipeline: Pipeline) -> dict[str, float]:
    """Extract RF feature importances from a fitted pipeline, aggregating OHE columns."""
    raw_names = pipeline.named_steps["preprocessor"].get_feature_names_out()
    importances = pipeline.named_steps["clf"].feature_importances_

    result: dict[str, float] = {}
    for fname, imp in zip(raw_names, importances):
        _, orig = fname.split("__", 1)
        base = orig
        for cat in _CATEGORICAL_FEATURES:
            if orig == cat or orig.startswith(cat + "_"):
                base = cat
                break
        result[base] = result.get(base, 0.0) + float(imp)

    return result


def _count_records(species_name: str, db) -> tuple[int, int]:
    names = list(_BASS_POOL) if species_name in _BASS_POOL else [species_name]
    n_inat = n_gbif = 0
    for name in names:
        s = name.lower()
        row = db.execute(
            "SELECT COUNT(*) FROM observations WHERE LOWER(species) = ?", (s,)
        ).fetchone()
        n_inat += row[0] if row else 0
        row = db.execute(
            "SELECT COUNT(*) FROM gbif_observations WHERE LOWER(species) = ?", (s,)
        ).fetchone()
        n_gbif += row[0] if row else 0
    return n_inat, n_gbif
