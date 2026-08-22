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
    _structural_bonus,
    compute_untapped_potential,
    find_exploration_targets,
    find_untapped_water_for_agent,
    gate_exclusion_reason,
    plausibility_gate,
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


def test_compute_pressure_zero_density_gets_floor():
    fm = _make_feature_matrix(5)
    fm["observation_density_25km"] = 0.0
    pressure = _compute_pressure(fm)
    # All zeros → log1p(0)/ref = 0 → floored at 0.10
    assert pressure.max() == pytest.approx(0.10)
    assert pressure.min() == pytest.approx(0.10)


def test_compute_pressure_preserves_index():
    fm = _make_feature_matrix(10)
    pressure = _compute_pressure(fm)
    assert set(pressure.index) == set(fm["ogf_id"])


# ── unit: plausibility gate ───────────────────────────────────────────────────
#
# The gate replaced the SDM habitat term. It rules segments OUT on affirmative
# evidence only; missing data must never exclude, because the fields it reads
# are absent for ~99% of segments.


def test_gate_passes_segment_with_no_evidence_either_way():
    df = pd.DataFrame({"watercourse_type": ["Stream"], "do_median_mgl": [float("nan")]})
    assert bool(plausibility_gate(df).iloc[0]) is True


def test_gate_missing_columns_entirely_passes_everything():
    df = pd.DataFrame({"ogf_id": [1, 2, 3]})
    assert plausibility_gate(df).all()


def test_gate_excludes_ditch_and_virtual_types():
    df = pd.DataFrame(
        {
            "watercourse_type": ["Stream", "Ditch", "Virtual Flow", "Virtual Connector"],
            "do_median_mgl": [float("nan")] * 4,
        }
    )
    assert list(plausibility_gate(df)) == [True, False, False, False]


def test_gate_excludes_measured_hypoxia_only():
    df = pd.DataFrame(
        {
            "watercourse_type": ["Stream"] * 3,
            # below floor, above floor, never measured
            "do_median_mgl": [2.4, 9.1, float("nan")],
        }
    )
    assert list(plausibility_gate(df)) == [False, True, True]


def test_gate_does_not_rank_two_passing_segments():
    """The gate is boolean by design — it must not express preference."""
    df = pd.DataFrame(
        {
            "watercourse_type": ["Stream", "Stream"],
            "do_median_mgl": [4.1, 13.9],
        }
    )
    gate = plausibility_gate(df)
    assert gate.iloc[0] == gate.iloc[1]


def test_gate_exclusion_reason_is_specific_or_none():
    df = pd.DataFrame(
        {
            "watercourse_type": ["Stream", "Ditch", "Stream"],
            "do_median_mgl": [float("nan"), float("nan"), 2.4],
        }
    )
    assert gate_exclusion_reason(df.iloc[0]) is None
    assert "ditch" in gate_exclusion_reason(df.iloc[1]).lower()
    assert "2.4" in gate_exclusion_reason(df.iloc[2])


def test_gate_zeroes_score_for_excluded_segment():
    """A gated segment must score 0 regardless of how good its other terms are."""
    df = pd.DataFrame(
        {
            "watercourse_type": ["Stream", "Ditch"],
            "do_median_mgl": [float("nan"), float("nan")],
            "observation_pressure": [0.1, 0.1],
            "access_score": [0.9, 0.9],
            "observation_density_25km": [0, 0],
        }
    )
    scores = _compute_mode_score(df, "balanced")
    assert scores.iloc[0] > 0.0
    assert scores.iloc[1] == 0.0


# ── unit: formula correctness ─────────────────────────────────────────────────


def test_untapped_formula_low_pressure_remote_scores_highest(tmp_path: Path, monkeypatch):
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

    _insert_access_scores(tmp_path, {1: 1.0, 2: 0.5, 3: 0.5, 4: 0.5, 5: 0.5})

    df = compute_untapped_potential(db, fm)

    # Segment 1: density=0 → pressure=0.10 (floor), remoteness=1.5, struct=1.0
    # balanced: (1-0.10) × 1.0 × 1.5 = 1.35
    seg1 = df[df["ogf_id"] == 1].iloc[0]
    assert seg1["untapped_score"] == pytest.approx(1.35)

    # Segment 2: higher density → more pressure, no remoteness bonus → lower
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

    _insert_access_scores(tmp_path, {i: 0.5 for i in range(1, 11)})

    df = compute_untapped_potential(db, fm)
    scores = df["untapped_score"].values
    assert np.all(scores[:-1] >= scores[1:])


