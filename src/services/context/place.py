"""Place resolution.

Anglers think in named stretches ("Byng Island"), the physical data is keyed
to OHN segment IDs, and sightings are points that do not snap cleanly to
either. So any input resolves to the same thing: a coordinate, a set of
segments, and a radius.

Resolution is local-only by design — OHN names, the user's own logged
location names, and ingested waterbodies. No geocoder: an unresolvable name
returns an honest failure rather than a confident guess at the wrong river.
"""

import logging

from sqlite_utils import Database

from src.models.context import Place

logger = logging.getLogger(__name__)

_KM_PER_DEGREE = 111.0

# How far around a resolved point we gather segments and sightings. Sightings
# are points with real positional error (iNaturalist obscures to 22km), so a
# radius is not optional.
_DEFAULT_RADIUS_KM = 5.0


def resolve(
    db: Database,
    query: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    segment_id: int | None = None,
    radius_km: float = _DEFAULT_RADIUS_KM,
    user_id: int = 1,
) -> Place | None:
    """Resolve any of lat/lng, segment ID, or a name to a Place.

    Returns None when a name cannot be resolved from local data — callers
    surface that as an honest failure, not an empty result set for the
    wrong stretch of water.
    """
    if lat is not None and lng is not None:
        return _from_latlng(db, lat, lng, radius_km, query)

    if segment_id is not None:
        return _from_segment(db, segment_id, radius_km)

    if query:
        return _from_name(db, query, radius_km, user_id)

    return None


def _from_latlng(
    db: Database, lat: float, lng: float, radius_km: float, query: str | None
) -> Place:
    segs = segments_near(db, lat, lng, radius_km)
    name = None
    if segs:
        name = _segment_name(db, segs[0])
    return Place(
        query=query or f"{lat:.5f},{lng:.5f}",
        name=name,
        lat=lat,
        lng=lng,
        segment_ids=segs,
        radius_km=radius_km,
        jurisdiction=_jurisdiction_at(db, lat, lng),
        resolved_by="latlng",
    )


def _from_segment(db: Database, segment_id: int, radius_km: float) -> Place | None:
    if "stream_segments" not in db.table_names():
        return None
    rows = list(db["stream_segments"].rows_where("ogf_id = ?", [segment_id]))
    if not rows:
        return None
    row = rows[0]
    lat, lng = _segment_centroid(row)
    if lat is None or lng is None:
        return None
    return Place(
        query=str(segment_id),
        name=row.get("name") or None,
        lat=lat,
        lng=lng,
        segment_ids=[segment_id],
        radius_km=radius_km,
        jurisdiction=row.get("jurisdiction"),
        resolved_by="segment_id",
    )


def _from_name(db: Database, query: str, radius_km: float, user_id: int) -> Place | None:
    """Name lookup: the user's own logged spots first, then OHN, then OSM water.

    User logs come first deliberately. If someone has logged "the dam" six
    times, that phrase means their dam, not the nearest OHN match.
    """
    pattern = f"%{query.lower().strip()}%"

    hit = _user_logged_place(db, pattern, user_id)
    if hit:
        lat, lng, name = hit
        return Place(
            query=query,
            name=name,
            lat=lat,
            lng=lng,
            segment_ids=segments_near(db, lat, lng, radius_km),
            radius_km=radius_km,
            jurisdiction=_jurisdiction_at(db, lat, lng),
            resolved_by="user_log",
            resolution_note=f"matched your logged trips at {name}",
        )

    hit = _named_segment(db, pattern)
    if hit:
        lat, lng, name, seg_id = hit
        return Place(
            query=query,
            name=name,
            lat=lat,
            lng=lng,
            segment_ids=segments_near(db, lat, lng, radius_km) or [seg_id],
            radius_km=radius_km,
            jurisdiction=_jurisdiction_at(db, lat, lng),
            resolved_by="name",
            resolution_note=f"matched OHN watercourse {name}",
        )

    hit = _named_water_feature(db, pattern)
    if hit:
        lat, lng, name = hit
        return Place(
            query=query,
            name=name,
            lat=lat,
            lng=lng,
            segment_ids=segments_near(db, lat, lng, radius_km),
            radius_km=radius_km,
            jurisdiction=_jurisdiction_at(db, lat, lng),
            resolved_by="name",
            resolution_note=f"matched mapped water feature {name}",
        )

    return None


