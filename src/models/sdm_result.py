"""Pydantic models for SDM prediction output and trained model metadata."""

from datetime import datetime

from pydantic import BaseModel, Field


class SDMResult(BaseModel):
    ogf_id: int
    species: str
    presence_probability: float
    confidence_tier: str  # "high" | "medium" | "low"
    model_version: str
    predicted_at: datetime = Field(default_factory=datetime.now)


class SDMModelMeta(BaseModel):
    species: str
    species_slug: str
    n_presence: int
    n_pseudo_absence: int
    oob_score: float | None
    feature_names: list[str]
    feature_importances: dict[str, float]
    training_date: datetime = Field(default_factory=datetime.now)
    model_path: str
    confidence_tier: str  # "high" (>=50) | "medium" (>=15) | "low" (>=5)
