"""Water quality reading CRUD via sqlite-utils."""

from datetime import date
from typing import Any

from sqlite_utils.db import Database

from src.models.water_quality_reading import WaterQualityReading

_KM_PER_DEGREE = 111.0


def upsert_water_quality_readings(db: Database, records: list[WaterQualityReading]) -> None:
    rows = [_to_row(r) for r in records]
    db["water_quality_readings"].upsert_all(rows, pk="record_id")


def query_water_quality(
    db: Database,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    station_id: str | None = None,
) -> list[WaterQualityReading]:
    conditions: list[str] = []
    params: list[Any] = []

    if station_id:
        conditions.append("station_id = ?")
        params.append(station_id)

    if lat is not None and lng is not None and radius_km is not None:
        deg = radius_km / _KM_PER_DEGREE
        conditions.append("lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?")
        params += [lat - deg, lat + deg, lng - deg, lng + deg]

    if date_from is not None:
        conditions.append("sampled_at >= ?")
        params.append(date_from.isoformat())

    if date_to is not None:
        conditions.append("sampled_at <= ?")
        params.append(date_to.isoformat())

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = db["water_quality_readings"].rows_where(where, params, order_by="sampled_at desc")
    return [_row_to_record(r) for r in rows]


def _to_row(r: WaterQualityReading) -> dict[str, Any]:
    return {
        "record_id": r.record_id,
        "station_id": r.station_id,
        "station_name": r.station_name,
        "lat": r.lat,
        "lng": r.lng,
        "jurisdiction": r.jurisdiction,
        "sampled_at": r.sampled_at.isoformat(),
        "do_mgl": r.do_mgl,
        "ph": r.ph,
        "temp_c": r.temp_c,
        "conductivity_us_cm": r.conductivity_us_cm,
        "turbidity_fnu": r.turbidity_fnu,
    }


def _row_to_record(row: dict[str, Any]) -> WaterQualityReading:
    d = dict(row)
    d["sampled_at"] = date.fromisoformat(d["sampled_at"])
    return WaterQualityReading.model_validate(d)
