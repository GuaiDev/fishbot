"""CRUD for HYDAT stream temperature summaries and readings."""

import math

from sqlite_utils import Database

from src.models.stream_temperature import StreamTemperatureReading, StreamTemperatureSummary

_KM_PER_DEGREE = 111.0


def upsert_temperature_readings(db: Database, records: list[StreamTemperatureReading]) -> None:
    rows = [
        {
            "station_id": r.station_id,
            "station_name": r.station_name,
            "lat": r.lat,
            "lng": r.lng,
            "jurisdiction": r.jurisdiction,
            "year": r.year,
            "month": r.month,
            "mean_temp_c": r.mean_temp_c,
            "max_temp_c": r.max_temp_c,
            "min_temp_c": r.min_temp_c,
            "days_measured": r.days_measured,
        }
        for r in records
    ]
    db["stream_temperature_readings"].upsert_all(rows, pk=["station_id", "year", "month"])


def upsert_temperature_summaries(db: Database, summaries: list[StreamTemperatureSummary]) -> None:
    rows = [
        {
            "station_id": s.station_id,
            "station_name": s.station_name,
            "lat": s.lat,
            "lng": s.lng,
            "jurisdiction": s.jurisdiction,
            "summer_mean_c": s.summer_mean_c,
            "summer_max_c": s.summer_max_c,
            "thermal_regime": s.thermal_regime,
            "years_of_data": s.years_of_data,
            "species_notes": s.species_notes,
        }
        for s in summaries
    ]
    db["stream_temperature_summaries"].upsert_all(rows, pk="station_id")


def query_temperature_summaries(
    db: Database, lat: float, lng: float, radius_km: float
) -> list[StreamTemperatureSummary]:
    if "stream_temperature_summaries" not in db.table_names():
        return []

    deg = radius_km / _KM_PER_DEGREE
    rows = db.execute(
        """
        SELECT station_id, station_name, lat, lng, jurisdiction,
               summer_mean_c, summer_max_c, thermal_regime, years_of_data, species_notes
        FROM stream_temperature_summaries
        WHERE lat BETWEEN ? AND ?
          AND lng BETWEEN ? AND ?
        """,
        (lat - deg, lat + deg, lng - deg, lng + deg),
    ).fetchall()

    result = []
    for row in rows:
        s_lat, s_lng = row[2], row[3]
        if s_lat is None or s_lng is None:
            continue
        if _haversine_km(lat, lng, s_lat, s_lng) > radius_km:
            continue
        result.append(
            StreamTemperatureSummary(
                station_id=row[0],
                station_name=row[1],
                lat=row[2],
                lng=row[3],
                jurisdiction=row[4],
                summer_mean_c=row[5],
                summer_max_c=row[6],
                thermal_regime=row[7],
                years_of_data=row[8],
                species_notes=row[9],
            )
        )

    return sorted(
        result,
        key=lambda s: _haversine_km(lat, lng, s.lat or lat, s.lng or lng),
    )


def is_data_loaded(db: Database) -> bool:
    if "stream_temperature_summaries" not in db.table_names():
        return False
    count = db.execute("SELECT COUNT(*) FROM stream_temperature_summaries").fetchone()[0]
    return count > 0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
