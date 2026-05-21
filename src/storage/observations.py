"""Observation CRUD via sqlite-utils."""

from datetime import date, datetime, timedelta
from typing import Any

from sqlite_utils.db import Database

from src.models.observation import Observation

_KM_PER_DEGREE = 111.0


def upsert_observations(db: Database, observations: list[Observation]) -> None:
    rows = [_obs_to_row(o) for o in observations]
    db["observations"].upsert_all(rows, pk="observation_id")


def query_observations(
    db: Database,
    lat: float,
    lng: float,
    radius_km: float,
    days_back: int,
    species_filter: str | None = None,
) -> list[Observation]:
    deg = radius_km / _KM_PER_DEGREE
    since = (date.today() - timedelta(days=days_back)).isoformat()

    where = "lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? AND observed_on >= ?"
    params: list[Any] = [lat - deg, lat + deg, lng - deg, lng + deg, since]

    if species_filter:
        where += " AND (LOWER(species) LIKE ? OR LOWER(common_name) LIKE ?)"
        pattern = f"%{species_filter.lower()}%"
        params += [pattern, pattern]

    rows = db["observations"].rows_where(where, params, order_by="observed_on desc")
    return [_row_to_obs(r) for r in rows]


def _obs_to_row(obs: Observation) -> dict[str, Any]:
    return {
        "observation_id": obs.observation_id,
        "species": obs.species,
        "common_name": obs.common_name,
        "taxon_id": obs.taxon_id,
        "lat": obs.lat,
        "lng": obs.lng,
        "observed_on": obs.observed_on.isoformat(),
        "quality_grade": obs.quality_grade,
        "photo_url": obs.photo_url,
        "observer": obs.observer,
        "place_guess": obs.place_guess,
        "jurisdiction": obs.jurisdiction,
        "ingested_at": obs.ingested_at.isoformat(),
    }


def _row_to_obs(row: dict[str, Any]) -> Observation:
    decoded = dict(row)
    decoded["observed_on"] = date.fromisoformat(row["observed_on"])
    decoded["ingested_at"] = datetime.fromisoformat(row["ingested_at"])
    return Observation.model_validate(decoded)
