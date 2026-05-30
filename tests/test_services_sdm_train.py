"""Tests for the SDM training pipeline. All use synthetic data — no live DB."""

from pathlib import Path

import numpy as np
import pandas as pd

from src.services.sdm_train import (
    FEATURE_COLS,
    _all_qualifying_species,
    _confidence_tier,
    _generate_pseudo_absences,
    _get_presence_points,
    _snap_to_segments,
    slugify,
    train_all_models,
    train_species_model,
)
from src.storage.database import get_db

# ── synthetic helpers ─────────────────────────────────────────────────────────

_N = 50  # number of synthetic segments


def _make_features(n: int = _N, seed: int = 0) -> pd.DataFrame:
    """Synthetic feature matrix with the right columns for training."""
    rng = np.random.default_rng(seed)
    lats = np.linspace(43.5, 44.5, n)
    lngs = np.linspace(-80.0, -79.0, n)

    summer_temp = np.full(n, np.nan)
    summer_temp[:5] = rng.uniform(10, 20, 5)

    return pd.DataFrame(
        {
            "ogf_id": list(range(1, n + 1)),
            "centroid_lat": lats,
            "centroid_lng": lngs,
            "stream_order": rng.integers(1, 5, n),
            "length_m": rng.uniform(500, 5000, n),
            "flow_verified": rng.integers(0, 2, n),
            "substrate_category": rng.choice(["coarse", "fine", "bedrock"], n),
            "thermal_regime": np.where(np.arange(n) < 5, "coldwater", "unknown"),
            "summer_mean_temp_c": summer_temp,
            "do_median_mgl": np.where(np.arange(n) < 5, rng.uniform(6, 10, n), np.nan),
            "ph_median": np.where(np.arange(n) < 5, rng.uniform(6.5, 8.0, n), np.nan),
            "conductivity_median_us_cm": np.where(
                np.arange(n) < 5, rng.uniform(80, 200, n), np.nan
            ),
            "ept_quality": np.where(np.arange(n) < 5, "high", "unknown"),
            "ept_proportion": np.where(np.arange(n) < 5, rng.uniform(0.3, 0.8, n), np.nan),
            "barrier_count_upstream": rng.integers(0, 5, n),
            "is_stocked_within_5yr": np.zeros(n, dtype=bool),
        }
    )


_obs_id_counter = 0


def _add_obs(db, species: str, coords: list[tuple[float, float]], obscured: bool = False) -> None:
    global _obs_id_counter
    for lat, lng in coords:
        _obs_id_counter += 1
        db["observations"].insert(
            {
                "observation_id": _obs_id_counter,
                "species": species,
                "common_name": species,
                "taxon_id": 9999,
                "lat": lat,
                "lng": lng,
                "observed_on": "2024-06-01",
                "quality_grade": "research",
                "photo_url": None,
                "observer": "tester",
                "place_guess": "test",
                "jurisdiction": "CA-ON",
                "ingested_at": "2026-05-01T00:00:00",
                "geoprivacy": "obscured" if obscured else "open",
                "is_obscured": 1 if obscured else 0,
                "obscuration_radius_km": 22.0 if obscured else None,
            },
            replace=True,
        )


def _add_gbif(
    db, species: str, coords: list[tuple[float, float]], uncertainty_m: float = 100.0
) -> None:
    global _obs_id_counter
    for lat, lng in coords:
        _obs_id_counter += 1
        db["gbif_observations"].insert(
            {
                "gbif_key": _obs_id_counter + 900_000,
                "species": species,
                "common_name": species,
                "taxon_key": 8888,
                "lat": lat,
                "lng": lng,
                "observed_on": "2024-06-01",
                "country_code": "CA",
                "dataset_name": "test",
                "basis_of_record": "HUMAN_OBSERVATION",
                "coordinate_uncertainty_m": uncertainty_m,
                "jurisdiction": "CA-ON",
                "ingested_at": "2026-05-01T00:00:00",
            },
            replace=True,
        )


# ── unit tests ────────────────────────────────────────────────────────────────


def test_slugify_basic():
    assert slugify("Lepomis macrochirus") == "lepomis_macrochirus"
    assert slugify("Oncorhynchus mykiss") == "oncorhynchus_mykiss"


def test_slugify_strips_leading_trailing():
    assert slugify("  Esox lucius  ") == "esox_lucius"


def test_confidence_tier_thresholds():
    assert _confidence_tier(4) == "low"
    assert _confidence_tier(5) == "low"
    assert _confidence_tier(14) == "low"
    assert _confidence_tier(15) == "medium"
    assert _confidence_tier(49) == "medium"
    assert _confidence_tier(50) == "high"
    assert _confidence_tier(200) == "high"


def test_snap_precise_obs_within_radius():
    df = _make_features(10)
    # Place obs exactly at segment 1 centroid
    lat, lng = df.iloc[0]["centroid_lat"], df.iloc[0]["centroid_lng"]
    wmap = _snap_to_segments([(lat, lng, False)], df)
    assert 1 in wmap
    assert abs(wmap[1] - 1.0) < 1e-9


