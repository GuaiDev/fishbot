"""Tests for the Observation Pydantic model."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from src.models.observation import Observation


def _valid_obs(**overrides) -> dict:
    base = {
        "observation_id": 123,
        "species": "Cottus cognatus",
        "lat": 43.85,
        "lng": -79.03,
        "observed_on": date(2026, 4, 15),
        "quality_grade": "research",
        "jurisdiction": "CA-ON",
    }
    return {**base, **overrides}


def test_minimal_observation():
    obs = Observation(**_valid_obs())
    assert obs.observation_id == 123
    assert obs.species == "Cottus cognatus"
    assert obs.jurisdiction == "CA-ON"


def test_optional_fields_default_none():
    obs = Observation(**_valid_obs())
    assert obs.common_name is None
    assert obs.taxon_id is None
    assert obs.photo_url is None
    assert obs.observer is None
    assert obs.place_guess is None


def test_optional_fields_set():
    obs = Observation(
        **_valid_obs(
            common_name="Slimy Sculpin",
            taxon_id=12345,
            photo_url="https://example.com/photo.jpg",
            observer="ontariofish",
            place_guess="Rouge River, Ontario",
        )
    )
    assert obs.common_name == "Slimy Sculpin"
    assert obs.taxon_id == 12345
    assert obs.observer == "ontariofish"


def test_ingested_at_defaults_to_now():
    obs = Observation(**_valid_obs())
    assert isinstance(obs.ingested_at, datetime)


def test_missing_required_field_raises():
    data = _valid_obs()
    del data["species"]
    with pytest.raises(ValidationError):
        Observation(**data)


def test_missing_jurisdiction_raises():
    data = _valid_obs()
    del data["jurisdiction"]
    with pytest.raises(ValidationError):
        Observation(**data)


def test_round_trip_model_dump():
    obs = Observation(
        **_valid_obs(common_name="Slimy Sculpin", taxon_id=12345)
    )
    dumped = obs.model_dump(mode="json")
    restored = Observation.model_validate(dumped)
    assert restored.observation_id == obs.observation_id
    assert restored.species == obs.species
    assert restored.common_name == obs.common_name
    assert restored.taxon_id == obs.taxon_id
    assert restored.jurisdiction == obs.jurisdiction
