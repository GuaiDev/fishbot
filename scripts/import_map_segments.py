"""
One-time import of map_data.json into the map_segments table.
Run: uv run python scripts/import_map_segments.py
"""
import sys
import json

sys.path.insert(0, "src")
from storage.database import get_db, ensure_schema


def main():
    print("Loading map_data.json...")
    with open("data/processed/map_data.json") as f:
        data = json.load(f)

    features = data["features"]
    print(f"Importing {len(features):,} segments...")

    db = get_db()
    ensure_schema(db)

    try:
        db.execute("DELETE FROM map_segments")
        db.conn.commit()
    except Exception:
        pass

    rows = []
    total = len(features)
    for i, f in enumerate(features):
        coords = f["geometry"]["coordinates"]
        p = f["properties"]
        rows.append({
            "ogf_id": p["ogf_id"],
            "lat": coords[1],
            "lng": coords[0],
            "score_balanced": p.get("untapped_score_balanced"),
            "score_easy": p.get("untapped_score_easy"),
            "score_adventure": p.get("untapped_score_adventure"),
            "habitat_score": p.get("habitat_score"),
            "access_score": p.get("access_score"),
            "stream_order": p.get("stream_order"),
            "watercourse_name": p.get("watercourse_name"),
            "nearest_named_stream": p.get("nearest_named_stream"),
            "is_confluence": 1 if p.get("is_confluence_segment") else 0,
            "connected_to_waterbody": 1 if p.get("connected_to_waterbody") else 0,
            "observation_pressure": p.get("observation_pressure"),
            "google_maps_url": p.get("google_maps_url"),
            "swoop_url": p.get("swoop_url"),
        })

        if len(rows) >= 1000:
            db["map_segments"].insert_all(rows, ignore=True)
            db.conn.commit()
            rows = []
            print(f"  {i + 1:,}/{total:,}")

    if rows:
        db["map_segments"].insert_all(rows, ignore=True)
        db.conn.commit()

    count = db.execute("SELECT COUNT(*) FROM map_segments").fetchone()[0]
    print(f"Done. {count:,} segments in database.")


if __name__ == "__main__":
    main()
