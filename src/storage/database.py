"""SQLite database setup for trips and future tables."""

from datetime import datetime, timedelta
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


def cleanup_old_gauge_readings(db: Database, days: int = 7) -> None:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    db.execute("DELETE FROM stream_gauge_readings WHERE reading_datetime < ?", [cutoff])