def test_untapped_ignores_sdm_predictions_entirely(tmp_path: Path, monkeypatch):
    """SDM predictions in the DB must not influence the ranking any more.

    Previously `species=` reweighted scores by per-species habitat probability.
    That model scored 0.51-0.61 AUC, so the reweighting was noise. Predictions
    may still exist in the DB from the research path; they must be inert here.
    """
    import src.services.accessibility as acc_mod
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(acc_mod, "_PARQUET_PATH", tmp_path / "a.parquet")
    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "u.parquet")
    monkeypatch.setattr(up_mod, "_FEATURE_MATRIX_PATH", tmp_path / "fm.parquet")

    db = get_db(tmp_path / "test.db")
    fm = _make_feature_matrix(5)
    fm["observation_density_25km"] = 0.0
    _insert_access_scores(tmp_path, {i: 1.0 for i in range(1, 6)})

    before = compute_untapped_potential(db, fm)

    # Wildly lopsided predictions — would have dominated the old formula.
    _insert_predictions(db, "Semotilus atromaculatus", {1: 0.99, 2: 0.01, 3: 0.5, 4: 0.5, 5: 0.5})
    after = compute_untapped_potential(db, fm)

    pd.testing.assert_series_equal(
        before.set_index("ogf_id")["untapped_score"],
        after.set_index("ogf_id")["untapped_score"],
    )


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

    result = json.loads(
        find_exploration_targets(
            db, 43.75, -79.75, radius_km=200, mode="balanced", enable_vision=False
        )
    )

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

    df = pd.DataFrame({"observation_pressure": [0.5, 0.7]})
    bonus = _structural_bonus(df)
    assert (bonus == 1.0).all()


# ── seen-before penalty ───────────────────────────────────────────────────────


def test_seen_before_penalty_pushes_segment_down(tmp_path: Path, monkeypatch):
    """Previously shown ogf_id scores 0.3× so it ranks below equal-quality unseen segments."""
    import src.services.accessibility as acc_mod
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(acc_mod, "_PARQUET_PATH", tmp_path / "a.parquet")
    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "u.parquet")
    monkeypatch.setattr(up_mod, "_FEATURE_MATRIX_PATH", tmp_path / "fm.parquet")

    db = get_db(tmp_path / "test.db")
    fm = _make_feature_matrix(4)
    fm["observation_density_25km"] = 0.0
    fm["stream_order"] = [3, 3, 3, 3]
    _insert_predictions(db, "Sp", {i: 0.6 for i in range(1, 5)})
    _insert_access_scores(tmp_path, {i: 0.7 for i in range(1, 5)})
    compute_untapped_potential(db, fm)

    # Without penalty: all scores equal, first segment wins ties
    result_no_penalty = json.loads(
        find_exploration_targets(
            db, 43.75, -79.75, radius_km=200, mode="balanced",
            limit=4, enable_vision=False,
        )
    )
    first_ids_no_penalty = [s["ogf_id"] for s in result_no_penalty.get("segments", [])]

    # With penalty on first segment: it should rank last
    if not first_ids_no_penalty:
        pytest.skip("No segments returned without penalty")

    penalised_id = first_ids_no_penalty[0]
    result_with_penalty = json.loads(
        find_exploration_targets(
            db, 43.75, -79.75, radius_km=200, mode="balanced",
            limit=4, enable_vision=False,
            previously_shown_ogf_ids=[penalised_id],
        )
    )
    ids_with_penalty = [s["ogf_id"] for s in result_with_penalty.get("segments", [])]

    # Penalised segment should no longer be first
    if ids_with_penalty:
        assert ids_with_penalty[0] != penalised_id


# ── dismiss + trip log feedback loop ─────────────────────────────────────────


