"""Pydantic model for CABIN benthic macroinvertebrate site-visit aggregates."""

from pydantic import BaseModel


class BenthicSample(BaseModel):
    site_visit_id: str  # SiteVisitID — primary key
    site_code: str  # Site
    site_name: str | None = None
    lat: float | None = None
    lng: float | None = None
    jurisdiction: str = "CA-ON"
    sampled_year: int
    sampled_julian_day: int | None = None
    stream_order: int | None = None
    local_basin: str | None = None
    ept_richness: int  # distinct EPT genus/family taxa
    ept_count: float  # scaled EPT abundance
    total_count: float  # scaled total abundance
    ept_proportion: float  # ept_count / total_count
    total_taxa_richness: int  # distinct taxa across all orders
    habitat_quality: str  # "high" | "moderate" | "impaired"
