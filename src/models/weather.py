from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class CurrentConditions(BaseModel):
    lat: float
    lng: float
    jurisdiction: str
    time: datetime
    temperature_c: float
    humidity_pct: float
    precipitation_mm: float
    wind_speed_kmh: float
    pressure_hpa: float
    cloud_cover_pct: float
    weather_code: int
    fetched_at: datetime = Field(default_factory=datetime.now)


class ForecastDay(BaseModel):
    date: date
    temp_max_c: float
    temp_min_c: float
    precipitation_sum_mm: float
    wind_speed_max_kmh: float
    weather_code: int


class WeatherForecast(BaseModel):
    lat: float
    lng: float
    jurisdiction: str
    days: list[ForecastDay]
    fetched_at: datetime = Field(default_factory=datetime.now)


class PressureTrend(BaseModel):
    lat: float
    lng: float
    jurisdiction: str
    trend: Literal["rising", "steady", "falling"]
    current_hpa: float
    delta_24h_hpa: float
    delta_48h_hpa: float
    fetched_at: datetime = Field(default_factory=datetime.now)