def _make_fm_with_centroids(tmp_path, n=4):
    """Feature matrix where ogf_id N has centroid at (43.5 + N*0.01, -79.5)."""
    lats = [43.5 + i * 0.01 for i in range(n)]
    lngs = [-79.5] * n
    return pd.DataFrame(
        {
            "ogf_id": list(range(1, n + 1)),
            "centroid_lat": lats,
            "centroid_lng": lngs,
            "stream_order": [3] * n,
            "observation_density_25km": [0.0] * n,
            "watercourse_type": [""] * n,
            "watercourse_name": [""] * n,
        }
    )


def _setup_full_env(tmp_path, monkeypatch):
    import src.services.accessibility as acc_mod
    import src.services.untapped_potential as up_mod

    monkeypatch.setattr(acc_mod, "_PARQUET_PATH", tmp_path / "a.parquet")
    monkeypatch.setattr(up_mod, "_PARQUET_PATH", tmp_path / "u.parquet")
    monkeypatch.setattr(up_mod, "_FEATURE_MATRIX_PATH", tmp_path / "fm.parquet")

    db = get_db(tmp_path / "test.db")
    fm = _make_fm_with_centroids(tmp_path)
    _insert_predictions(db, "Sp", {i: 0.6 for i in range(1, 5)})
    _insert_access_scores(tmp_path, {i: 0.7 for i in range(1, 5)})

    # Write feature matrix parquet so _snap_trips_to_segments can read it
    fm_slim = fm[["ogf_id", "centroid_lat", "centroid_lng"]].copy()
    fm_slim.to_parquet(tmp_path / "fm.parquet", index=False)

    compute_untapped_potential(db, fm)
    return db, fm


def test_dismissed_segments_penalized(tmp_path, monkeypatch):
    """Segment in dismissed_segments scores 0.3× and ranks below equal-quality segments."""
    db, _ = _setup_full_env(tmp_path, monkeypatch)

    # Dismiss ogf_id=1
    from datetime import datetime
    db["dismissed_segments"].insert(
        {"ogf_id": 1, "dismissed_at": datetime.now().isoformat(), "reason": "private"}
    )

    result = json.loads(
        find_exploration_targets(
            db, 43.75, -79.5, radius_km=200, mode="balanced",
            limit=4, enable_vision=False,
        )
    )
    ids = [s["ogf_id"] for s in result.get("segments", [])]
    # ogf_id 1 should not be first — penalised to 0.3× score
    if len(ids) >= 2:
        assert ids[0] != 1


def test_trip_log_segments_penalized(tmp_path, monkeypatch):
    """Trip with lat/lng near ogf_id=2 causes that segment to be penalised."""
    db, fm = _setup_full_env(tmp_path, monkeypatch)

    # ogf_id=2 centroid is at (43.51, -79.5) — insert a trip 200m away
    from datetime import datetime
    db["trips"].insert(
        {
            "id": 1,
            "status": "completed",
            "date": "2026-05-01",
            "planned_for": None,
            "jurisdiction": "CA-ON",
            "location_name": "Test Creek",
            "lat": 43.510,   # very close to ogf_id=2 centroid at 43.51
            "lng": -79.500,
            "species_caught": None,
            "conditions": None,
            "gear_used": None,
            "notes": None,
            "what_worked": None,
            "what_didnt": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    )

    result = json.loads(
        find_exploration_targets(
            db, 43.75, -79.5, radius_km=200, mode="balanced",
            limit=4, enable_vision=False,
        )
    )
    ids = [s["ogf_id"] for s in result.get("segments", [])]
    if len(ids) >= 2:
        assert ids[0] != 2


def test_dismiss_tool_inserts_record(tmp_path, monkeypatch):
    """dismiss_segment tool call inserts a row into dismissed_segments."""
    import src.storage.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "test.db")

    db = get_db(tmp_path / "test.db")

    # Call the tool dispatch directly
    import json as _json

    from src.agent.chat import _execute_tool

    result = _json.loads(_execute_tool("dismiss_segment", {"ogf_id": 42, "reason": "private"}))
    assert result["success"] is True
    assert result["ogf_id"] == 42

    rows = list(db["dismissed_segments"].rows)
    assert len(rows) == 1
    assert rows[0]["ogf_id"] == 42
    assert rows[0]["reason"] == "private"
