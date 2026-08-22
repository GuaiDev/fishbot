"""Conservation status must fail closed until verified against a real registry.

The statuses in data/processed/ontario_species_ranges.json were generated
during development, not sourced. Trusting a bare "Not at Risk" would clear the
conservation flag on text nobody checked — the worst-consequence failure in
this system, since it ends with someone targeting a protected fish.
"""

from datetime import UTC, datetime

import pytest

from src.models.context import ProvenanceKind
from src.models.species_range import SpeciesRange
from src.services.context.species import describe_species
from src.storage.database import get_db
from src.storage.species_ranges import upsert_species_ranges


@pytest.fixture
def db(tmp_path):
    return get_db(tmp_path / "sr.db")


def _species(**overrides) -> SpeciesRange:
    base = dict(
        species="Least Darter",
        scientific_name="Etheostoma microperca",
        native_to_ontario=True,
        native_to_great_lakes=True,
        general_range="Southwestern Ontario.",
        habitat_notes="Dense aquatic vegetation.",
        fishing_notes="Rare microfishing target.",
        sara_status="Not at Risk",
        ontario_status="Not at Risk",
        cosewic_status="Not at Risk",
    )
    base.update(overrides)
    return SpeciesRange(**base)


def test_unverified_not_at_risk_still_raises_the_flag(db):
    """The whole point: an unsourced 'Not at Risk' is not evidence of safety."""
    upsert_species_ranges(db, [_species()])
    c = describe_species(db, "Least Darter")
    assert c.sar_alert is True
    assert c.targeting_guidance_suppressed is True
    assert "not been verified" in c.sar_reason


def test_unverified_status_is_tagged_inference_not_record(db):
    upsert_species_ranges(db, [_species()])
    f = describe_species(db, "Least Darter").conservation_status
    assert f.provenance.kind is ProvenanceKind.INFERENCE
    assert "generated during development" in (f.meaning or "")


def test_verified_not_at_risk_clears_the_flag_and_cites_its_source(db):
    upsert_species_ranges(db, [_species(
        status_source="COSEWIC assessments, Nov 2025",
        status_source_url="https://cosewic.ca/",
        status_verified_at=datetime.now(UTC),
    )])
    c = describe_species(db, "Least Darter")
    assert c.sar_alert is False
    assert c.conservation_status.provenance.kind is ProvenanceKind.RECORD
    assert "COSEWIC" in c.sar_reason


def test_verified_listed_species_still_flags(db):
    upsert_species_ranges(db, [_species(
        species="Redside Dace", scientific_name="Clinostomus elongatus",
        sara_status="Endangered", ontario_status="Endangered", cosewic_status="Endangered",
        status_source="SARA Schedule 1", status_source_url="https://x/",
        status_verified_at=datetime.now(UTC),
    )])
    c = describe_species(db, "Redside Dace")
    assert c.sar_alert is True
    assert "Endangered" in c.sar_reason


def test_targeting_guidance_is_withheld_while_flagged(db):
    upsert_species_ranges(db, [_species()])
    assert describe_species(db, "Least Darter").angling_note.is_empty


def test_unknown_species_fails_closed_rather_than_silent(db):
    c = describe_species(db, "Nonexistent Fish")
    assert c.found is False
    assert c.sar_alert is True


def test_verification_refuses_to_mark_verified_without_a_citation(db):
    """There must be no path that sets verified_at without a source."""
    from src.services.status_verification import apply_verified_statuses

    upsert_species_ranges(db, [_species()])
    with pytest.raises(ValueError, match="citation is required"):
        apply_verified_statuses(db, {}, source="", source_url="")


def test_verification_rejects_a_status_it_does_not_recognise(db):
    """A typo must not become an unrecognised status that clears the flag."""
    from src.services.status_verification import apply_verified_statuses

    upsert_species_ranges(db, [_species()])
    summary = apply_verified_statuses(
        db,
        {"etheostoma microperca": {"sara_status": "Probably Fine"}},
        source="Test registry", source_url="https://example.org/",
    )
    assert summary["rejected_values"]
    assert describe_species(db, "Least Darter").sar_alert is True


def test_species_absent_from_the_registry_stays_unverified(db):
    from src.services.status_verification import apply_verified_statuses

    upsert_species_ranges(db, [_species()])
    summary = apply_verified_statuses(
        db, {"some other fish": {"sara_status": "Not at Risk"}},
        source="Test registry", source_url="https://example.org/",
    )
    assert summary["verified"] == 0
    assert describe_species(db, "Least Darter").sar_alert is True
