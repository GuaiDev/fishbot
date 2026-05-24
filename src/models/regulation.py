"""Pydantic model for a parsed MNRF regulation chunk (one per FMZ zone)."""

from pydantic import BaseModel, field_validator


class RegulationChunk(BaseModel):
    zone: int
    jurisdiction: str = "CA-ON"
    regulation_year: int
    raw_text: str
    char_count: int = 0
    source_url: str
    ingested_at: str

    @field_validator("zone")
    @classmethod
    def zone_in_range(cls, v: int) -> int:
        if not 1 <= v <= 20:
            raise ValueError(f"Ontario FMZ zone must be 1-20, got {v}")
        return v

    @field_validator("char_count", mode="before")
    @classmethod
    def compute_char_count(cls, v: int, info: object) -> int:
        if v == 0 and hasattr(info, "data") and "raw_text" in info.data:
            return len(info.data["raw_text"])
        return v

    model_config = {"populate_by_name": True}
