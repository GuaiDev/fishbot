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


# ── the join between a registry export and the corpus ─────────────────────────
#
# All twelve rows of a real COSEWIC export verified nothing, every run, and the
# summary said "left unverified: 69" — indistinguishable from an export that
# simply did not cover those species. Nothing in this file could catch it: every
# test above builds its registry dict by hand, so the key-construction code that
# actually failed was never exercised.


def _write_csv(tmp_path, header: str, *rows: str):
    path = tmp_path / "registry.csv"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def test_common_name_export_matches_a_corpus_keyed_by_latin(db, tmp_path):
    """The actual failure: 12 rows, 69 rows, zero possible matches.

    Both sides used `scientific_name or species`, which looks symmetrical. It is
    not — the fallback fires only where the column is missing, so an export
    carrying common names alone keyed 'least darter' while the corpus row keyed
    'etheostoma microperca'.
    """
    from src.services.status_verification import (
        apply_verified_statuses,
        load_registry_file,
    )

    upsert_species_ranges(db, [_species()])
    path = _write_csv(
        tmp_path,
        "species,cosewic_status",
        "Least Darter,Not at Risk",
    )

    summary = apply_verified_statuses(
        db, load_registry_file(path), source="COSEWIC 2024", source_url="https://x"
    )
    assert summary["verified"] == 1
    assert summary["skipped_not_in_registry"] == 0


def test_latin_only_export_matches_too(db, tmp_path):
    """The join must not depend on which column either side happens to have."""
    from src.services.status_verification import (
        apply_verified_statuses,
        load_registry_file,
    )

    upsert_species_ranges(db, [_species()])
    path = _write_csv(
        tmp_path,
        "scientific_name,cosewic_status",
        "Etheostoma microperca,Not at Risk",
    )

    summary = apply_verified_statuses(
        db, load_registry_file(path), source="COSEWIC 2024", source_url="https://x"
    )
    assert summary["verified"] == 1


def test_registry_entry_count_is_species_not_keys(db, tmp_path):
    """One row indexed under both its names is one species, not two."""
    from src.services.status_verification import (
        load_registry_file,
        registry_species_count,
    )

    path = _write_csv(
        tmp_path,
        "species,scientific_name,cosewic_status",
        "Least Darter,Etheostoma microperca,Not at Risk",
    )
    registry = load_registry_file(path)
    assert len(registry) == 2, "indexed under both names"
    assert registry_species_count(registry) == 1


def test_registry_rows_that_matched_nothing_are_named(db, tmp_path):
    """Silence about an unmatched export entry is how a typo survives."""
    from src.services.status_verification import (
        apply_verified_statuses,
        load_registry_file,
    )

    upsert_species_ranges(db, [_species()])
    path = _write_csv(
        tmp_path,
        "species,cosewic_status",
        "Least Darter,Not at Risk",
        "Leest Darter,Endangered",
    )

    summary = apply_verified_statuses(
        db, load_registry_file(path), source="COSEWIC 2024", source_url="https://x"
    )
    assert summary["verified"] == 1
    assert summary["unmatched_registry_entries"] == ["Leest Darter"]


def test_a_total_join_failure_is_distinguishable_from_a_narrow_export(db, tmp_path):
    """Zero verified is legitimate here, so the counts have to say which zero."""
    from src.services.status_verification import (
        apply_verified_statuses,
        load_registry_file,
    )

    upsert_species_ranges(db, [_species()])
    path = _write_csv(
        tmp_path,
        "species,cosewic_status",
        "Northern Pike,Not at Risk",
    )

    summary = apply_verified_statuses(
        db, load_registry_file(path), source="COSEWIC 2024", source_url="https://x"
    )
    assert summary["verified"] == 0
    assert summary["registry_entries"] == 1
    assert summary["skipped_not_in_registry"] == 1
    assert summary["unmatched_registry_entries"] == ["Northern Pike"]


# ── the citation must not cover statuses the registry never supplied ──────────


def test_statuses_the_registry_is_silent_on_are_cleared_not_inherited(db, tmp_path):
    """Otherwise a generated status ends up sitting under a real citation.

    Redside Dace would have rendered "Listed: Endangered, Threatened (source:
    COSEWIC)" from a COSEWIC export that only ever said Endangered — the
    Threatened came from the model. Generated content wearing a record's
    authority is the exact defect this path exists to remove.
    """
    from src.services.status_verification import (
        apply_verified_statuses,
        load_registry_file,
    )

    upsert_species_ranges(
        db,
        [
            _species(
                species="Redside Dace",
                scientific_name="Clinostomus elongatus",
                sara_status="Threatened",
                ontario_status="Endangered",
                cosewic_status="Endangered",
            )
        ],
    )
    path = _write_csv(
        tmp_path,
        "species,cosewic_status",
        "Redside Dace,Endangered",
    )

    summary = apply_verified_statuses(
        db, load_registry_file(path), source="COSEWIC 2024", source_url="https://x"
    )
    assert summary["verified"] == 1
    assert summary["cleared_generated_statuses"] == [
        "Redside Dace: sara_status, ontario_status"
    ]

    row = db["species_ranges"].get("Redside Dace")
    assert row["cosewic_status"] == "Endangered"
    assert row["sara_status"] is None
    assert row["ontario_status"] is None

    c = describe_species(db, "Redside Dace")
    assert c.status_known_listed is True
    assert "Threatened" not in c.sar_reason, "the model's status must not be cited"
