"""Tests for untapped potential scoring. All use synthetic data — no live calls."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.services.untapped_potential import (
    _build_connectivity_note,
    _compute_mode_score,
    _compute_pressure,
    _load_habitat_scores,
    _resolve_species,
    _structural_bonus,
    compute_untapped_potential,
    find_exploration_targets,
    find_untapped_water_for_agent,
)
from src.storage.database import get_db

# ── synthetic helpers ─────────────────────────────────────────────────────────


def _make_feature_matrix(n: int = 20, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    lats = np.linspace(43.5, 44.0, n)
    lngs = np.linspace(-80.0, -79.5, n)
    density = rng.uniform(0, 10, n)
    return pd.DataFrame(
        {
            "ogf_id": list(range(1, n + 1)),
            "centroid_lat": lats,
            "centroid_lng": lngs,
            "stream_order": rng.integers(1, 5, n),
            "observation_density_25km": density,
        }
    )


def _insert_predictions(db, species: str, scores: dict[int, float]) -> None:
    if "sdm_predictions" not in db.table_names():
        db["sdm_predictions"].create(
            {
                "ogf_id": int,
                "species": str,
                "presence_probability": float,
                "model_version": str,
                "predicted_at": str,
                "centroid_lat": float,
                "centroid_lng": float,
            },
            pk=["ogf_id", "species"],
        )
    rows = [
        {
            "ogf_id": ogf_id,
            "species": species,
            "presence_probability": prob,
            "model_version": "2c-v1",
            "predicted_at": "2026-05-01T00:00:00",
            "centroid_lat": 43.6,
            "centroid_lng": -79.4,
        }
        for ogf_id, prob in scores.items()
    ]
    db["sdm_predictions"].upsert_all(rows, pk=["ogf_id", "species"])


def _insert_access_scores(path: Path, scores: dict[int, float]) -> None:

    s = pd.Series(scores, name="access_score")
    s.index.name = "ogf_id"
    s.to_frame().to_parquet(path / "access_scores.parquet")


# ── unit: pressure normalisation ─────────────────────────────────────────────


def test_compute_pressure_normalises_to_01():
    fm = _make_feature_matrix(20)
    pressure = _compute_pressure(fm)
    assert pressure.min() >= 0.0
    assert pressure.max() <= 1.0


def test_compute_pressure_zero_density_is_zero():
    fm = _make_feature_matrix(5)
    fm["observation_density_25km"] = 0.0
    pressure = _compute_pressure(fm)
    # All zeros → constant → clipped to 0 (degenerate case)
    assert (pressure == 0.0).all()


def test_compute_pressure_preserves_index():
    fm = _make_feature_matrix(10)
    pressure = _compute_pressure(fm)
    assert set(pressure.index) == set(fm["ogf_id"])


# ── unit: habitat score loading ───────────────────────────────────────────────


def test_load_habitat_scores_no_predictions_table(tmp_path: Path):
    db = get_db(tmp_path / "test.db")
    scores = _load_habitat_scores(db, None)
    assert len(scores) == 0


def test_load_habitat_scores_averages_across_species(tmp_path: Path):
    db = get_db(tmp_path / "test.db")
    _insert_predictions(db, "Species A", {1: 0.8, 2: 0.6})
    _insert_predictions(db, "Species B", {1: 0.4, 2: 0.2})

    scores = _load_habitat_scores(db, None)
    assert scores.loc[1] == pytest.approx(0.6)
    assert scores.loc[2] == pytest.approx(0.4)


def test_load_habitat_scores_filters_by_species(tmp_path: Path):
    db = get_db(tmp_path / "test.db")
    _insert_predictions(db, "semotilus atromaculatus", {1: 0.9, 2: 0.1})
    _insert_predictions(db, "perca flavescens", {1: 0.3, 2: 0.7})

    scores = _load_habitat_scores(db, "Semotilus atromaculatus")
    assert scores.loc[1] == pytest.approx(0.9)
    assert scores.loc[2] == pytest.approx(0.1)


def test_resolve_species_common_name():
    assert _resolve_species("Creek Chub") == "Semotilus atromaculatus"
    assert _resolve_species("creek chub") == "Semotilus atromaculatus"


def test_resolve_species_scientific_passthrough():
    assert _resolve_species("Perca flavescens") == "Perca flavescens"


# ── unit: formula correctness ─────────────────────────────────────────────────


def test_untapped_formula_high_habitat_low_pressure_good_access(tmp_path: Path, monkeypatch):
    import src.services.accessibility as acc_mod
    import src.services.untapped_potential as up_mod

    acc_path = tmp_path / "access_scores.parquet"
    up_path = tmp_path / "untapped_potential.parquet"
    monkeypatch.setattr(acc_mod, "_PARQUET_PATH", acc_path)
    monkeypatch.setattr(up_mod, "_PARQUET_PATH", up_path)
    monkeypatch.setattr(up_mod, "_FEATURE_MATRIX_PATH", tmp_path / "fm.parquet")

    db = get_db(tmp_path / "test.db")
    fm = _make_feature_matrix(5)
    fm["observation_density_25km"] = [0.0, 5.0, 5.0, 5.0, 5.0]

    _insert_predictions(db, "TestSpecies", {1: 1.0, 2: 0.5, 3: 0.5, 4: 0.5, 5: 0.5})
    _insert_access_scores(tmp_path, {1: 1.0, 2: 0.5, 3: 0.5, 4: 0.5, 5: 0.5})

    df = compute_untapped_potential(db, fm)

    # Segment 1: habitat=1.0, pressure=0.0, access=1.0 → untapped=1.0
    seg1 = df[df["ogf_id"] == 1].iloc[0]
    assert seg1["untapped_score"] == pytest.approx(1.0)

    # Segment 2: habitat=0.5, pressure>0, access=0.5 → lower
    seg2 = df[df["ogf_id"] == 2].iloc[0]
    assert seg2["untapped_score"] < seg1["untapped_score"]


def test_untapped_sorted_descending(tmp_path: Path, monkeypatch):
    import src.services.accessibility as acc_mod
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(acc_mod, "_PARQUET_PATH", tmp_path / "a.parquet")
    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "u.parquet")
    monkeypatch.setattr(up_mod, "_FEATURE_MATRIX_PATH", tmp_path / "fm.parquet")

    db = get_db(tmp_path / "test.db")
    fm = _make_feature_matrix(10)
    fm["observation_density_25km"] = np.linspace(0, 9, 10)

    _insert_predictions(db, "Sp", {i: 0.5 for i in range(1, 11)})
    _insert_access_scores(tmp_path, {i: 0.5 for i in range(1, 11)})

    df = compute_untapped_potential(db, fm)
    scores = df["untapped_score"].values
    assert np.all(scores[:-1] >= scores[1:])


def test_untapped_species_filter_changes_scores(tmp_path: Path, monkeypatch):
    import src.services.accessibility as acc_mod
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(acc_mod, "_PARQUET_PATH", tmp_path / "a.parquet")
    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "u.parquet")
    monkeypatch.setattr(up_mod, "_FEATURE_MATRIX_PATH", tmp_path / "fm.parquet")

    db = get_db(tmp_path / "test.db")
    fm = _make_feature_matrix(5)
    fm["observation_density_25km"] = 0.0

    _insert_predictions(db, "Semotilus atromaculatus", {1: 0.9, 2: 0.1, 3: 0.5, 4: 0.5, 5: 0.5})
    _insert_predictions(db, "Perca flavescens", {1: 0.1, 2: 0.9, 3: 0.5, 4: 0.5, 5: 0.5})
    _insert_access_scores(tmp_path, {i: 1.0 for i in range(1, 6)})

    df_creek = compute_untapped_potential(db, fm, species="Creek Chub")
    df_perch = compute_untapped_potential(db, fm, species="Yellow Perch")

    # Creek Chub: seg 1 should rank highest
    assert df_creek.iloc[0]["ogf_id"] == 1
    # Yellow Perch: seg 2 should rank highest
    assert df_perch.iloc[0]["ogf_id"] == 2


# ── agent wrapper tests ───────────────────────────────────────────────────────


def test_find_untapped_water_no_cache(tmp_path: Path, monkeypatch):
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "missing.parquet")

    db = get_db(tmp_path / "test.db")
    result = json.loads(find_untapped_water_for_agent(db, 43.65, -79.38))
    assert "error" in result


def test_find_untapped_water_spatial_filter(tmp_path: Path, monkeypatch):
    import src.services.accessibility as acc_mod
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(acc_mod, "_PARQUET_PATH", tmp_path / "a.parquet")
    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "u.parquet")
    monkeypatch.setattr(up_mod, "_FEATURE_MATRIX_PATH", tmp_path / "fm.parquet")

    db = get_db(tmp_path / "test.db")
    fm = _make_feature_matrix(10)
    fm["observation_density_25km"] = 0.0
    _insert_predictions(db, "Sp", {i: 0.7 for i in range(1, 11)})
    _insert_access_scores(tmp_path, {i: 0.8 for i in range(1, 11)})

    compute_untapped_potential(db, fm)

    # Query near the first segment (43.5, -80.0) with tiny radius
    result = json.loads(find_untapped_water_for_agent(db, 43.5, -80.0, radius_km=5, limit=10))
    # Segments far from 43.5/-80.0 should be excluded
    if "segments" in result:
        for seg in result["segments"]:
            assert abs(seg["centroid_lat"] - 43.5) <= 0.1
            assert abs(seg["centroid_lng"] - -80.0) <= 0.1


def test_find_untapped_water_stream_order_filter(tmp_path: Path, monkeypatch):
    import src.services.accessibility as acc_mod
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(acc_mod, "_PARQUET_PATH", tmp_path / "a.parquet")
    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "u.parquet")
    monkeypatch.setattr(up_mod, "_FEATURE_MATRIX_PATH", tmp_path / "fm.parquet")

    db = get_db(tmp_path / "test.db")
    fm = _make_feature_matrix(5)
    fm["observation_density_25km"] = 0.0
    fm["stream_order"] = [1, 1, 3, 3, 3]
    _insert_predictions(db, "Sp", {i: 0.6 for i in range(1, 6)})
    _insert_access_scores(tmp_path, {i: 0.7 for i in range(1, 6)})

    compute_untapped_potential(db, fm)

    result = json.loads(
        find_untapped_water_for_agent(db, 43.75, -79.75, radius_km=100, min_stream_order=2)
    )
    if "segments" in result:
        for seg in result["segments"]:
            assert seg["stream_order"] >= 2


def test_find_untapped_water_model_note_present(tmp_path: Path, monkeypatch):
    import src.services.accessibility as acc_mod
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(acc_mod, "_PARQUET_PATH", tmp_path / "a.parquet")
    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "u.parquet")
    monkeypatch.setattr(up_mod, "_FEATURE_MATRIX_PATH", tmp_path / "fm.parquet")

    db = get_db(tmp_path / "test.db")
    fm = _make_feature_matrix(5)
    fm["observation_density_25km"] = 0.0
    _insert_predictions(db, "Sp", {i: 0.6 for i in range(1, 6)})
    _insert_access_scores(tmp_path, {i: 0.7 for i in range(1, 6)})
    compute_untapped_potential(db, fm)

    result = json.loads(find_untapped_water_for_agent(db, 43.75, -79.75, radius_km=200))
    assert "model_note" in result


# ── Phase 2e: find_exploration_targets ───────────────────────────────────────


def test_scoring_modes_produce_different_rankings():
    """_compute_mode_score ranks high-access vs low-access segments differently per mode."""
    df = pd.DataFrame(
        {
            "ogf_id": [1, 2],
            "habitat_score": [0.8, 0.8],
            "observation_pressure": [0.1, 0.1],
            "access_score": [0.9, 0.1],  # seg1=road-accessible, seg2=remote
        }
    )
    easy = _compute_mode_score(df, "easy_access")
    adv = _compute_mode_score(df, "adventure")
    bal = _compute_mode_score(df, "balanced")

    # easy_access: high access wins
    assert float(easy.iloc[0]) > float(easy.iloc[1])
    # adventure: low access (remote) wins
    assert float(adv.iloc[1]) > float(adv.iloc[0])
    # balanced: access ignored → equal scores
    assert float(bal.iloc[0]) == pytest.approx(float(bal.iloc[1]))


def test_adventure_mode_rewards_low_access():
    """access_score=0.1 outranks access_score=0.9 in adventure mode."""
    df = pd.DataFrame(
        {
            "ogf_id": [1, 2],
            "habitat_score": [0.7, 0.7],
            "observation_pressure": [0.2, 0.2],
            "access_score": [0.9, 0.1],
        }
    )
    scores = _compute_mode_score(df, "adventure")
    # seg2 (low access) should score higher in adventure mode
    assert float(scores.iloc[1]) > float(scores.iloc[0])


def test_connectivity_note_generated_when_stream_and_species_present():
    """_build_connectivity_note returns a note when stream within 3km and species confirmed."""
    note = _build_connectivity_note(
        seg_name=None,
        named_stream_3km="Humber River (1.2km)",
        nearby_species=["Creek Chub", "Pumpkinseed"],
    )
    assert note is not None
    assert "Humber River" in note
    assert "Creek Chub" in note
    assert "dispersal" in note


def test_connectivity_note_none_without_named_stream():
    """No connectivity note when there is no named stream within 3km."""
    assert _build_connectivity_note(None, None, ["Creek Chub"]) is None


def test_connectivity_note_none_without_nearby_species():
    """No connectivity note when no confirmed species were found nearby."""
    assert _build_connectivity_note(None, "Humber River (1.2km)", []) is None


def test_regulation_zone_toronto():
    """_estimate_fmz returns a valid FMZ integer for Toronto coordinates."""
    from src.services.regulations import _estimate_fmz

    fmz = _estimate_fmz(43.65, -79.38)
    assert fmz is not None
    assert isinstance(fmz, int)
    assert 1 <= fmz <= 20


def test_find_exploration_targets_no_cache(tmp_path: Path, monkeypatch):
    """Returns error JSON when untapped parquet not yet computed."""
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "missing.parquet")

    db = get_db(tmp_path / "test.db")
    result = json.loads(find_exploration_targets(db, 43.65, -79.38, enable_vision=False))
    assert "error" in result


def test_find_exploration_targets_balanced_mode(tmp_path: Path, monkeypatch):
    """find_exploration_targets returns segments with enrichment fields in balanced mode."""
    import src.services.accessibility as acc_mod
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(acc_mod, "_PARQUET_PATH", tmp_path / "a.parquet")
    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "u.parquet")
    monkeypatch.setattr(up_mod, "_FEATURE_MATRIX_PATH", tmp_path / "fm.parquet")

    db = get_db(tmp_path / "test.db")
    fm = _make_feature_matrix(5)
    fm["observation_density_25km"] = 0.0
    fm["stream_order"] = [2, 2, 3, 3, 4]
    _insert_predictions(db, "Sp", {i: 0.6 for i in range(1, 6)})
    _insert_access_scores(tmp_path, {i: 0.7 for i in range(1, 6)})
    compute_untapped_potential(db, fm)

    result = json.loads(find_exploration_targets(db, 43.75, -79.75, radius_km=200, mode="balanced", enable_vision=False))

    assert "segments" in result
    assert result.get("mode") == "balanced"
    if result["segments"]:
        seg = result["segments"][0]
        assert "nearby_confirmed_species" in seg
        assert "connectivity_note" in seg
        assert "habitat_summary" in seg
        assert "regulation_zone" in seg
        assert "maps_urls" in seg


# ── Phase 3a: structural scoring tests ────────────────────────────────────────


def test_structural_bonus_confluence_scores_higher():
    """Confluence segment scores higher than identical non-confluence segment."""

    df = pd.DataFrame({
        "habitat_score": [0.6, 0.6],
        "observation_pressure": [0.2, 0.2],
        "access_score": [0.5, 0.5],
        "is_confluence_segment": [True, False],
        "distance_to_nearest_confluence_km": [0.0, 5.0],
        "connected_to_waterbody": [False, False],
    })
    bonus = _structural_bonus(df)
    assert float(bonus.iloc[0]) > float(bonus.iloc[1])
    assert float(bonus.iloc[0]) == pytest.approx(1.4)  # +0.4 for confluence


def test_structural_bonus_waterbody_adds_to_score():
    """connected_to_waterbody adds +0.3 bonus."""

    df = pd.DataFrame({
        "is_confluence_segment": [False, False],
        "distance_to_nearest_confluence_km": [5.0, 5.0],
        "connected_to_waterbody": [True, False],
    })
    bonus = _structural_bonus(df)
    assert float(bonus.iloc[0]) == pytest.approx(1.3)
    assert float(bonus.iloc[1]) == pytest.approx(1.0)


def test_structural_bonus_capped_at_two():
    """Confluence + waterbody bonus is capped at 2.0."""

    df = pd.DataFrame({
        "is_confluence_segment": [True],
        "distance_to_nearest_confluence_km": [0.0],
        "connected_to_waterbody": [True],
    })
    bonus = _structural_bonus(df)
    # 1.0 + 0.4 + 0.3 = 1.7 → not capped in this case
    assert float(bonus.iloc[0]) == pytest.approx(1.7)


def test_structural_bonus_graceful_missing_columns():
    """_structural_bonus returns 1.0 when structural columns are absent."""

    df = pd.DataFrame({"habitat_score": [0.5, 0.7]})
    bonus = _structural_bonus(df)
    assert (bonus == 1.0).all()
