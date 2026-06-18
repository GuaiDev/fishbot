"""SQLite database setup for trips and future tables."""

import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlite_utils import Database

# Respect DATA_DIR env var for Railway persistent volumes; default to local data/
DB_PATH = Path(os.environ.get("DATA_DIR", "data")) / "fishing.db"


def get_db(path: Path | None = None) -> Database:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    db = Database(p)
    ensure_schema(db)
    migrate_behavioral_insights(db)
    migrate_stops(db)
    return db


def migrate_stops(db: Database) -> None:
    """Add party_species_caught column to stops. Idempotent."""
    try:
        db.execute("ALTER TABLE stops ADD COLUMN party_species_caught TEXT")
    except Exception:
        pass  # column already exists


def migrate_behavioral_insights(db: Database) -> None:
    """Add location and recommendation fields to behavioral_insights.

    Safe to run multiple times — skips columns that already exist.
    """
    new_columns = [
        ("lat", "REAL"),
        ("lng", "REAL"),
        ("recommendation", "TEXT"),
        ("condition_season", "TEXT"),
        ("location_name", "TEXT"),
    ]
    for col_name, col_type in new_columns:
        try:
            db.execute(f"ALTER TABLE behavioral_insights ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass


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
                "geoprivacy": str,
                "is_obscured": int,
                "obscuration_radius_km": float,
            },
            pk="observation_id",
        )
    else:
        # Migrate existing observations table — add geoprivacy columns if absent
        obs_cols = {c.name for c in db["observations"].columns}
        if "geoprivacy" not in obs_cols:
            db["observations"].add_column("geoprivacy", str, not_null_default="open")
        if "is_obscured" not in obs_cols:
            db["observations"].add_column("is_obscured", int, not_null_default=0)
        if "obscuration_radius_km" not in obs_cols:
            db["observations"].add_column("obscuration_radius_km", float)

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

    if "gbif_observations" not in db.table_names():
        db["gbif_observations"].create(
            {
                "gbif_key": int,
                "species": str,
                "common_name": str,
                "taxon_key": int,
                "lat": float,
                "lng": float,
                "observed_on": str,
                "country_code": str,
                "dataset_name": str,
                "basis_of_record": str,
                "coordinate_uncertainty_m": float,
                "jurisdiction": str,
                "ingested_at": str,
            },
            pk="gbif_key",
        )

    if "behavioral_insights" not in db.table_names():
        db["behavioral_insights"].create(
            {
                "id": int,
                "species": str,
                "condition_type": str,
                "condition_context": str,
                "conclusion": str,
                "confidence": str,
                "source_type": str,
                "source_detail": str,
                "evidence_count": int,
                "version": int,
                "is_current": int,
                "contradicted_by": int,
                "user_verified": int,
                "jurisdiction": str,
                "lat": float,
                "lng": float,
                "recommendation": str,
                "condition_season": str,
                "location_name": str,
                "last_validated": str,
                "created_at": str,
            },
            pk="id",
        )

    if "water_features" not in db.table_names():
        db["water_features"].create(
            {
                "osm_id": str,
                "feature_type": str,
                "name": str,
                "lat": float,
                "lng": float,
                "jurisdiction": str,
                "area_m2": float,
                "tags": str,
                "fetched_at": str,
            },
            pk="osm_id",
        )

    if "access_points" not in db.table_names():
        db["access_points"].create(
            {
                "osm_id": str,
                "access_type": str,
                "name": str,
                "lat": float,
                "lng": float,
                "jurisdiction": str,
                "tags": str,
                "fetched_at": str,
            },
            pk="osm_id",
        )

    if "stream_gauge_readings" not in db.table_names():
        db["stream_gauge_readings"].create(
            {
                "id": int,
                "station_id": str,
                "station_name": str,
                "river_name": str,
                "lat": float,
                "lng": float,
                "jurisdiction": str,
                "water_level_m": float,
                "discharge_cms": float,
                "level_trend": str,
                "discharge_trend": str,
                "level_grade": str,
                "reading_datetime": str,
                "fetched_at": str,
            },
            pk="id",
        )
        db["stream_gauge_readings"].create_index(
            ["station_id", "reading_datetime"], unique=True, if_not_exists=True
        )

    if "stocking_records" not in db.table_names():
        db["stocking_records"].create(
            {
                "record_id": str,
                "waterbody_name": str,
                "waterbody_code": str,
                "municipality": str,
                "county": str,
                "lat": float,
                "lng": float,
                "jurisdiction": str,
                "species": str,
                "species_code": str,
                "year": int,
                "month": int,
                "quantity": int,
                "life_stage": str,
                "stocking_purpose": str,
                "stocked_at": str,
            },
            pk="record_id",
        )

    if "species_ranges" not in db.table_names():
        db["species_ranges"].create(
            {
                "species": str,
                "scientific_name": str,
                "native_to_ontario": int,
                "native_to_great_lakes": int,
                "introduced": int,
                "extirpated_from_ontario": int,
                "general_range": str,
                "habitat_notes": str,
                "jurisdictions_present": str,  # JSON array
                "sara_status": str,
                "ontario_status": str,
                "cosewic_status": str,
                "fishing_notes": str,
                "last_updated": str,
            },
            pk="species",
        )

    if "reddit_posts" not in db.table_names():
        db["reddit_posts"].create(
            {
                "post_id": str,
                "subreddit": str,
                "post_type": str,
                "title": str,
                "body": str,
                "url": str,
                "author": str,
                "score": int,
                "num_comments": int,
                "parent_post_id": str,
                "created_utc": str,
                "extracted_species": str,  # JSON array
                "extracted_locations": str,  # JSON array
                "jurisdiction": str,
                "ingested_at": str,
            },
            pk="post_id",
        )

    if "reddit_posts_fts" not in db.table_names():
        db["reddit_posts"].enable_fts(["title", "body"], create_triggers=True)
        db["reddit_posts"].populate_fts(["title", "body"])

    if "stream_segments" not in db.table_names():
        db["stream_segments"].create(
            {
                "ogf_id": int,
                "watercourse_type": str,
                "name": str,
                "flow_verified": int,  # 0 or 1
                "permanency": str,
                "flow_classification": str,
                "length_m": float,
                "geom_wkt": str,
                "start_node": str,
                "end_node": str,
                "jurisdiction": str,
                "ingested_at": str,
            },
            pk="ogf_id",
        )
        db["stream_segments"].create_index(["name"], if_not_exists=True)
        db["stream_segments"].create_index(["start_node"], if_not_exists=True)
        db["stream_segments"].create_index(["end_node"], if_not_exists=True)

    if "barriers" not in db.table_names():
        db["barriers"].create(
            {
                "ogf_id": int,
                "barrier_type": str,
                "geom_wkt": str,
                "nearest_segment_ogf_id": int,
                "snap_distance_m": float,
                "jurisdiction": str,
                "ingested_at": str,
            },
            pk="ogf_id",
        )

    if "regulation_chunks" not in db.table_names():
        db["regulation_chunks"].create(
            {
                "zone": int,
                "jurisdiction": str,
                "regulation_year": int,
                "raw_text": str,
                "char_count": int,
                "source_url": str,
                "ingested_at": str,
            },
            pk=["zone", "jurisdiction", "regulation_year"],
        )

    if "water_quality_readings" not in db.table_names():
        db["water_quality_readings"].create(
            {
                "record_id": str,
                "station_id": str,
                "station_name": str,
                "lat": float,
                "lng": float,
                "jurisdiction": str,
                "sampled_at": str,
                "do_mgl": float,
                "ph": float,
                "temp_c": float,
                "conductivity_us_cm": float,
                "turbidity_fnu": float,
            },
            pk="record_id",
        )
        db["water_quality_readings"].create_index(["station_id"], if_not_exists=True)
        db["water_quality_readings"].create_index(["sampled_at"], if_not_exists=True)

    if "bird_observations" not in db.table_names():
        db["bird_observations"].create(
            {
                "obs_id": str,
                "species_code": str,
                "common_name": str,
                "scientific_name": str,
                "lat": float,
                "lng": float,
                "observed_on": str,
                "how_many": int,
                "location_name": str,
                "jurisdiction": str,
                "piscivore_significance": str,
                "fetched_at": str,
            },
            pk="obs_id",
        )
        db["bird_observations"].create_index(["species_code"], if_not_exists=True)
        db["bird_observations"].create_index(["observed_on"], if_not_exists=True)

    if "stream_temperature_readings" not in db.table_names():
        db["stream_temperature_readings"].create(
            {
                "station_id": str,
                "station_name": str,
                "lat": float,
                "lng": float,
                "jurisdiction": str,
                "year": int,
                "month": int,
                "mean_temp_c": float,
                "max_temp_c": float,
                "min_temp_c": float,
                "days_measured": int,
            },
            pk=["station_id", "year", "month"],
        )

    if "stream_temperature_summaries" not in db.table_names():
        db["stream_temperature_summaries"].create(
            {
                "station_id": str,
                "station_name": str,
                "lat": float,
                "lng": float,
                "jurisdiction": str,
                "summer_mean_c": float,
                "summer_max_c": float,
                "thermal_regime": str,
                "years_of_data": int,
                "species_notes": str,
            },
            pk="station_id",
        )

    if "crown_land" not in db.table_names():
        db["crown_land"].create(
            {
                "crown_id": str,
                "land_use_type": str,
                "geom_wkt": str,
                "centroid_lat": float,
                "centroid_lng": float,
                "bbox_minx": float,
                "bbox_miny": float,
                "bbox_maxx": float,
                "bbox_maxy": float,
                "fetched_at": str,
            },
            pk="crown_id",
        )

    if "sdm_predictions" not in db.table_names():
        db["sdm_predictions"].create(
            {
                "ogf_id": int,
                "species": str,
                "presence_probability": float,
                "model_version": str,
                "predicted_at": str,
                "centroid_lat": float,
                "centroid_lng": float,
            },
            pk=["ogf_id", "species"],
        )
        db["sdm_predictions"].create_index(
            ["species", "centroid_lat", "centroid_lng"],
            if_not_exists=True,
        )

    if "dismissed_segments" not in db.table_names():
        db["dismissed_segments"].create(
            {
                "ogf_id": int,
                "dismissed_at": str,
                "reason": str,
            },
            pk="ogf_id",
        )


    if "sessions" not in db.table_names():
        db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT,
                date_approx TEXT,
                overall_notes TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)

    if "stops" not in db.table_names():
        db.execute("""
            CREATE TABLE IF NOT EXISTS stops (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                location_text       TEXT NOT NULL,
                location_name       TEXT,
                lat                 REAL,
                lng                 REAL,
                ohn_segment_id      TEXT,
                location_method     TEXT,
                location_confidence REAL,
                species_caught      TEXT,
                party_species_caught TEXT,
                was_productive      INTEGER,
                technique           TEXT,
                gear                TEXT,
                water_level         TEXT,
                water_clarity       TEXT,
                water_temp_c        REAL,
                weather_notes       TEXT,
                notes               TEXT,
                created_at          TEXT DEFAULT (datetime('now'))
            )
        """)

    if "parsed_trips" not in db.table_names():
        db["parsed_trips"].create(
            {
                "trip_id": int,
                "user_id": str,
                "logged_at": str,
                "trip_date": str,
                "location_description": str,
                "waterbody_name": str,
                "lat": float,
                "lng": float,
                "ogf_id": int,
                "distance_to_segment_m": float,
                "species_caught": str,    # JSON array
                "species_observed": str,  # JSON array
                "species_targeted": str,
                "water_level": str,
                "water_clarity": str,
                "water_temp_c": float,
                "weather": str,
                "flow_trend": str,
                "habitat_notes": str,
                "spot_type": str,
                "fish_count": int,
                "was_productive": int,    # 0/1/null
                "gear": str,
                "notes": str,
                "raw_text": str,
                "location_method": str,
                "location_confidence": float,
            },
            pk="trip_id",
        )
        db["parsed_trips"].create_index(["ogf_id"], if_not_exists=True)
        db["parsed_trips"].create_index(["trip_date"], if_not_exists=True)
    else:
        # Migrate: add location resolution columns if absent
        pt_cols = {c.name for c in db["parsed_trips"].columns}
        for col, col_type in [("location_method", "TEXT"), ("location_confidence", "REAL")]:
            if col not in pt_cols:
                try:
                    db.execute(f"ALTER TABLE parsed_trips ADD COLUMN {col} {col_type}")
                except Exception:
                    pass


    if "knowledge_sources" not in db.table_names():
        db["knowledge_sources"].create(
            {
                "id": int,
                "source_type": str,
                "source_id": str,
                "title": str,
                "url": str,
                "channel_name": str,
                "published_at": str,
                "search_query": str,
                "transcript_raw": str,
                "ingested_at": str,
            },
            pk="id",
        )
        db["knowledge_sources"].create_index(
            ["source_type", "source_id"], unique=True, if_not_exists=True
        )

    if "knowledge_chunks" not in db.table_names():
        db["knowledge_chunks"].create(
            {
                "id": int,
                "source_id": int,
                "chunk_index": int,
                "chunk_text": str,
                "created_at": str,
            },
            pk="id",
            foreign_keys=[("source_id", "knowledge_sources", "id")],
        )
        db["knowledge_chunks"].create_index(["source_id"], if_not_exists=True)
        db["knowledge_chunks"].enable_fts(["chunk_text"], create_triggers=True)

    db.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT,
            timestamp       TEXT DEFAULT (datetime('now')),
            model           TEXT,
            input_tokens    INTEGER,
            output_tokens   INTEGER,
            total_tokens    INTEGER,
            tool_calls_made INTEGER DEFAULT 0,
            endpoint        TEXT DEFAULT 'chat'
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id      TEXT PRIMARY KEY,
            started_at      TEXT DEFAULT (datetime('now')),
            ended_at        TEXT,
            turn_count      INTEGER DEFAULT 0,
            summary         TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            turn_index      INTEGER NOT NULL,
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session
            ON chat_messages(session_id)
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS angler_context (
            id              INTEGER PRIMARY KEY CHECK (id = 1),
            content         TEXT NOT NULL DEFAULT '',
            last_updated    TEXT DEFAULT (datetime('now')),
            session_count   INTEGER DEFAULT 0
        )
    """)


    db.execute("""
        CREATE TABLE IF NOT EXISTS segment_synthesis (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key       TEXT UNIQUE NOT NULL,
            lat             REAL,
            lng             REAL,
            location_name   TEXT,
            synthesis       TEXT NOT NULL,
            data_sources    TEXT,
            computed_at     TEXT DEFAULT (datetime('now')),
            hit_count       INTEGER DEFAULT 0
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_segment_synthesis_key
            ON segment_synthesis(cache_key)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_segment_synthesis_loc
            ON segment_synthesis(lat, lng)
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS tool_usage (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT,
            timestamp       TEXT DEFAULT (datetime('now')),
            tool_name       TEXT NOT NULL,
            input_summary   TEXT,
            success         INTEGER DEFAULT 1
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_tool_usage_session ON tool_usage(session_id)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_tool_usage_tool ON tool_usage(tool_name)
    """)


def cleanup_old_gauge_readings(db: Database, days: int = 7) -> None:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    db.execute("DELETE FROM stream_gauge_readings WHERE reading_datetime < ?", [cutoff])
