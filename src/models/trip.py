"""A fishing trip — completed or planned for the future."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.catch import Catch
from src.models.jurisdiction import JurisdictionCode


class Trip(BaseModel):
    id: int | None = None
    status: Literal["planned", "completed"] = "completed"
    date: date
    planned_for: date | None = None
    jurisdiction: JurisdictionCode
    location_name: str
    lat: float | None = None
    lng: float | None = None
    species_caught: list[Catch] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    gear_used: list[str] = Field(default_factory=list)
    notes: str = ""
    what_worked: str = ""
    what_didnt: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
