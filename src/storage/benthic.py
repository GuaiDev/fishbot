"""Benthic sample CRUD via sqlite-utils."""

from typing import Any

from sqlite_utils.db import Database

from src.models.benthic_sample import BenthicSample

_KM_PER_DEGREE = 111.0


def upsert_benthic_samples(db: Database, records: list[BenthicSample]) -> None:
    rows = [_to_row(r) for r in records]
    db["benthic_samples"].upsert_all(rows, pk="site_visit_id")


def query_benthic(
    db: Database,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[BenthicSample]:
    conditions: list[str] = []
    params: list[Any] = []

    if lat is not None and lng is not None and radius_km is not None:
        deg = radius_km / _KM_PER_DEGREE
        conditions.append("lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?")
        params += [lat - deg, lat + deg, lng - deg, lng + deg]

    if year_from is not None:
        conditions.append("sampled_year >= ?")
        params.append(year_from)

    if year_to is not None:
        conditions.append("sampled_year <= ?")
        params.append(year_to)

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = db["benthic_samples"].rows_where(where, params, order_by="sampled_year desc")
    return [_row_to_record(r) for r in rows]


def _to_row(r: BenthicSample) -> dict[str, Any]:
    return {
        "site_visit_id": r.site_visit_id,
        "site_code": r.site_code,
        "site_name": r.site_name,
        "lat": r.lat,
        "lng": r.lng,
        "jurisdiction": r.jurisdiction,
        "sampled_year": r.sampled_year,
        "sampled_julian_day": r.sampled_julian_day,
        "stream_order": r.stream_order,
        "local_basin": r.local_basin,
        "ept_richness": r.ept_richness,
        "ept_count": r.ept_count,
        "total_count": r.total_count,
        "ept_proportion": r.ept_proportion,
        "total_taxa_richness": r.total_taxa_richness,
        "habitat_quality": r.habitat_quality,
    }


def _row_to_record(row: dict[str, Any]) -> BenthicSample:
    return BenthicSample.model_validate(dict(row))
