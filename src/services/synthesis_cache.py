"""
Synthesis cache: compute expensive cross-dataset location analysis once,
store it, reuse forever. Lazy — only computes spots people actually ask about.
"""
import json
import math
from datetime import datetime

from sqlite_utils import Database


def _cache_key(lat: float | None, lng: float | None, location_name: str | None) -> str:
    """Build a stable cache key. Round coords to ~100m grid so nearby queries hit."""
    if lat is not None and lng is not None:
        return f"geo:{round(lat, 3)},{round(lng, 3)}"
    if location_name:
        return f"name:{location_name.strip().lower()}"
    return "unknown"


def get_cached_synthesis(
    db: Database,
    lat: float | None = None,
    lng: float | None = None,
    location_name: str | None = None,
    radius_km: float = 0.15,
) -> dict | None:
    """
    Check the cache for an existing synthesis near this location.
    Returns the cached synthesis dict, or None on miss.
    """
    key = _cache_key(lat, lng, location_name)

    # rows_where returns dicts automatically
    try:
        row = next(db["segment_synthesis"].rows_where("cache_key = ?", [key]), None)
    except Exception:
        row = None

    if row:
        db.execute(
            "UPDATE segment_synthesis SET hit_count = hit_count + 1 WHERE cache_key = ?",
            [key],
        )
        db.conn.commit()
        return {
            "synthesis": row["synthesis"],
            "location_name": row.get("location_name"),
            "computed_at": row.get("computed_at"),
            "cache_hit": True,
        }

    if lat is not None and lng is not None:
        try:
            candidates = list(
                db["segment_synthesis"].rows_where("lat IS NOT NULL AND lng IS NOT NULL")
            )
        except Exception:
            candidates = []
        for c in candidates:
            d = _haversine_km(lat, lng, c["lat"], c["lng"])
            if d <= radius_km:
                db.execute(
                    "UPDATE segment_synthesis SET hit_count = hit_count + 1 WHERE id = ?",
                    [c["id"]],
                )
                db.conn.commit()
                return {
                    "synthesis": c["synthesis"],
                    "location_name": c.get("location_name"),
                    "computed_at": c.get("computed_at"),
                    "cache_hit": True,
                }

    # Fuzzy name match: one name is a subset of words of the other
    if location_name:
        try:
            all_entries = list(db["segment_synthesis"].rows_where(
                "location_name IS NOT NULL"
            ))
        except Exception:
            all_entries = []
        query_words = set(location_name.strip().lower().split())
        for c in all_entries:
            c_words = set((c["location_name"] or "").strip().lower().split())
            if query_words and c_words and (query_words <= c_words or c_words <= query_words):
                db.execute(
                    "UPDATE segment_synthesis SET hit_count = hit_count + 1 WHERE id = ?",
                    [c["id"]],
                )
                db.conn.commit()
                return {
                    "synthesis": c["synthesis"],
                    "location_name": c.get("location_name"),
                    "computed_at": c.get("computed_at"),
                    "cache_hit": True,
                }

    return None


def store_synthesis(
    db: Database,
    synthesis: str,
    lat: float | None = None,
    lng: float | None = None,
    location_name: str | None = None,
    data_sources: list[str] | None = None,
) -> None:
    """Store a freshly computed synthesis in the cache."""
    key = _cache_key(lat, lng, location_name)
    # Raw SQL avoids sqlite-utils upsert quirks with AUTOINCREMENT primary keys
    db.execute(
        """
        INSERT OR REPLACE INTO segment_synthesis
            (cache_key, lat, lng, location_name, synthesis, data_sources, computed_at, hit_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """,
        [
            key,
            lat,
            lng,
            location_name,
            synthesis,
            json.dumps(data_sources or []),
            datetime.now().isoformat(),
        ],
    )
    db.conn.commit()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))
