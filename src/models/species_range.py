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


class SpeciesAtRisk(BaseModel):
    species: str
    scientific_name: str | None = None
    sara_status: SarStatus
    ontario_status: SarStatus | None = None
    is_protected: bool  # True when sara_status is Threatened or Endangered
    handling_guidance: str
    report_url: str | None = None
