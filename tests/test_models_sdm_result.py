"""Tests for SDMResult and SDMModelMeta Pydantic models."""

from datetime import datetime

import pytest

from src.models.sdm_result import SDMModelMeta, SDMResult


def test_sdm_result_basic():
    r = SDMResult(
        ogf_id=42,
        species="Lepomis macrochirus",
        presence_probability=0.73,
        confidence_tier="medium",
        model_version="rf-20260529",
    )
    assert r.ogf_id == 42
    assert r.presence_probability == 0.73
    assert isinstance(r.predicted_at, datetime)


def test_sdm_result_rejects_missing_required():
    with pytest.raises(Exception):
        SDMResult(ogf_id=1)  # missing required fields


def test_sdm_model_meta_basic():
    meta = SDMModelMeta(
        species="Semotilus atromaculatus",
        species_slug="semotilus_atromaculatus",
        n_presence=25,
        n_pseudo_absence=250,
        oob_score=0.84,
        feature_names=["stream_order", "length_m"],
        feature_importances={"stream_order": 0.6, "length_m": 0.4},
        model_path="data/models/semotilus_atromaculatus.joblib",
        confidence_tier="medium",
    )
    assert meta.n_presence == 25
    assert meta.confidence_tier == "medium"
    assert isinstance(meta.training_date, datetime)


def test_sdm_model_meta_null_oob():
    meta = SDMModelMeta(
        species="Cottus cognatus",
        species_slug="cottus_cognatus",
        n_presence=6,
        n_pseudo_absence=60,
        oob_score=None,
        feature_names=[],
        feature_importances={},
        model_path="data/models/cottus_cognatus.joblib",
        confidence_tier="low",
    )
    assert meta.oob_score is None


def test_sdm_model_meta_round_trips_json():
    meta = SDMModelMeta(
        species="Perca flavescens",
        species_slug="perca_flavescens",
        n_presence=80,
        n_pseudo_absence=800,
        oob_score=0.91,
        feature_names=["stream_order"],
        feature_importances={"stream_order": 1.0},
        model_path="data/models/perca_flavescens.joblib",
        confidence_tier="high",
    )
    restored = SDMModelMeta.model_validate_json(meta.model_dump_json())
    assert restored.species == meta.species
    assert restored.oob_score == meta.oob_score
    assert restored.confidence_tier == meta.confidence_tier
