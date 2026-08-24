"""Pydantic models for species native range and Species at Risk status."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SarStatus = Literal[
    "Not at Risk",
    "Special Concern",
    "Threatened",
    "Endangered",
    "Extirpated",
    "No Status",
]


class SpeciesRange(BaseModel):
    species: str  # title-case common name; used as primary key
    scientific_name: str | None = None
    native_to_ontario: bool
    native_to_great_lakes: bool
    introduced: bool = False
    extirpated_from_ontario: bool = False
    general_range: str
    habitat_notes: str | None = None
    jurisdictions_present: list[str] = Field(default_factory=list)
    sara_status: SarStatus | None = None
    ontario_status: SarStatus | None = None
    cosewic_status: str | None = None
    fishing_notes: str | None = None
    last_updated: datetime = Field(default_factory=datetime.now)

    # ── status provenance ─────────────────────────────────────────────────────
    # The conservation statuses in this file were generated, not sourced. Until
    # a species is checked against COSEWIC or the SARA registry these three
    # fields stay empty, and `status_is_verified` stays False — which makes the
    # SAR check fail closed rather than trusting an unattributed "Not at Risk".
    status_source: str | None = None
    """e.g. 'COSEWIC 2023 assessment', 'SARA Schedule 1'. None = unverified."""

    status_source_url: str | None = None

    status_assessed_on: str | None = None
    """When the registry made the assessment, as published.

    Kept as a string, not a date: COSEWIC publishes month precision
    ("2012-05"), and coercing that to a day would invent precision the source
    did not offer. This is the date an angler actually cares about — a 1998
    "Not at Risk" and a 2023 one are not the same reassurance — and it is
    years away from `status_last_checked_at` below."""

    status_last_checked_at: datetime | None = None
    """When we last read this status out of a registry export.

    Not when the registry made its assessment, and not when the value last
    changed — re-applying the same export moves this date and leaves the
    status alone, which is correct: checking again is a real event. It was
    called `status_verified_at`, which claimed the second of those three
    things while recording the first."""

    @property
    def status_is_verified(self) -> bool:
        """True only when a real registry has been cited for this species."""
        return bool(self.status_source and self.status_last_checked_at)


class SpeciesAtRisk(BaseModel):
    species: str
    scientific_name: str | None = None
    sara_status: SarStatus
    ontario_status: SarStatus | None = None
    is_protected: bool  # True when sara_status is Threatened or Endangered
    handling_guidance: str
    report_url: str | None = None
