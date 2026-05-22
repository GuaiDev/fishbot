"""Pydantic model for a single GBIF species occurrence record."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class GBIFObservation(BaseModel):
    gbif_key: int
    species: str
    common_name: str | None = None
    taxon_key: int
    lat: float
    lng: float
    observed_on: date | None = None
    country_code: str | None = None
    dataset_name: str | None = None
    basis_of_record: str
    coordinate_uncertainty_m: float | None = None
    jurisdiction: str
    ingested_at: datetime = Field(default_factory=datetime.now)
