"""SQLite database setup for trips and future tables."""

from pathlib import Path

from sqlite_utils import Database

DB_PATH = Path("data/fishing.db")


def get_db(path: Path | None = None) -> Database:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    db = Database(p)
    ensure_schema(db)
    return db


def ensure_schema(db: Database) -> None:
    if "trips" not in db.table_names():
        db["trips"].create(
            {
                "id": int,
                "status": str,
                "date": str,
                "planned_for": str,
                "jurisdiction": str,
                "location_name": str,
                "lat": float,
                "lng": float,
                "species_caught": str,
                "conditions": str,
                "gear_used": str,
                "notes": str,
                "what_worked": str,
                "what_didnt": str,
                "created_at": str,
                "updated_at": str,
            },
            pk="id",
        )

    if "observations" not in db.table_names():
        db["observations"].create(
            {
                "observation_id": int,
                "species": str,
                "common_name": str,
                "taxon_id": int,
                "lat": float,
                "lng": float,
                "observed_on": str,
                "quality_grade": str,
                "photo_url": str,
                "observer": str,
                "place_guess": str,
                "jurisdiction": str,
                "ingested_at": str,
            },
            pk="observation_id",
        )

    if "recommendations" not in db.table_names():
        db["recommendations"].create(
            {
                "id": int,
                "timestamp": str,
                "species": str,
                "lat": float,
                "lng": float,
                "jurisdiction": str,
                "conditions_json": str,
                "recommendation_json": str,
                "was_used": int,
                "trip_id": int,
            },
            pk="id",
        )
