"""Tests for the SDM prediction pipeline. All use synthetic data — no live DB."""

from pathlib import Path

import numpy as np
import pandas as pd

from src.services.sdm_predict import list_trained_species, load_model_metadata, predict_species
from src.services.sdm_train import train_species_model
from src.storage.database import get_db

# ── shared helpers ────────────────────────────────────────────────────────────

_N = 50
_obs_counter = 0


def _make_features(n: int = _N, seed: int = 0) -> pd.DataFrame:
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


def _train_test_model(species: str, df: pd.DataFrame, tmp_path: Path) -> None:
    db = get_db(tmp_path / "test.db")
    global _obs_counter
    for i in range(5, 15):
        _obs_counter += 1
        db["observations"].insert(
            {
                "observation_id": _obs_counter,
                "species": species,
                "common_name": species,
                "taxon_id": 9999,
                "lat": df.iloc[i]["centroid_lat"],
                "lng": df.iloc[i]["centroid_lng"],
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
    train_species_model(species, db=db, features_df=df, models_dir=tmp_path / "models")


# ── tests ─────────────────────────────────────────────────────────────────────


def test_predict_species_no_model_returns_none(tmp_path: Path):
    df = _make_features()
    result = predict_species("Nonexistent fish", features_df=df, models_dir=tmp_path / "models")
    assert result is None


def test_predict_species_returns_dataframe(tmp_path: Path):
    df = _make_features()
    _train_test_model("Lepomis macrochirus", df, tmp_path)

    result = predict_species("Lepomis macrochirus", features_df=df, models_dir=tmp_path / "models")

    assert result is not None
    assert isinstance(result, pd.DataFrame)
    assert len(result) == _N
    assert set(result.columns) >= {
        "ogf_id",
        "species",
        "presence_probability",
        "confidence_tier",
        "model_version",
        "predicted_at",
    }


def test_predictions_bounded_zero_one(tmp_path: Path):
    df = _make_features()
    _train_test_model("Perca flavescens", df, tmp_path)

    result = predict_species("Perca flavescens", features_df=df, models_dir=tmp_path / "models")

    assert result is not None
    assert result["presence_probability"].between(0.0, 1.0).all()


def test_predictions_cover_all_segments(tmp_path: Path):
    df = _make_features()
    _train_test_model("Esox lucius", df, tmp_path)

    result = predict_species("Esox lucius", features_df=df, models_dir=tmp_path / "models")

    assert result is not None
    assert set(result["ogf_id"].tolist()) == set(range(1, _N + 1))


def test_confidence_tier_propagated(tmp_path: Path):
    df = _make_features()
    _train_test_model("Catostomus commersonii", df, tmp_path)

    mdir = tmp_path / "models"
    result = predict_species("Catostomus commersonii", features_df=df, models_dir=mdir)
    meta = load_model_metadata("Catostomus commersonii", models_dir=mdir)

    assert result is not None
    assert meta is not None
    assert (result["confidence_tier"] == meta.confidence_tier).all()


def test_model_version_contains_date(tmp_path: Path):
    df = _make_features()
    _train_test_model("Ambloplites rupestris", df, tmp_path)

    result = predict_species(
        "Ambloplites rupestris", features_df=df, models_dir=tmp_path / "models"
    )

    assert result is not None
    assert result["model_version"].iloc[0].startswith("rf-")


def test_load_model_metadata_missing_returns_none(tmp_path: Path):
    meta = load_model_metadata("Ghost fish", models_dir=tmp_path / "models")
    assert meta is None


def test_load_model_metadata_returns_meta(tmp_path: Path):
    df = _make_features()
    _train_test_model("Semotilus atromaculatus", df, tmp_path)

    meta = load_model_metadata("Semotilus atromaculatus", models_dir=tmp_path / "models")

    assert meta is not None
    assert meta.species == "Semotilus atromaculatus"
    assert meta.n_presence > 0
    assert isinstance(meta.feature_importances, dict)


def test_list_trained_species_empty_dir(tmp_path: Path):
    assert list_trained_species(models_dir=tmp_path / "absent") == []


def test_list_trained_species_returns_sorted(tmp_path: Path):
    df = _make_features()
    for i, sp in enumerate(["Perca flavescens", "Esox lucius", "Ambloplites rupestris"]):
        global _obs_counter
        db = get_db(tmp_path / "test.db")
        for j in range(5, 12):
            _obs_counter += 1
            db["observations"].insert(
                {
                    "observation_id": _obs_counter,
                    "species": sp,
                    "common_name": sp,
                    "taxon_id": 9999,
                    "lat": df.iloc[j + i * 5]["centroid_lat"],
                    "lng": df.iloc[j + i * 5]["centroid_lng"],
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
        train_species_model(sp, db=db, features_df=df, models_dir=tmp_path / "models")

    species_list = list_trained_species(models_dir=tmp_path / "models")
    assert species_list == sorted(species_list)
    assert len(species_list) == 3
