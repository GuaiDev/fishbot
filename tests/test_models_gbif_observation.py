"""Tests for GBIFObservation model validation."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from src.models.gbif_observation import GBIFObservation


def _valid_data(**overrides) -> dict:
    base = {
        "gbif_key": 4058211872,
        "species": "Moxostoma duquesnii",
        "common_name": "Black Redhorse",
        "taxon_key": 2360285,
        "lat": 43.85,
        "lng": -79.03,
        "observed_on": date(2023, 6, 15),
        "country_code": "CA",
        "dataset_name": "iNaturalist research-grade observations",
        "basis_of_record": "HUMAN_OBSERVATION",
        "coordinate_uncertainty_m": 10.0,
        "jurisdiction": "CA-ON",
    }
    base.update(overrides)
    return base


def test_valid_full_record():
    obs = GBIFObservation(**_valid_data())
    assert obs.gbif_key == 4058211872
    assert obs.species == "Moxostoma duquesnii"
    assert obs.basis_of_record == "HUMAN_OBSERVATION"
    assert obs.jurisdiction == "CA-ON"


def test_null_observed_on():
    obs = GBIFObservation(**_valid_data(observed_on=None))
    assert obs.observed_on is None


def test_null_common_name():
    obs = GBIFObservation(**_valid_data(common_name=None))
    assert obs.common_name is None


def test_null_coordinate_uncertainty():
    obs = GBIFObservation(**_valid_data(coordinate_uncertainty_m=None))
    assert obs.coordinate_uncertainty_m is None


def test_null_country_code():
    obs = GBIFObservation(**_valid_data(country_code=None))
    assert obs.country_code is None


def test_null_dataset_name():
    obs = GBIFObservation(**_valid_data(dataset_name=None))
    assert obs.dataset_name is None


def test_ingested_at_defaults_to_now():
    obs = GBIFObservation(**_valid_data())
    assert isinstance(obs.ingested_at, datetime)
    delta = (datetime.now() - obs.ingested_at).total_seconds()
    assert abs(delta) < 5


def test_preserved_specimen_basis():
    obs = GBIFObservation(**_valid_data(basis_of_record="PRESERVED_SPECIMEN", observed_on=None))
    assert obs.basis_of_record == "PRESERVED_SPECIMEN"
    assert obs.observed_on is None


def test_missing_required_field_raises():
    data = _valid_data()
    del data["gbif_key"]
    with pytest.raises(ValidationError):
        GBIFObservation(**data)


def test_missing_basis_of_record_raises():
    data = _valid_data()
    del data["basis_of_record"]
    with pytest.raises(ValidationError):
        GBIFObservation(**data)
