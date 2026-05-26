"""Tests for the BirdObservation Pydantic model."""

from datetime import date, datetime

from src.models.bird_observation import BirdObservation


def _make(**kwargs) -> BirdObservation:
    defaults = dict(
        obs_id="S123_grbher3",
        species_code="grbher3",
        common_name="Great Blue Heron",
        scientific_name="Ardea herodias",
        lat=43.643,
        lng=-79.381,
        observed_on=date(2026, 5, 24),
        how_many=2,
        location_name="Toronto Harbour",
        jurisdiction="CA-ON",
        piscivore_significance="Active hunting indicates shallow fish-bearing water",
        fetched_at=datetime(2026, 5, 25, 10, 0, 0),
    )
    return BirdObservation(**{**defaults, **kwargs})


def test_model_valid():
    obs = _make()
    assert obs.species_code == "grbher3"
    assert obs.jurisdiction == "CA-ON"


def test_how_many_nullable():
    obs = _make(how_many=None)
    assert obs.how_many is None


def test_scientific_name_nullable():
    obs = _make(scientific_name=None)
    assert obs.scientific_name is None


def test_location_name_nullable():
    obs = _make(location_name=None)
    assert obs.location_name is None


def test_fetched_at_defaults_to_now():
    obs = BirdObservation(
        obs_id="S999_osprey1",
        species_code="osprey1",
        common_name="Osprey",
        lat=43.7,
        lng=-79.4,
        observed_on=date(2026, 5, 20),
        jurisdiction="CA-ON",
        piscivore_significance="Confirmed fish presence",
    )
    assert isinstance(obs.fetched_at, datetime)


def test_obs_id_composite():
    obs = _make(obs_id="S234567890_grbher3")
    assert "_" in obs.obs_id


def test_observed_on_is_date():
    obs = _make()
    assert isinstance(obs.observed_on, date)
