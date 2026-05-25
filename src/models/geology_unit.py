"""Pydantic model for Ontario MRD 128 surficial geology polygon units."""

from pydantic import BaseModel


class GeologyUnit(BaseModel):
    unit_id: str          # composite: f"{tile_id}_{seq:04d}"
    tile_id: str          # e.g. "-79.5_43.5_-79_44"
    unit_code: str        # e.g. "7", "8a", "9c"
    unit_name: str        # full geological name
    primary_material: str | None = None
    substrate_class: str  # "coarse" | "fine" | "bedrock" | "organic" | "mixed"
    jurisdiction: str = "CA-ON"
    centroid_lat: float   # from Point element inside MultiGeometry
    centroid_lng: float
    bbox_minx: float
    bbox_miny: float
    bbox_maxx: float
    bbox_maxy: float
