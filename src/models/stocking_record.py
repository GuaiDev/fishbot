"""Pydantic model for MNRF fish stocking records."""

from datetime import datetime

from pydantic import BaseModel


class StockingRecord(BaseModel):
    record_id: str
    waterbody_name: str
    waterbody_code: str | None = None
    municipality: str | None = None  # Geographic_Township in MNRF CSV
    county: str | None = None  # MNRF_District in MNRF CSV
    lat: float | None = None
    lng: float | None = None
    jurisdiction: str = "CA-ON"
    species: str
    species_code: str | None = None  # not published in current MNRF CSV
    year: int
    month: int | None = None  # not published in current MNRF CSV
    quantity: int | None = None
    life_stage: str | None = None
    stocking_purpose: str | None = None  # not published in current MNRF CSV
    stocked_at: datetime  # datetime(year, month or 1, 1)
