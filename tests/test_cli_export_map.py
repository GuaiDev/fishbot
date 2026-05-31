"""Tests for src/cli/export_map.py."""

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.cli.export_map import export_map_data, _haversine_km, HOME_LAT, HOME_LNG


# ── fixtures ──────────────────────────────────────────────────────────────────

def _make_untapped_df():
    """Minimal untapped_potential DataFrame with two nearby segments."""
    return pd.DataFrame({
        "ogf_id": [1001, 1002],
        "centroid_lat": [43.50, 43.55],
        "centroid_lng": [-79.70, -79.65],
        "stream_order": [3, 4],
        "watercourse_name": ["Test Creek", None],
        "watercourse_type": ["Stream", "Stream"],
        "observation_density_25km": [100, 50],
        "is_confluence_segment": [True, False],
        "distance_to_nearest_confluence_km": [0.1, 5.0],
        "nearest_waterbody_distance_m": [50.0, 500.0],
        "connected_to_waterbody": [True, False],
        "habitat_score": [0.7, 0.5],
        "access_score": [0.6, 0.8],
        "observation_pressure": [0.3, 0.1],
        "untapped_score": [0.35, 0.20],
    })


def _make_features_df():
    """Minimal SDM feature matrix matching the untapped rows."""
    return pd.DataFrame({
        "ogf_id": [1001, 1002],
        "centroid_lat": [43.50, 43.55],
        "centroid_lng": [-79.70, -79.65],
        "stream_order": [3, 4],
        "length_m": [500.0, 800.0],
        "flow_verified": [1, 1],
        "summer_mean_temp_c": [18.0, 16.0],
        "do_median_mgl": [9.0, 10.0],
        "ph_median": [7.2, 7.5],
        "conductivity_median_us_cm": [300.0, 250.0],
        "ept_proportion": [0.4, 0.6],
        "barrier_count_upstream": [0, 1],
        "substrate_category": ["Gravel", "Sand"],
        "thermal_regime": ["coldwater", "coolwater"],
        "ept_quality": ["good", "fair"],
        "watercourse_name": ["Test Creek", None],
        "watercourse_type": ["Stream", "Stream"],
        "observation_density_25km": [100, 50],
        "is_confluence_segment": [True, False],
        "distance_to_nearest_confluence_km": [0.1, 5.0],
        "nearest_waterbody_distance_m": [50.0, 500.0],
        "connected_to_waterbody": [True, False],
    })


# ── unit test: haversine ──────────────────────────────────────────────────────

def test_haversine_same_point():
    assert _haversine_km(HOME_LAT, HOME_LNG, HOME_LAT, HOME_LNG) == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance():
    # Toronto (~43.65, -79.38) to Oakville (~43.47, -79.69) ≈ 32 km
    d = _haversine_km(43.4675, -79.6877, 43.65, -79.38)
    assert 28 < d < 38


# ── integration test: export produces valid GeoJSON ───────────────────────────

def test_export_map_generates_geojson(tmp_path):
    out = tmp_path / "map_data.json"
    untapped = _make_untapped_df()
    features_df = _make_features_df()

    with (
        patch("src.cli.export_map.pd.read_parquet") as mock_parquet,
        patch("src.cli.export_map._run_predictions") as mock_preds,
    ):
        # Return untapped on first call, features on second
        mock_parquet.side_effect = [untapped, features_df]

        # Predictions: return empty (no models needed for this test)
        mock_preds.return_value = pd.DataFrame(
            {
                "ogf_id": [1001, 1002],
                "top1_species": ["Creek Chub", "Yellow Perch"],
                "top1_prob": [0.82, 0.71],
                "top2_species": ["Pumpkinseed", "Rock Bass"],
                "top2_prob": [0.65, 0.55],
            }
        ).set_index("ogf_id")

        stats = export_map_data(
            output_path=out,
            html_output_path=tmp_path / "map_index.html",
        )

    assert out.exists(), "Output file should be created"
    assert stats["segments"] == 2

    data = json.loads(out.read_text())

    # Top-level GeoJSON structure
    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert "metadata" in data
    assert data["metadata"]["segment_count"] == 2

    for feat in data["features"]:
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] == "Point"
        assert len(feat["geometry"]["coordinates"]) == 2

        props = feat["properties"]
        # Required properties present
        for key in ("untapped_score", "habitat_score", "access_score", "stream_order",
                    "is_confluence_segment", "connected_to_waterbody",
                    "google_maps_url", "swoop_url"):
            assert key in props, f"Missing property: {key}"

        # Scores are numeric and in range
        assert 0.0 <= props["untapped_score"] <= 1.0
        assert 0.0 <= props["habitat_score"] <= 1.0
        assert 0.0 <= props["access_score"] <= 1.0

        # Links are plausible URLs
        assert props["google_maps_url"].startswith("https://www.google.com/maps/")
        assert props["swoop_url"].startswith("https://maps.ontario.ca/swoop/")

    # Named segment preserved
    named = next(f for f in data["features"] if f["properties"]["watercourse_name"] == "Test Creek")
    assert named["properties"]["is_confluence_segment"] is True
    assert named["properties"]["top1_species"] == "Creek Chub"
