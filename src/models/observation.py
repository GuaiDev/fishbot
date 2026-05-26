"""Pydantic model for a single iNaturalist fish observation."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class Observation(BaseModel):
    observation_id: int
    species: str
    common_name: str | None = None
    taxon_id: int | None = None
    lat: float
    lng: float
    observed_on: date
    quality_grade: str
    photo_url: str | None = None
    observer: str | None = None
    place_guess: str | None = None
    jurisdiction: str
    ingested_at: datetime = Field(default_factory=datetime.now)
    # iNaturalist geoprivacy — "open", "obscured", or "private"
    geoprivacy: str | None = "open"
    is_obscured: bool = False
    # 22.0 km for obscured observations (iNat randomises within ~0.2° box)
    obscuration_radius_km: float | None = None
