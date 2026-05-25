"""Geology unit storage via sqlite-utils — nearest-centroid point lookup."""

from typing import Any

from sqlite_utils.db import Database

from src.models.geology_unit import GeologyUnit


def upsert_geology_units(db: Database, units: list[GeologyUnit]) -> None:
    rows = [_to_row(u) for u in units]
    db["geology_units"].upsert_all(rows, pk="unit_id")


def query_substrate_at_point(db: Database, lat: float, lng: float) -> GeologyUnit | None:
    """Return the geology unit whose centroid is nearest to (lat, lng).

    Pre-filters to ±1° bbox then picks by minimum Euclidean distance in
    degree-space.  Sufficient precision for a 0.5°×0.5° tile grid.
    """
    if "geology_units" not in db.table_names():
        return None
    rows = list(
        db["geology_units"].rows_where(
            "centroid_lat BETWEEN ? AND ? AND centroid_lng BETWEEN ? AND ?",
            [lat - 1.0, lat + 1.0, lng - 1.0, lng + 1.0],
        )
    )
    if not rows:
        return None

    def _dist_sq(row: dict[str, Any]) -> float:
        return (row["centroid_lat"] - lat) ** 2 + (row["centroid_lng"] - lng) ** 2

    return GeologyUnit.model_validate(min(rows, key=_dist_sq))


def query_substrate_area(
    db: Database, lat: float, lng: float, radius_km: float
) -> list[GeologyUnit]:
    """Return geology units with centroids within radius_km of (lat, lng)."""
    if "geology_units" not in db.table_names():
        return []
    deg = radius_km / 111.0
    rows = db["geology_units"].rows_where(
        "centroid_lat BETWEEN ? AND ? AND centroid_lng BETWEEN ? AND ?",
        [lat - deg, lat + deg, lng - deg, lng + deg],
    )
    return [GeologyUnit.model_validate(dict(r)) for r in rows]


def _to_row(u: GeologyUnit) -> dict[str, Any]:
    return {
        "unit_id": u.unit_id,
        "tile_id": u.tile_id,
        "unit_code": u.unit_code,
        "unit_name": u.unit_name,
        "primary_material": u.primary_material,
        "substrate_class": u.substrate_class,
        "jurisdiction": u.jurisdiction,
        "centroid_lat": u.centroid_lat,
        "centroid_lng": u.centroid_lng,
        "bbox_minx": u.bbox_minx,
        "bbox_miny": u.bbox_miny,
        "bbox_maxx": u.bbox_maxx,
        "bbox_maxy": u.bbox_maxy,
    }
