"""Tests for the SDM training pipeline (Phase 2c).

All tests use synthetic data — no live DB required.
No model accuracy assertions — outputs are data-dependent.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.services.sdm_training import (
    _ALL_FEATURES,
    generate_pseudo_absences,
    predict_all_segments,
    prepare_species_data,
    train_species_model,
)
from src.storage.database import get_db

# ── synthetic helpers ─────────────────────────────────────────────────────────

_N = 80  # number of synthetic segments


def _make_features(n: int = _N, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    lats = np.linspace(43.2, 44.8, n)
    lngs = np.linspace(-80.5, -78.5, n)

    summer_temp = np.full(n, np.nan)
    summer_temp[:10] = rng.uniform(10, 22, 10)

    df = pd.DataFrame(
        {
            "ogf_id": list(range(1, n + 1)),
            "centroid_lat": lats,
            "centroid_lng": lngs,
            "stream_order": rng.integers(1, 5, n),
            "length_m": rng.uniform(300, 8000, n),
            "flow_verified": rng.integers(0, 2, n).astype(bool),
            "substrate_category": rng.choice(["coarse", "fine", "bedrock", "organic"], n),
            "thermal_regime": np.where(np.arange(n) < 10, "coldwater", "unknown"),
            "summer_mean_temp_c": summer_temp,
            "do_median_mgl": np.where(np.arange(n) < 10, rng.uniform(6, 10, n), np.nan),
            "ph_median": np.where(np.arange(n) < 10, rng.uniform(6.5, 8.0, n), np.nan),
            "conductivity_median_us_cm": np.where(
                np.arange(n) < 10, rng.uniform(80, 200, n), np.nan
            ),
            "ept_quality": np.where(np.arange(n) < 10, "high", "unknown"),
            "ept_proportion": np.where(np.arange(n) < 10, rng.uniform(0.3, 0.8, n), np.nan),
            "barrier_count_upstream": rng.integers(0, 5, n),
            "distance_to_nearest_observation_km": rng.uniform(0.5, 30, n),
            "observation_density_25km": rng.integers(0, 20, n),
            "is_stocked_within_5yr": np.zeros(n, dtype=bool),
            "pwqmn_coverage": np.zeros(n, dtype=bool),
            # Phase 3a structural features
            "is_confluence_segment": np.zeros(n, dtype=bool),
            "distance_to_nearest_confluence_km": rng.uniform(0.1, 5.0, n),
            "nearest_waterbody_distance_m": np.where(
                np.arange(n) < 5, rng.uniform(50, 450, n), np.nan
            ),
            "connected_to_waterbody": np.where(np.arange(n) < 5, True, False),
        }
    )
    return df


_obs_counter = 0


def _add_obs(db, species: str, coords: list[tuple[float, float]]) -> None:
    global _obs_counter
    for lat, lng in coords:
        _obs_counter += 1
        db["observations"].insert(
            {
                "observation_id": _obs_counter,
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
                "geoprivacy": "open",
                "is_obscured": 0,
                "obscuration_radius_km": None,
            },
            replace=True,
        )


def _add_gbif(db, species: str, coords: list[tuple[float, float]]) -> None:
    global _obs_counter
    for lat, lng in coords:
        _obs_counter += 1
        db["gbif_observations"].insert(
            {
                "gbif_key": _obs_counter + 500_000,
                "species": species,
                "common_name": species,
                "taxon_key": 8888,
                "lat": lat,
                "lng": lng,
                "observed_on": "2024-06-01",
                "country_code": "CA",
                "dataset_name": "test",
                "basis_of_record": "HUMAN_OBSERVATION",
                "coordinate_uncertainty_m": 100.0,
                "jurisdiction": "CA-ON",
                "ingested_at": "2026-05-01T00:00:00",
            },
            replace=True,
        )


def _coords_at(df: pd.DataFrame, indices: list[int]) -> list[tuple[float, float]]:
    return [(df.iloc[i]["centroid_lat"], df.iloc[i]["centroid_lng"]) for i in indices]


# ── prepare_species_data ──────────────────────────────────────────────────────


def test_prepare_species_data_loads_presence_records(tmp_path: Path):
    df = _make_features()
    db = get_db(tmp_path / "test.db")
    _add_obs(db, "Semotilus atromaculatus", _coords_at(df, range(5, 15)))

    X, y = prepare_species_data("Semotilus atromaculatus", db, df)

    assert len(X) > 0
    assert (y == 1.0).all()
    assert set(X.columns) == set(_ALL_FEATURES)
    assert X.index.name == "ogf_id"


def test_prepare_species_data_combines_inat_and_gbif(tmp_path: Path):
    df = _make_features()
    db = get_db(tmp_path / "test.db")
    _add_obs(db, "Perca flavescens", _coords_at(df, range(5, 10)))  # 5 iNat
    _add_gbif(db, "Perca flavescens", _coords_at(df, range(20, 25)))  # 5 GBIF

    X, y = prepare_species_data("Perca flavescens", db, df)

    # Up to 10 unique segments (some might snap to same segment)
    assert len(X) >= 5


def test_prepare_species_data_stocking_exclusion(tmp_path: Path):
    df = _make_features().copy()
    df.loc[df["ogf_id"] <= 15, "is_stocked_within_5yr"] = True
    db = get_db(tmp_path / "test.db")

    # Observations on stocked segments + clean segments
    stocked_coords = _coords_at(df, range(0, 8))
    clean_coords = _coords_at(df, range(30, 38))
    _add_obs(db, "Oncorhynchus mykiss", stocked_coords + clean_coords)

    X_with, _ = prepare_species_data("Oncorhynchus mykiss", db, df, stocking_exclusion=True)
    X_without, _ = prepare_species_data("Oncorhynchus mykiss", db, df, stocking_exclusion=False)

    # Exclusion should produce fewer presences
    assert len(X_with) < len(X_without)
    # No stocked segments in result
    assert not any(df.loc[df["ogf_id"].isin(X_with.index), "is_stocked_within_5yr"])


def test_prepare_species_data_no_records_returns_empty(tmp_path: Path):
    df = _make_features()
    db = get_db(tmp_path / "test.db")

    X, y = prepare_species_data("Ghost fish", db, df)

    assert len(X) == 0
    assert len(y) == 0


def test_prepare_species_data_bass_pooling(tmp_path: Path):
    df = _make_features()
    db = get_db(tmp_path / "test.db")
    # Add records for both Micropterus species
    _add_obs(db, "Micropterus nigricans", _coords_at(df, range(5, 10)))
    _add_obs(db, "Micropterus salmoides", _coords_at(df, range(20, 25)))

    X_nigricans, _ = prepare_species_data("Micropterus nigricans", db, df)
    X_salmoides, _ = prepare_species_data("Micropterus salmoides", db, df)

    # Both names trigger pooled lookup — same result
    assert len(X_nigricans) == len(X_salmoides)


# ── generate_pseudo_absences ──────────────────────────────────────────────────


def test_generate_pseudo_absences_ratio(tmp_path: Path):
    df = _make_features()
    db = get_db(tmp_path / "test.db")
    # Background observations on many segments
    _add_obs(db, "Other fish", _coords_at(df, range(0, _N)))

    presence_ids = list(df["ogf_id"].iloc[:5])
    absences = generate_pseudo_absences(presence_ids, df, db, ratio=5)

    # Should generate up to 5× presence count
    assert len(absences) <= len(presence_ids) * 5
    assert len(absences) > 0


def test_generate_pseudo_absences_no_target_species_overlap(tmp_path: Path):
    df = _make_features()
    db = get_db(tmp_path / "test.db")
    _add_obs(db, "Background fish", _coords_at(df, range(0, 40)))

    presence_ids = [1, 2, 3, 4, 5]
    absences = generate_pseudo_absences(presence_ids, df, db)

    # Pseudo-absences must not include confirmed-presence segments
    assert not (set(absences) & set(presence_ids))


def test_generate_pseudo_absences_min_distance_buffer(tmp_path: Path):
    df = _make_features()
    db = get_db(tmp_path / "test.db")
    # Background observations across all segments
    _add_obs(db, "Background", _coords_at(df, range(0, _N)))

    presence_ids = [df["ogf_id"].iloc[40]]  # single presence in the middle
    # 10km buffer ≈ 0.09° — adjacent segments should be excluded
    absences = generate_pseudo_absences(presence_ids, df, db, min_network_distance_km=10.0)

    # No absence should be suspiciously close to presence
    pres_lat = df.loc[df["ogf_id"] == presence_ids[0], "centroid_lat"].iloc[0]
    pres_lng = df.loc[df["ogf_id"] == presence_ids[0], "centroid_lng"].iloc[0]
    for abs_id in absences:
        row = df.loc[df["ogf_id"] == abs_id].iloc[0]
        dlat = row["centroid_lat"] - pres_lat
        dlng = row["centroid_lng"] - pres_lng
        dist = (dlat**2 + dlng**2) ** 0.5
        assert dist > 0.09, f"Absence {abs_id} too close to presence"


def test_generate_pseudo_absences_no_background_returns_empty(tmp_path: Path):
    df = _make_features()
    db = get_db(tmp_path / "test.db")
    # No background observations at all
    presence_ids = [1, 2, 3]
    absences = generate_pseudo_absences(presence_ids, df, db)
    assert absences == []


# ── train_species_model (smoke tests) ────────────────────────────────────────


def _setup_smoke_db(tmp_path: Path, df: pd.DataFrame, species: str) -> object:
    """Create a test DB with 20 presence records and a background population."""
    db = get_db(tmp_path / "test.db")
    # 20 presence records for target species
    _add_obs(db, species, _coords_at(df, range(10, 30)))
    # Background observations (many other species + locations)
    for bg_sp in ["Background A", "Background B", "Background C"]:
        _add_obs(db, bg_sp, _coords_at(df, range(0, _N)))
    return db


def test_train_species_model_smoke(tmp_path: Path):
    df = _make_features()
    db = _setup_smoke_db(tmp_path, df, "Semotilus atromaculatus")

    result = train_species_model("Semotilus atromaculatus", db, df)

    assert result["species"] == "Semotilus atromaculatus"
    assert result["n_presence"] >= 5
    assert result["n_pseudo_absence"] > 0
    assert isinstance(result["spatial_cv_auc"], float)
    assert 0.0 <= result["spatial_cv_auc"] <= 1.0
    assert "model" in result


def test_train_species_model_auc_returned(tmp_path: Path):
    df = _make_features()
    db = _setup_smoke_db(tmp_path, df, "Perca flavescens")

    result = train_species_model("Perca flavescens", db, df)

    assert "spatial_cv_auc" in result
    assert isinstance(result["spatial_cv_auc"], float)


def test_train_species_model_feature_importances_sum_to_one(tmp_path: Path):
    df = _make_features()
    db = _setup_smoke_db(tmp_path, df, "Lepomis gibbosus")

    result = train_species_model("Lepomis gibbosus", db, df)

    imps = result["feature_importances"]
    assert isinstance(imps, dict)
    # All original feature names should be present
    assert set(imps.keys()) == set(_ALL_FEATURES)
    total = sum(imps.values())
    assert abs(total - 1.0) < 1e-5, f"Importances sum to {total}, expected ~1.0"


def test_train_species_model_raises_on_insufficient_data(tmp_path: Path):
    df = _make_features()
    db = get_db(tmp_path / "test.db")
    # Only 3 presence records — below threshold
    _add_obs(db, "Rare fish", _coords_at(df, range(5, 8)))

    with pytest.raises(ValueError, match="Insufficient"):
        train_species_model("Rare fish", db, df)


# ── predict_all_segments ─────────────────────────────────────────────────────


def test_predict_all_segments_returns_series(tmp_path: Path):
    df = _make_features()
    db = _setup_smoke_db(tmp_path, df, "Catostomus commersonii")

    result = train_species_model("Catostomus commersonii", db, df)
    preds = predict_all_segments(result, df)

    assert isinstance(preds, pd.Series)
    assert len(preds) == len(df)
    assert preds.index.name == "ogf_id"


def test_predict_all_segments_values_in_0_1(tmp_path: Path):
    df = _make_features()
    db = _setup_smoke_db(tmp_path, df, "Ambloplites rupestris")

    result = train_species_model("Ambloplites rupestris", db, df)
    preds = predict_all_segments(result, df)

    assert preds.between(0.0, 1.0).all(), "Some probabilities outside [0, 1]"


def test_calibrated_probabilities_not_all_extremes(tmp_path: Path):
    """Calibrated model should not cluster predictions at exactly 0.0 or 1.0."""
    df = _make_features()
    db = _setup_smoke_db(tmp_path, df, "Etheostoma caeruleum")

    result = train_species_model("Etheostoma caeruleum", db, df)
    preds = predict_all_segments(result, df)

    # More than 95% of predictions should be strictly between 0 and 1
    interior = preds[(preds > 0.0) & (preds < 1.0)]
    assert len(interior) / len(preds) > 0.95, (
        "Too many predictions at 0.0 or 1.0 — calibration may not be working"
    )
