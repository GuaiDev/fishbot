"""Stocking record CRUD via sqlite-utils."""

from datetime import datetime
from typing import Any

from sqlite_utils.db import Database

from src.models.stocking_record import StockingRecord

_KM_PER_DEGREE = 111.0


def upsert_stocking_records(db: Database, records: list[StockingRecord]) -> None:
    rows = [_to_row(r) for r in records]
    db["stocking_records"].upsert_all(rows, pk="record_id")


def query_stocking(
    db: Database,
    waterbody_name: str | None = None,
    species: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float | None = None,
) -> list[StockingRecord]:
    conditions: list[str] = []
    params: list[Any] = []

    if waterbody_name:
        conditions.append("LOWER(waterbody_name) LIKE ?")
        params.append(f"%{waterbody_name.lower()}%")

    if species:
        conditions.append("LOWER(species) LIKE ?")
        params.append(f"%{species.lower()}%")

    if year_from is not None:
        conditions.append("year >= ?")
        params.append(year_from)

    if year_to is not None:
        conditions.append("year <= ?")
        params.append(year_to)

    if lat is not None and lng is not None and radius_km is not None:
        deg = radius_km / _KM_PER_DEGREE
        conditions.append("lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?")
        params += [lat - deg, lat + deg, lng - deg, lng + deg]

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = db["stocking_records"].rows_where(where, params, order_by="year desc")
    return [_row_to_record(r) for r in rows]


def get_stocking_summary(db: Database, waterbody_name: str) -> dict:
    rows = list(
        db["stocking_records"].rows_where(
            "LOWER(waterbody_name) LIKE ?",
            [f"%{waterbody_name.lower()}%"],
        )
    )
    if not rows:
        return {
            "waterbody_name": waterbody_name,
            "species_stocked": [],
            "most_recent_year": None,
            "total_quantity": None,
            "life_stages": [],
            "event_count": 0,
        }

    species_stocked = sorted({r["species"] for r in rows if r.get("species")})
    life_stages = sorted({r["life_stage"] for r in rows if r.get("life_stage")})
    years = [r["year"] for r in rows if r.get("year")]
    quantities = [r["quantity"] for r in rows if r.get("quantity") is not None]

    return {
        "waterbody_name": waterbody_name,
        "species_stocked": species_stocked,
        "most_recent_year": max(years) if years else None,
        "total_quantity": sum(quantities) if quantities else None,
        "life_stages": life_stages,
        "event_count": len(rows),
    }


def _to_row(r: StockingRecord) -> dict[str, Any]:
    return {
        "record_id": r.record_id,
        "waterbody_name": r.waterbody_name,
        "waterbody_code": r.waterbody_code,
        "municipality": r.municipality,
        "county": r.county,
        "lat": r.lat,
        "lng": r.lng,
        "jurisdiction": r.jurisdiction,
        "species": r.species,
        "species_code": r.species_code,
        "year": r.year,
        "month": r.month,
        "quantity": r.quantity,
        "life_stage": r.life_stage,
        "stocking_purpose": r.stocking_purpose,
        "stocked_at": r.stocked_at.isoformat(),
    }


def _row_to_record(row: dict[str, Any]) -> StockingRecord:
    d = dict(row)
    d["stocked_at"] = datetime.fromisoformat(d["stocked_at"])
    return StockingRecord.model_validate(d)
