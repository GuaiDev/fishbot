"""Pydantic model for a parsed MNRF regulation chunk.

Most chunks are one per FMZ zone. Province-wide sections — Bait, General
Fishing Regulations, Licences — use zone 0 and carry a `section` label. They
were previously absorbed into whichever zone chunk happened to precede them in
the PDF, which buried the bait rules inside FMZ 12 where nobody would find
them.
"""

from pydantic import BaseModel, field_validator

PROVINCE_WIDE = 0
"""Sentinel zone for rules that apply everywhere in Ontario, not to one FMZ."""


class RegulationChunk(BaseModel):
    zone: int
    section: str | None = None
    """Section name for province-wide chunks, e.g. "Bait". None for zone chunks."""
    jurisdiction: str = "CA-ON"
    regulation_year: int
    raw_text: str
    char_count: int = 0
    source_url: str
    ingested_at: str

    @field_validator("zone")
    @classmethod
    def zone_in_range(cls, v: int) -> int:
        if v != PROVINCE_WIDE and not 1 <= v <= 20:
            raise ValueError(
                f"Ontario FMZ zone must be 1-20, or 0 for province-wide, got {v}"
            )
        return v

    @field_validator("char_count", mode="before")
    @classmethod
    def compute_char_count(cls, v: int, info: object) -> int:
        if v == 0 and hasattr(info, "data") and "raw_text" in info.data:
            return len(info.data["raw_text"])
        return v

    model_config = {"populate_by_name": True}
