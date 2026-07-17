"""Catch CRUD — one row per species caught at a stop.

Distinct from stops.species_caught (a JSON array kept for backward
compatibility with existing readers). catches gives each species its own
row so it can carry its own photo, count, size, and bait going forward.
"""

import json
from typing import Any

from sqlite_utils.db import Database


def insert_catch(
    db: Database,
    *,
    stop_id: int,
    session_id: int,
    user_id: int,
    species: str,
    count: int | None = None,
    biggest_size: str | None = None,
    bait: str | None = None,
    photo_path: str | None = None,
    photo_url: str | None = None,
    photo_lat: float | None = None,
    photo_lng: float | None = None,
    photo_taken_at: str | None = None,
    species_confirmed: bool = True,
    suggested_species: list[dict[str, str]] | None = None,
) -> int:
    """Insert a catch row.

    species_confirmed defaults to True — direct inserts (tests, any future
    manual-entry path) represent already-trusted data. The NL-parsed/photo-
    suggested logging path (trip_logger.log_session) explicitly passes
    species_confirmed=False with suggested_species populated, since that's
    the one path where the species is a fallible AI suggestion rather than
    a human-entered fact — see the FishDex hallucination fix in fishdex.py.
    """
    return db["catches"].insert(
        {
            "stop_id": stop_id,
            "session_id": session_id,
            "user_id": user_id,
            "species": species,
            "count": count,
            "biggest_size": biggest_size,
            "bait": bait,
            "photo_path": photo_path,
            "photo_url": photo_url,
            "photo_lat": photo_lat,
            "photo_lng": photo_lng,
            "photo_taken_at": photo_taken_at,
            "species_confirmed": int(species_confirmed),
            "suggested_species": json.dumps(suggested_species) if suggested_species else None,
        }
    ).last_pk  # type: ignore[return-value]


def get_all_catches_for_user(
    db: Database, user_id: int, confirmed_only: bool = False
) -> list[dict[str, Any]]:
    if confirmed_only:
        return list(
            db["catches"].rows_where(
                "user_id = ? AND species_confirmed = 1", [user_id], order_by="id"
            )
        )
    return list(db["catches"].rows_where("user_id = ?", [user_id], order_by="id"))


def get_pending_catches_for_user(db: Database, user_id: int) -> list[dict[str, Any]]:
    """Catches logged but not yet confirmed by the user — species_caught was
    parser/vision-suggested, not human-confirmed fact."""
    return list(
        db["catches"].rows_where(
            "user_id = ? AND species_confirmed = 0", [user_id], order_by="id desc"
        )
    )


def confirm_catch_species(db: Database, catch_id: int, user_id: int, species: str) -> bool:
    """Commit the user's confirmed/corrected species. Returns False if the
    catch doesn't exist or belongs to another user."""
    from datetime import datetime

    row = next(iter(db["catches"].rows_where("id = ? AND user_id = ?", [catch_id, user_id])), None)
    if not row:
        return False
    db["catches"].update(
        catch_id,
        {
            "species": species,
            "species_confirmed": 1,
            "confirmed_at": datetime.now().isoformat(),
        },
    )
    return True


def get_catches_for_session(db: Database, session_id: int) -> list[dict[str, Any]]:
    return list(
        db["catches"].rows_where(
            "session_id = ?", [session_id], order_by="id"
        )
    )


def get_catches_for_sessions(
    db: Database, session_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Return {session_id: [catch, ...]} for a batch of sessions, one query."""
    if not session_ids:
        return {}
    placeholders = ",".join("?" for _ in session_ids)
    rows = db.execute(
        f"SELECT * FROM catches WHERE session_id IN ({placeholders}) ORDER BY id",
        session_ids,
    ).fetchall()
    cols = [c[0] for c in db.execute("SELECT * FROM catches LIMIT 0").description]
    by_session: dict[int, list[dict[str, Any]]] = {sid: [] for sid in session_ids}
    for r in rows:
        row = dict(zip(cols, r))
        by_session.setdefault(row["session_id"], []).append(row)
    return by_session
