"""Tests for species range storage layer."""

from src.models.species_range import SpeciesRange
from src.storage.database import get_db
from src.storage.species_ranges import (
    is_species_at_risk,
    query_sar_species,
    query_species_range,
    upsert_species_ranges,
)


def _make_db(tmp_path):
    return get_db(tmp_path / "test.db")


def _sample_ranges() -> list[SpeciesRange]:
    return [
        SpeciesRange(
            species="Brook Trout",
            scientific_name="Salvelinus fontinalis",
            native_to_ontario=True,
            native_to_great_lakes=True,
            general_range="Cold headwater streams.",
            jurisdictions_present=["CA-ON", "US-MI"],
            sara_status="Not at Risk",
            ontario_status="Not at Risk",
        ),
        SpeciesRange(
            species="Greater Redhorse",
            scientific_name="Moxostoma valenciennesi",
            native_to_ontario=True,
            native_to_great_lakes=True,
            general_range="Grand River and tributaries.",
            jurisdictions_present=["CA-ON", "CA-QC"],
            sara_status="Threatened",
            ontario_status="Threatened",
            fishing_notes="Release immediately. Report to MNRF.",
        ),
        SpeciesRange(
            species="Smallmouth Bass",
            scientific_name="Micropterus dolomieu",
            native_to_ontario=True,
            native_to_great_lakes=True,
            general_range="Widespread in southern and central Ontario.",
            jurisdictions_present=["CA-ON", "US-MI", "US-OH"],
            sara_status="Not at Risk",
            ontario_status="Not at Risk",
        ),
        SpeciesRange(
            species="Redside Dace",
            scientific_name="Clinostomus elongatus",
            native_to_ontario=True,
            native_to_great_lakes=True,
            general_range="Cold headwater streams in southern Ontario.",
            jurisdictions_present=["CA-ON"],
            sara_status="Threatened",
            ontario_status="Endangered",
            fishing_notes="Do not target. Release immediately.",
        ),
        SpeciesRange(
            species="Spotted Gar",
            scientific_name="Lepisosteus oculatus",
            native_to_ontario=True,
            native_to_great_lakes=True,
            general_range="Lake Erie and Lake St. Clair.",
            jurisdictions_present=["CA-ON", "US-OH"],
            sara_status="Special Concern",
            ontario_status="Special Concern",
        ),
    ]


def test_upsert_and_query_exact(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    result = query_species_range(db, "Brook Trout")
    assert result is not None
    assert result.species == "Brook Trout"
    assert result.native_to_ontario is True


def test_query_case_insensitive(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    result = query_species_range(db, "brook trout")
    assert result is not None
    assert result.species == "Brook Trout"


def test_query_partial_match(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    result = query_species_range(db, "redhorse")
    assert result is not None
    assert "Redhorse" in result.species


def test_query_unknown_returns_none(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    result = query_species_range(db, "platypus")
    assert result is None


def test_upsert_idempotent(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    upsert_species_ranges(db, _sample_ranges())
    result = query_species_range(db, "Smallmouth Bass")
    assert result is not None
    count = db["species_ranges"].count
    assert count == len(_sample_ranges())


def test_jurisdictions_present_roundtrip(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    result = query_species_range(db, "Smallmouth Bass")
    assert isinstance(result.jurisdictions_present, list)
    assert "CA-ON" in result.jurisdictions_present


def test_query_sar_returns_only_at_risk(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    sar = query_sar_species(db, "CA-ON")
    names = [s.species for s in sar]
    assert "Greater Redhorse" in names
    assert "Redside Dace" in names
    assert "Spotted Gar" in names
    assert "Brook Trout" not in names
    assert "Smallmouth Bass" not in names


def test_query_sar_jurisdiction_filter(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    # Redside Dace only has CA-ON; Greater Redhorse has CA-ON and CA-QC
    sar_qc = query_sar_species(db, "CA-QC")
    names = [s.species for s in sar_qc]
    assert "Greater Redhorse" in names
    assert "Redside Dace" not in names  # not in CA-QC jurisdictions_present


def test_is_species_at_risk_true(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    assert is_species_at_risk(db, "Greater Redhorse") is True
    assert is_species_at_risk(db, "redside dace") is True


def test_is_species_at_risk_false(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    assert is_species_at_risk(db, "Smallmouth Bass") is False
    assert is_species_at_risk(db, "brook trout") is False


def test_is_species_at_risk_unknown(tmp_path):
    db = _make_db(tmp_path)
    upsert_species_ranges(db, _sample_ranges())
    assert is_species_at_risk(db, "narwhal") is False
