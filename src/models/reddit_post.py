from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class RedditPost(BaseModel):
    post_id: str
    subreddit: str
    post_type: Literal["post", "comment"]
    title: str | None = None
    body: str
    url: str
    author: str
    score: int
    num_comments: int = 0
    parent_post_id: str | None = None
    created_utc: datetime
    extracted_species: list[str] = []
    extracted_locations: list[str] = []
    jurisdiction: str | None = None
    ingested_at: datetime

    @field_validator("post_id")
    @classmethod
    def strip_type_prefix(cls, v: str) -> str:
        for prefix in ("t3_", "t1_"):
            if v.startswith(prefix):
                return v[3:]
        return v
