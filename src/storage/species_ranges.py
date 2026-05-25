"""Species range and SAR CRUD via sqlite-utils."""

import json
from typing import Any

from sqlite_utils.db import Database

from src.models.species_range import SpeciesAtRisk, SpeciesRange

_PROTECTED_STATUSES = {"Threatened", "Endangered"}
_AT_RISK_STATUSES = {"Threatened", "Endangered", "Special Concern", "Extirpated"}


def upsert_species_ranges(db: Database, ranges: list[SpeciesRange]) -> None:
    rows = [_to_row(r) for r in ranges]
    db["species_ranges"].upsert_all(rows, pk="species")


def query_species_range(db: Database, species: str) -> SpeciesRange | None:
    term = species.strip().lower()
    rows = list(
        db["species_ranges"].rows_where(
            "LOWER(species) LIKE ?",
            [f"%{term}%"],
            limit=1,
        )
    )
    if not rows:
        return None
    return _row_to_range(rows[0])


def query_sar_species(db: Database, jurisdiction: str | None = None) -> list[SpeciesAtRisk]:
    status_placeholders = ",".join("?" * len(_AT_RISK_STATUSES))
    params: list[Any] = list(_AT_RISK_STATUSES)

    where = f"(sara_status IN ({status_placeholders}) OR ontario_status IN ({status_placeholders}))"
    params = list(_AT_RISK_STATUSES) + list(_AT_RISK_STATUSES)

    if jurisdiction:
        where += " AND jurisdictions_present LIKE ?"
        params.append(f"%{jurisdiction}%")

    rows = list(db["species_ranges"].rows_where(where, params))
    return [_row_to_sar(r) for r in rows]


def is_species_at_risk(db: Database, species: str) -> bool:
    sr = query_species_range(db, species)
    if sr is None:
        return False
    return (sr.sara_status in _PROTECTED_STATUSES) or (sr.ontario_status in _PROTECTED_STATUSES)


def _to_row(r: SpeciesRange) -> dict[str, Any]:
    return {
        "species": r.species,
        "scientific_name": r.scientific_name,
        "native_to_ontario": int(r.native_to_ontario),
        "native_to_great_lakes": int(r.native_to_great_lakes),
        "introduced": int(r.introduced),
        "extirpated_from_ontario": int(r.extirpated_from_ontario),
        "general_range": r.general_range,
        "habitat_notes": r.habitat_notes,
        "jurisdictions_present": json.dumps(r.jurisdictions_present),
        "sara_status": r.sara_status,
        "ontario_status": r.ontario_status,
        "cosewic_status": r.cosewic_status,
        "fishing_notes": r.fishing_notes,
        "last_updated": r.last_updated.isoformat(),
    }


def _row_to_range(row: dict[str, Any]) -> SpeciesRange:
    d = dict(row)
    d["native_to_ontario"] = bool(d["native_to_ontario"])
    d["native_to_great_lakes"] = bool(d["native_to_great_lakes"])
    d["introduced"] = bool(d["introduced"])
    d["extirpated_from_ontario"] = bool(d["extirpated_from_ontario"])
    d["jurisdictions_present"] = json.loads(d["jurisdictions_present"] or "[]")
    return SpeciesRange.model_validate(d)


def _row_to_sar(row: dict[str, Any]) -> SpeciesAtRisk:
    sara = row.get("sara_status") or ""
    ontario = row.get("ontario_status")
    is_protected = sara in _PROTECTED_STATUSES or (
        ontario is not None and ontario in _PROTECTED_STATUSES
    )

    # Use the more severe of the two statuses as the canonical sara_status for the SAR model
    effective_sara = sara if sara else (ontario or "No Status")
    if effective_sara not in {
        "Not at Risk",
        "Special Concern",
        "Threatened",
        "Endangered",
        "Extirpated",
        "No Status",
    }:
        effective_sara = "No Status"

    guidance = row.get("fishing_notes") or (
        "Release immediately. Do not target. Report sightings to MNRF at 1-877-TIPS-MNR."
    )

    return SpeciesAtRisk(
        species=row["species"],
        scientific_name=row.get("scientific_name"),
        sara_status=effective_sara,  # type: ignore[arg-type]
        ontario_status=ontario,  # type: ignore[arg-type]
        is_protected=is_protected,
        handling_guidance=guidance,
        report_url=None,
    )
