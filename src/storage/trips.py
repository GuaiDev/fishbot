"""Trip CRUD via sqlite-utils.

Trips serialize to a single row each. JSON columns (species_caught, conditions,
gear_used) are stored as JSON-encoded strings and round-tripped through Pydantic.
"""

import json
from datetime import datetime
from typing import Any

from sqlite_utils.db import Database

from src.models.catch import Catch
from src.models.trip import Trip


def insert_trip(db: Database, trip: Trip) -> int:
    row = _trip_to_row(trip)
    row.pop("id", None)
    return db["trips"].insert(row).last_pk


def get_trip(db: Database, trip_id: int) -> Trip | None:
    rows = list(db["trips"].rows_where("id = ?", [trip_id]))
    if not rows:
        return None
    return _row_to_trip(rows[0])


def update_trip(db: Database, trip_id: int, **fields: Any) -> None:
    encoded: dict[str, Any] = {}
    for key, value in fields.items():
        if key in {"species_caught", "conditions", "gear_used"}:
            encoded[key] = json.dumps(_to_jsonable(value))
        else:
            encoded[key] = value
    encoded["updated_at"] = datetime.now().isoformat()
    db["trips"].update(trip_id, encoded)


def recent_trips(db: Database, limit: int = 5, status: str = "completed") -> list[Trip]:
    rows = db["trips"].rows_where("status = ?", [status], order_by="date desc", limit=limit)
    return [_row_to_trip(r) for r in rows]


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, list):
        return [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value
        ]
    return value


def _trip_to_row(trip: Trip) -> dict[str, Any]:
    row = trip.model_dump(mode="json")
    row["species_caught"] = json.dumps([c.model_dump(mode="json") for c in trip.species_caught])
    row["conditions"] = json.dumps(trip.conditions)
    row["gear_used"] = json.dumps(trip.gear_used)
    return row


def _row_to_trip(row: dict[str, Any]) -> Trip:
    decoded = dict(row)
    decoded["species_caught"] = [
        Catch.model_validate(c) for c in json.loads(row.get("species_caught") or "[]")
    ]
    decoded["conditions"] = json.loads(row.get("conditions") or "{}")
    decoded["gear_used"] = json.loads(row.get("gear_used") or "[]")
    return Trip.model_validate(decoded)
