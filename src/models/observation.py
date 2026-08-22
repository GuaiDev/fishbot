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
    # origin system: "iNaturalist", "FISS", etc.
    source: str = "iNaturalist"

    # ── licensing and attribution ─────────────────────────────────────────────
    # iNaturalist licenses the observation record and its photos SEPARATELY, so
    # both are captured. A None license is not "unknown" — it is the platform's
    # default of all-rights-reserved, i.e. the most restrictive case, and must
    # not be conflated with a missing field.
    license_code: str | None = None
    """Observation record licence, e.g. 'cc0', 'cc-by', 'cc-by-nc'. None = ARR."""

    photo_license_code: str | None = None
    """Licence on the first photo. Often differs from the record licence."""

    observer_id: int | None = None
    """Stable numeric user id. Logins can be changed; this cannot."""

    uri: str | None = None
    """Canonical observation URL. Required to attribute a CC-BY work."""
