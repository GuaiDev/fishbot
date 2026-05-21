"""Recommendations CRUD via sqlite-utils."""

import json
from datetime import datetime
from typing import Any

from sqlite_utils.db import Database

from src.models.recommendation import LureRecommendation


def insert_recommendation(
    db: Database,
    species: str,
    lat: float | None,
    lng: float | None,
    jurisdiction: str | None,
    conditions: dict[str, Any],
    recommendations: list[LureRecommendation],
) -> int:
    row = {
        "timestamp": datetime.now().isoformat(),
        "species": species,
        "lat": lat,
        "lng": lng,
        "jurisdiction": jurisdiction,
        "conditions_json": json.dumps(conditions),
        "recommendation_json": json.dumps([r.model_dump() for r in recommendations]),
        "was_used": 0,
        "trip_id": None,
    }
    return db["recommendations"].insert(row).last_pk


def get_recommendation(db: Database, rec_id: int) -> dict[str, Any] | None:
    rows = list(db["recommendations"].rows_where("id = ?", [rec_id]))
    if not rows:
        return None
    return _decode(rows[0])


def mark_used(db: Database, rec_id: int, trip_id: int | None = None) -> None:
    update: dict[str, Any] = {"was_used": 1}
    if trip_id is not None:
        update["trip_id"] = trip_id
    db["recommendations"].update(rec_id, update)


def recent_recommendations(db: Database, limit: int = 10) -> list[dict[str, Any]]:
    rows = db["recommendations"].rows_where(order_by="timestamp desc", limit=limit)
    return [_decode(r) for r in rows]


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["conditions"] = json.loads(row.get("conditions_json") or "{}")
    decoded["recommendations"] = json.loads(row.get("recommendation_json") or "[]")
    return decoded
