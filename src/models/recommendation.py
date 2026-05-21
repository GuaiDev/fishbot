from typing import Literal

from pydantic import BaseModel, field_validator


class LureRecommendation(BaseModel):
    lure_type: str
    color: str
    size_range: str
    technique: str
    retrieve_speed: Literal["slow", "medium", "fast", "variable"]
    target_depth_range: str
    conditions_matched: list[str]
    confidence: Literal["high", "medium", "low"]
    reasoning: str

    @field_validator("reasoning")
    @classmethod
    def reasoning_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reasoning must not be empty")
        return v