# ── lookups ───────────────────────────────────────────────────────────────────


def _user_logged_place(
    db: Database, pattern: str, user_id: int
) -> tuple[float, float, str] | None:
    if "stops" not in db.table_names():
        return None
    rows = list(
        db.execute(
            "SELECT lat, lng, COALESCE(location_name, location_text) AS nm, COUNT(*) AS n "
            "FROM stops "
            "WHERE user_id = ? AND lat IS NOT NULL AND lng IS NOT NULL "
            "  AND (LOWER(location_name) LIKE ? OR LOWER(location_text) LIKE ?) "
            "GROUP BY nm ORDER BY n DESC LIMIT 1",
            [user_id, pattern, pattern],
        ).fetchall()
    )
    if not rows:
        return None
    lat, lng, name, _ = rows[0]
    return float(lat), float(lng), str(name)


def _named_segment(db: Database, pattern: str) -> tuple[float, float, str, int] | None:
    if "stream_segments" not in db.table_names():
        return None
    rows = list(
        db["stream_segments"].rows_where(
            "LOWER(name) LIKE ? AND name IS NOT NULL", [pattern], limit=25
        )
    )
    for row in rows:
        lat, lng = _segment_centroid(row)
        if lat is not None and lng is not None:
            return lat, lng, str(row["name"]), int(row["ogf_id"])
    return None


def _named_water_feature(db: Database, pattern: str) -> tuple[float, float, str] | None:
    if "water_features" not in db.table_names():
        return None
    rows = list(
        db["water_features"].rows_where(
            "LOWER(name) LIKE ? AND name IS NOT NULL AND lat IS NOT NULL",
            [pattern],
            limit=1,
        )
    )
    if not rows:
        return None
    row = rows[0]
    return float(row["lat"]), float(row["lng"]), str(row["name"])


def segments_near(db: Database, lat: float, lng: float, radius_km: float) -> list[int]:
    """OHN segment IDs whose centroid falls within radius_km."""
    if "stream_segments" not in db.table_names():
        return []
    deg = radius_km / _KM_PER_DEGREE
    out: list[int] = []
    for row in db["stream_segments"].rows_where(
        "ogf_id IS NOT NULL", [], limit=5000
    ):
        clat, clng = _segment_centroid(row)
        if clat is None or clng is None:
            continue
        if abs(clat - lat) <= deg and abs(clng - lng) <= deg:
            out.append(int(row["ogf_id"]))
    return out


def _segment_name(db: Database, segment_id: int) -> str | None:
    rows = list(db["stream_segments"].rows_where("ogf_id = ?", [segment_id]))
    return (rows[0].get("name") or None) if rows else None


def _segment_centroid(row: dict) -> tuple[float | None, float | None]:
    """Midpoint of an OHN segment.

    stream_segments stores geometry as WKT rather than a centroid pair, so
    the midpoint is averaged from the linestring vertices.
    """
    for lat_key, lng_key in (("centroid_lat", "centroid_lng"), ("lat", "lng")):
        if row.get(lat_key) is not None and row.get(lng_key) is not None:
            return float(row[lat_key]), float(row[lng_key])

    wkt = row.get("geom_wkt")
    if not wkt:
        return None, None
    try:
        inner = wkt[wkt.index("(") + 1 : wkt.rindex(")")].strip("() ")
        pts = [p.strip() for p in inner.split(",") if p.strip()]
        if not pts:
            return None, None
        lngs, lats = [], []
        for p in pts:
            parts = p.split()
            if len(parts) >= 2:
                lngs.append(float(parts[0]))
                lats.append(float(parts[1]))
        if not lats:
            return None, None
        return sum(lats) / len(lats), sum(lngs) / len(lngs)
    except (ValueError, IndexError):
        return None, None


def _jurisdiction_at(db: Database, lat: float, lng: float) -> str | None:
    """Best-effort jurisdiction from the nearest ingested record."""
    try:
        from src.jurisdictions.geo import jurisdiction_for_coords

        return jurisdiction_for_coords(lat, lng)
    except Exception:  # noqa: BLE001 - resolution must never break describe()
        logger.debug("jurisdiction lookup unavailable", exc_info=True)
        return None
