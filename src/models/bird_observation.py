"""Pydantic model for an eBird piscivore observation."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class BirdObservation(BaseModel):
    obs_id: str  # f"{subId}_{speciesCode}" — unique across species
    species_code: str  # eBird species code, e.g. "grbher3"
    common_name: str
    scientific_name: str | None = None
    lat: float
    lng: float
    observed_on: date
    how_many: int | None = None  # null when birder noted presence but not count
    location_name: str | None = None
    jurisdiction: str
    piscivore_significance: str  # why this species indicates fish presence
    fetched_at: datetime = Field(default_factory=datetime.now)
