"""Bird observation CRUD via sqlite-utils."""

from datetime import date, datetime, timedelta
from typing import Any

from sqlite_utils.db import Database

from src.models.bird_observation import BirdObservation

_KM_PER_DEGREE = 111.0


def upsert_bird_observations(db: Database, obs: list[BirdObservation]) -> None:
    rows = [_to_row(o) for o in obs]
    db["bird_observations"].upsert_all(rows, pk="obs_id")


def query_bird_observations(
    db: Database,
    lat: float,
    lng: float,
    radius_km: float,
    days_back: int = 30,
    species_code: str | None = None,
) -> list[BirdObservation]:
    if "bird_observations" not in db.table_names():
        return []

    deg = radius_km / _KM_PER_DEGREE
    since = (date.today() - timedelta(days=days_back)).isoformat()

    where = "lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? AND observed_on >= ?"
    params: list[Any] = [lat - deg, lat + deg, lng - deg, lng + deg, since]

    if species_code:
        where += " AND species_code = ?"
        params.append(species_code)

    rows = db["bird_observations"].rows_where(where, params, order_by="observed_on desc")
    return [_from_row(r) for r in rows]


def _to_row(o: BirdObservation) -> dict[str, Any]:
    return {
        "obs_id": o.obs_id,
        "species_code": o.species_code,
        "common_name": o.common_name,
        "scientific_name": o.scientific_name,
        "lat": o.lat,
        "lng": o.lng,
        "observed_on": o.observed_on.isoformat(),
        "how_many": o.how_many,
        "location_name": o.location_name,
        "jurisdiction": o.jurisdiction,
        "piscivore_significance": o.piscivore_significance,
        "fetched_at": o.fetched_at.isoformat(),
    }


def _from_row(row: dict[str, Any]) -> BirdObservation:
    decoded = dict(row)
    decoded["observed_on"] = date.fromisoformat(row["observed_on"])
    decoded["fetched_at"] = datetime.fromisoformat(row["fetched_at"])
    return BirdObservation.model_validate(decoded)
