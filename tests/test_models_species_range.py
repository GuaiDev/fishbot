"""Tests for SpeciesRange and SpeciesAtRisk Pydantic models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.species_range import SpeciesAtRisk, SpeciesRange


def test_species_range_basic():
    sr = SpeciesRange(
        species="Brook Trout",
        scientific_name="Salvelinus fontinalis",
        native_to_ontario=True,
        native_to_great_lakes=True,
        general_range="Cold headwater streams across the Shield.",
        sara_status="Not at Risk",
        ontario_status="Not at Risk",
    )
    assert sr.species == "Brook Trout"
    assert sr.native_to_ontario is True
    assert sr.introduced is False
    assert sr.extirpated_from_ontario is False
    assert sr.jurisdictions_present == []
    assert isinstance(sr.last_updated, datetime)


def test_species_range_sar_fields():
    sr = SpeciesRange(
        species="Greater Redhorse",
        scientific_name="Moxostoma valenciennesi",
        native_to_ontario=True,
        native_to_great_lakes=True,
        general_range="Grand River and tributaries.",
        sara_status="Threatened",
        ontario_status="Threatened",
        cosewic_status="Threatened",
        fishing_notes="Release immediately. Report to MNRF.",
    )
    assert sr.sara_status == "Threatened"
    assert sr.ontario_status == "Threatened"
    assert sr.fishing_notes is not None


def test_extirpated_native_is_valid():
    sr = SpeciesRange(
        species="Atlantic Salmon",
        scientific_name="Salmo salar",
        native_to_ontario=True,
        native_to_great_lakes=False,
        extirpated_from_ontario=True,
        general_range="Lake Ontario population — functionally extirpated.",
        sara_status="Endangered",
        ontario_status="Endangered",
    )
    assert sr.native_to_ontario is True
    assert sr.extirpated_from_ontario is True


def test_optional_fields_default_none():
    sr = SpeciesRange(
        species="Yellow Perch",
        native_to_ontario=True,
        native_to_great_lakes=True,
        general_range="Ubiquitous across Ontario.",
    )
    assert sr.scientific_name is None
    assert sr.habitat_notes is None
    assert sr.sara_status is None
    assert sr.ontario_status is None
    assert sr.cosewic_status is None
    assert sr.fishing_notes is None


def test_jurisdictions_present_is_list():
    sr = SpeciesRange(
        species="Walleye",
        native_to_ontario=True,
        native_to_great_lakes=True,
        general_range="Province-wide.",
        jurisdictions_present=["CA-ON", "US-MI", "US-WI"],
    )
    assert isinstance(sr.jurisdictions_present, list)
    assert "CA-ON" in sr.jurisdictions_present


def test_invalid_sara_status_rejected():
    with pytest.raises(ValidationError):
        SpeciesRange(
            species="Test Fish",
            native_to_ontario=True,
            native_to_great_lakes=False,
            general_range="Nowhere.",
            sara_status="Invalid Status",
        )


def test_species_at_risk_model():
    sar = SpeciesAtRisk(
        species="Redside Dace",
        scientific_name="Clinostomus elongatus",
        sara_status="Threatened",
        ontario_status="Endangered",
        is_protected=True,
        handling_guidance="Release immediately. Do not target.",
        report_url=None,
    )
    assert sar.is_protected is True
    assert sar.handling_guidance != ""


def test_species_at_risk_not_protected():
    sar = SpeciesAtRisk(
        species="Spotted Gar",
        sara_status="Special Concern",
        ontario_status="Special Concern",
        is_protected=False,
        handling_guidance="Catch and release only.",
    )
    assert sar.is_protected is False
    assert sar.scientific_name is None
    assert sar.report_url is None
