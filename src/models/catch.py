"""A single fish caught during a trip."""

from pydantic import BaseModel


class Catch(BaseModel):
    species: str
    length_cm: float | None = None
    weight_kg: float | None = None
    photo_path: str | None = None
    released: bool = True
