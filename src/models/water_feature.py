from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WaterFeature(BaseModel):
    osm_id: str  # e.g. "way/12345"
    feature_type: Literal[
        "lake", "river", "stream", "pond", "reservoir",
        "wetland", "canal", "ditch", "drain", "bay",
    ]
    name: str | None
    lat: float
    lng: float
    jurisdiction: str
    area_m2: float | None
    tags: dict
    fetched_at: datetime = Field(default_factory=datetime.now)


class AccessPoint(BaseModel):
    osm_id: str
    access_type: Literal[
        "boat_launch", "parking", "trail_head", "fishing_spot",
        "public_land", "conservation_area", "park",
    ]
    name: str | None
    lat: float
    lng: float
    jurisdiction: str
    tags: dict
    fetched_at: datetime = Field(default_factory=datetime.now)