def test_snap_precise_obs_outside_radius_excluded():
    df = _make_features(10)
    # Place obs far from all centroids
    wmap = _snap_to_segments([(50.0, -60.0, False)], df)
    assert len(wmap) == 0


def test_snap_obscured_obs_distributes_weight():
    df = _make_features(50)
    # Use centroid of middle segment — obscured radius covers several neighbours
    mid = df.iloc[25]
    wmap = _snap_to_segments([(mid["centroid_lat"], mid["centroid_lng"], True)], df)
    # Weight must be distributed across multiple segments
    assert len(wmap) > 1
    # Total weight must sum to 1.0
    assert abs(sum(wmap.values()) - 1.0) < 1e-9


def test_snap_obscured_fallback_to_nearest():
    # Isolated point far from all centroids — should fall back to nearest single segment
    df = _make_features(5)
    # cKDTree query_ball_point returns [] if nothing within radius
    wmap = _snap_to_segments([(50.0, -60.0, True)], df)
    # Fallback assigns to nearest, weight=1.0
    assert len(wmap) == 1
    assert abs(list(wmap.values())[0] - 1.0) < 1e-9


def test_generate_pseudo_absences_excludes_buffer():
    df = _make_features(50)
    # Presences at first 5 segments
    presence_ids = set(df["ogf_id"].iloc[:5].tolist())
    absences = _generate_pseudo_absences(df, presence_ids, n_target=20)
    # No absence should be in the presence set
    assert not (set(absences) & presence_ids)
    assert len(absences) > 0


def test_generate_pseudo_absences_respects_cap():
    df = _make_features(50)
    presence_ids = {1}
    absences = _generate_pseudo_absences(df, presence_ids, n_target=5)
    assert len(absences) <= 5


def test_generate_pseudo_absences_empty_presence():
    df = _make_features(20)
    absences = _generate_pseudo_absences(df, set(), n_target=10)
    assert len(absences) == 10  # no exclusion zone — sample freely


# ── integration tests ─────────────────────────────────────────────────────────


def test_get_presence_points_inat_and_gbif(tmp_path: Path):
    db = get_db(tmp_path / "test.db")
    _add_obs(db, "Lepomis macrochirus", [(43.6, -79.5), (43.7, -79.4)])
    _add_gbif(db, "Lepomis macrochirus", [(43.8, -79.3)])

    pts = _get_presence_points("Lepomis macrochirus", db)
    assert len(pts) == 3
    # iNat obs are not obscured; GBIF obs are never obscured
    assert all(not obs[2] for obs in pts)


def test_get_presence_points_obscured_flagged(tmp_path: Path):
    db = get_db(tmp_path / "test.db")
    _add_obs(db, "Cottus cognatus", [(43.6, -79.5)], obscured=True)
    _add_obs(db, "Cottus cognatus", [(43.7, -79.4)], obscured=False)

    pts = _get_presence_points("Cottus cognatus", db)
    assert len(pts) == 2
    obscured_flags = [p[2] for p in pts]
    assert True in obscured_flags
    assert False in obscured_flags


def test_get_presence_points_case_insensitive(tmp_path: Path):
    db = get_db(tmp_path / "test.db")
    _add_obs(db, "LEPOMIS MACROCHIRUS", [(43.6, -79.5)])
    pts = _get_presence_points("Lepomis macrochirus", db)
    assert len(pts) == 1


def test_get_presence_points_gbif_filters_high_uncertainty(tmp_path: Path):
    db = get_db(tmp_path / "test.db")
    _add_gbif(db, "Perca flavescens", [(43.6, -79.5)], uncertainty_m=100.0)
    _add_gbif(db, "Perca flavescens", [(43.7, -79.4)], uncertainty_m=10_000.0)

    pts = _get_presence_points("Perca flavescens", db)
    assert len(pts) == 1  # high-uncertainty record excluded


def test_all_qualifying_species_combined_count(tmp_path: Path):
    db = get_db(tmp_path / "test.db")
    # 3 iNat + 3 GBIF = 6 total → qualifies at min_presence=5
    _add_obs(db, "Esox lucius", [(43.6, -79.5)] * 3)
    _add_gbif(db, "Esox lucius", [(43.7, -79.4)] * 3)
    # Only 3 total → does not qualify
    _add_obs(db, "Rare species", [(43.6, -79.5)] * 3)

    qualifying = _all_qualifying_species(db, min_presence=5)
    species_names = [s for s, _ in qualifying]
    assert "Esox lucius" in species_names
    assert "Rare species" not in species_names


