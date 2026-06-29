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
    limit: int = 50,
) -> tuple[list[Observation], int]:
    """Return (observations, total_count).

    Hard cap of `limit` rows (default 50) to prevent context overflow.
    days_back applies only to iNaturalist records; survey sources (FISS, etc.)
    are always included regardless of date.
    """
    deg = radius_km / _KM_PER_DEGREE
    since = (date.today() - timedelta(days=days_back)).isoformat()

    where = (
        "lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? "
        "AND (source != 'iNaturalist' OR observed_on >= ?)"
    )
    params: list[Any] = [lat - deg, lat + deg, lng - deg, lng + deg, since]

    if species_filter:
        where += " AND (LOWER(species) LIKE ? OR LOWER(common_name) LIKE ?)"
        pattern = f"%{species_filter.lower()}%"
        params += [pattern, pattern]

    total: int = db.execute(
        f"SELECT COUNT(*) FROM observations WHERE {where}", params
    ).fetchone()[0]

    cursor = db.execute(
        f"SELECT * FROM observations WHERE {where} ORDER BY observed_on DESC LIMIT ?",
        params + [limit],
    )
    col_names = [d[0] for d in cursor.description]
    rows = [dict(zip(col_names, r)) for r in cursor.fetchall()]
    return [_row_to_obs(r) for r in rows], total


def get_obscured_observations(db: Database) -> list[Observation]:
    rows = db["observations"].rows_where("is_obscured = 1")
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
        "geoprivacy": obs.geoprivacy,
        "is_obscured": int(obs.is_obscured),
        "obscuration_radius_km": obs.obscuration_radius_km,
        "source": obs.source,
    }


def _row_to_obs(row: dict[str, Any]) -> Observation:
    decoded = dict(row)
    decoded["observed_on"] = date.fromisoformat(row["observed_on"])
    decoded["ingested_at"] = datetime.fromisoformat(row["ingested_at"])
    # Handle rows written before geoprivacy/source columns were added
    decoded.setdefault("geoprivacy", "open")
    decoded.setdefault("is_obscured", False)
    decoded.setdefault("obscuration_radius_km", None)
    decoded.setdefault("source", "iNaturalist")
    return Observation.model_validate(decoded)
