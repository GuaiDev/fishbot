"""Tests for LureRecommendation model."""

import pytest
from pydantic import ValidationError

from src.models.recommendation import LureRecommendation


def _valid(**overrides) -> LureRecommendation:
    defaults = dict(
        lure_type="spinnerbait (3/8 oz)",
        color="chartreuse/white",
        size_range="3/8-1/2 oz",
        technique="slow-roll near bottom",
        retrieve_speed="medium",
        target_depth_range="2-8 ft",
        conditions_matched=["stained water", "fall season"],
        confidence="high",
        reasoning="Fall smallmouth in stained water: the fish are bulking up before winter.",
    )
    defaults.update(overrides)
    return LureRecommendation(**defaults)


def test_valid_model_constructs():
    rec = _valid()
    assert rec.lure_type == "spinnerbait (3/8 oz)"
    assert rec.confidence == "high"
    assert len(rec.conditions_matched) == 2


def test_all_confidence_values_accepted():
    for level in ("high", "medium", "low"):
        rec = _valid(confidence=level)
        assert rec.confidence == level


def test_all_retrieve_speeds_accepted():
    for speed in ("slow", "medium", "fast", "variable"):
        rec = _valid(retrieve_speed=speed)
        assert rec.retrieve_speed == speed


def test_invalid_confidence_raises():
    with pytest.raises(ValidationError):
        _valid(confidence="extreme")


def test_invalid_retrieve_speed_raises():
    with pytest.raises(ValidationError):
        _valid(retrieve_speed="turbo")


def test_reasoning_empty_string_raises():
    with pytest.raises(ValidationError):
        _valid(reasoning="")


def test_reasoning_whitespace_only_raises():
    with pytest.raises(ValidationError):
        _valid(reasoning="   ")


def test_conditions_matched_is_list():
    rec = _valid(conditions_matched=["a", "b", "c"])
    assert rec.conditions_matched == ["a", "b", "c"]


def test_conditions_matched_can_be_empty():
    rec = _valid(conditions_matched=[])
    assert rec.conditions_matched == []


def test_round_trip_json():
    rec = _valid()
    decoded = LureRecommendation.model_validate_json(rec.model_dump_json())
    assert decoded.lure_type == rec.lure_type
    assert decoded.confidence == rec.confidence
    assert decoded.conditions_matched == rec.conditions_matched
    assert decoded.reasoning == rec.reasoning


def test_model_dump_contains_all_fields():
    rec = _valid()
    d = rec.model_dump()
    expected_fields = {
        "lure_type",
        "color",
        "size_range",
        "technique",
        "retrieve_speed",
        "target_depth_range",
        "conditions_matched",
        "confidence",
        "reasoning",
    }
    assert expected_fields == set(d.keys())