def test_train_species_model_basic(tmp_path: Path):
    df = _make_features(_N)
    db = get_db(tmp_path / "test.db")
    # Place 8 obs at segment centroids 5–12
    coords = [(df.iloc[i]["centroid_lat"], df.iloc[i]["centroid_lng"]) for i in range(5, 13)]
    _add_obs(db, "Lepomis macrochirus", coords)

    meta = train_species_model(
        "Lepomis macrochirus", db=db, features_df=df, models_dir=tmp_path / "models"
    )

    assert meta is not None
    assert meta.species == "Lepomis macrochirus"
    assert meta.n_presence >= 5
    assert meta.n_pseudo_absence > 0
    assert meta.oob_score is not None
    assert 0.0 <= meta.oob_score <= 1.0
    assert meta.confidence_tier in {"high", "medium", "low"}
    # Both joblib and meta JSON files must exist
    assert (tmp_path / "models" / "lepomis_macrochirus.joblib").exists()
    assert (tmp_path / "models" / "lepomis_macrochirus_meta.json").exists()


def test_train_species_model_insufficient_data(tmp_path: Path):
    df = _make_features(_N)
    db = get_db(tmp_path / "test.db")
    # Only 3 obs — below _MIN_PRESENCE=5
    _add_obs(db, "Rare minnow", [(43.6, -79.5), (43.7, -79.4), (43.8, -79.3)])

    meta = train_species_model("Rare minnow", db=db, features_df=df, models_dir=tmp_path / "models")
    assert meta is None


def test_train_species_model_rainbow_trout_excludes_stocked(tmp_path: Path):
    df = _make_features(_N).copy()
    # Mark first 15 segments as stocked
    df.loc[df["ogf_id"] <= 15, "is_stocked_within_5yr"] = True

    db = get_db(tmp_path / "test.db")
    # 8 obs: 6 on stocked segments, 6 on non-stocked → only 6 non-stocked survive
    stocked_coords = [(df.iloc[i]["centroid_lat"], df.iloc[i]["centroid_lng"]) for i in range(6)]
    clean_coords = [(df.iloc[i]["centroid_lat"], df.iloc[i]["centroid_lng"]) for i in range(20, 26)]
    _add_obs(db, "Oncorhynchus mykiss", stocked_coords + clean_coords)

    meta = train_species_model(
        "Oncorhynchus mykiss", db=db, features_df=df, models_dir=tmp_path / "models"
    )
    assert meta is not None
    # Stocked presences were excluded — only clean presences remain
    assert meta.n_presence <= len(clean_coords)


def test_train_species_model_all_stocked_returns_none(tmp_path: Path):
    df = _make_features(_N).copy()
    df["is_stocked_within_5yr"] = True  # every segment is stocked

    db = get_db(tmp_path / "test.db")
    coords = [(df.iloc[i]["centroid_lat"], df.iloc[i]["centroid_lng"]) for i in range(10)]
    _add_obs(db, "Oncorhynchus mykiss", coords)

    meta = train_species_model(
        "Oncorhynchus mykiss", db=db, features_df=df, models_dir=tmp_path / "models"
    )
    assert meta is None


def test_train_species_model_obscured_obs_contribute(tmp_path: Path):
    df = _make_features(_N)
    db = get_db(tmp_path / "test.db")
    # 6 obscured obs — each distributes across many segments
    mid_coords = [(df.iloc[i]["centroid_lat"], df.iloc[i]["centroid_lng"]) for i in range(20, 26)]
    _add_obs(db, "Cottus cognatus", mid_coords, obscured=True)

    meta = train_species_model(
        "Cottus cognatus", db=db, features_df=df, models_dir=tmp_path / "models"
    )
    # Obscured obs distribute weight, so more segments get presence signal
    assert meta is not None
    # n_presence reflects the number of segments with non-zero weight
    assert meta.n_presence >= 6


def test_train_all_models_runs_multiple(tmp_path: Path):
    df = _make_features(_N)
    db = get_db(tmp_path / "test.db")

    for i, species in enumerate(["Lepomis macrochirus", "Perca flavescens", "Esox lucius"]):
        base = i * 10
        coords = [
            (df.iloc[j]["centroid_lat"], df.iloc[j]["centroid_lng"]) for j in range(base, base + 7)
        ]
        _add_obs(db, species, coords)

    results = train_all_models(db=db, features_df=df, models_dir=tmp_path / "models")
    assert len(results) == 3
    trained_species = {m.species for m in results}
    assert "Lepomis macrochirus" in trained_species


def test_feature_importances_cover_all_features(tmp_path: Path):
    df = _make_features(_N)
    db = get_db(tmp_path / "test.db")
    coords = [(df.iloc[i]["centroid_lat"], df.iloc[i]["centroid_lng"]) for i in range(5, 15)]
    _add_obs(db, "Semotilus atromaculatus", coords)

    meta = train_species_model(
        "Semotilus atromaculatus", db=db, features_df=df, models_dir=tmp_path / "models"
    )
    assert meta is not None
    assert set(meta.feature_names) == set(FEATURE_COLS)
    assert set(meta.feature_importances.keys()) == set(FEATURE_COLS)
    total = sum(meta.feature_importances.values())
    assert abs(total - 1.0) < 1e-6
