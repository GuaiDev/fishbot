from typing import Literal

from pydantic import BaseModel


class StreamTemperatureReading(BaseModel):
    station_id: str
    station_name: str | None
    lat: float | None
    lng: float | None
    jurisdiction: str
    year: int
    month: int
    mean_temp_c: float | None
    max_temp_c: float | None
    min_temp_c: float | None
    days_measured: int | None


class StreamTemperatureSummary(BaseModel):
    station_id: str
    station_name: str | None
    lat: float | None
    lng: float | None
    jurisdiction: str
    summer_mean_c: float | None  # mean of July+August means across all available years
    summer_max_c: float | None  # mean of July+August maxima across all available years
    thermal_regime: Literal["coldwater", "coolwater", "warmwater", "unknown"]
    years_of_data: int
    species_notes: str
