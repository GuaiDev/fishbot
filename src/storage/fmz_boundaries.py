"""Storage and point-in-polygon lookup for Ontario FMZ boundaries.

Resolution fails CLOSED, matching the conservation-status pattern: if a point
cannot be placed inside a real zone polygon, the caller is told so explicitly
rather than handed the nearest guess. Regulations are retrieved-or-refused, and
that rule has to cover locating the reader as much as fetching the text — a
confident answer drawn from the wrong zone is the failure with teeth.
"""

import logging
from dataclasses import dataclass

from sqlite_utils import Database

logger = logging.getLogger(__name__)

_TABLE = "fmz_boundaries"


@dataclass(frozen=True)
class ZoneResolution:
    """The outcome of locating a point. Exactly one of zone / empty_reason is set."""

    zone: int | None
    zone_name: str | None = None
    empty_reason: str | None = None
    detail: str | None = None

    @property
    def resolved(self) -> bool:
        return self.zone is not None


def upsert_fmz_boundaries(db: Database, rows: list[dict]) -> int:
    if not rows:
        return 0
    db[_TABLE].upsert_all(rows, pk="zone", alter=True)
    db.conn.commit()
    return len(rows)


def boundary_count(db: Database) -> int:
    return db[_TABLE].count if _TABLE in db.table_names() else 0


def resolve_zone(db: Database, lat: float, lng: float) -> ZoneResolution:
    """Locate a point inside a real FMZ polygon, or refuse to guess."""
    if boundary_count(db) == 0:
        return ZoneResolution(
            zone=None,
            empty_reason="zone_boundaries_not_loaded",
            detail=(
                "Fisheries Management Zone boundaries have not been ingested, so this "
                "location cannot be placed in a zone. Regulations are withheld rather "
                "than guessed. Run `make ingest` to load the MNRF boundary layer."
            ),
        )

    try:
        from shapely.geometry import Point
        from shapely.wkt import loads as wkt_loads
    except ImportError:  # pragma: no cover
        return ZoneResolution(
            zone=None,
            empty_reason="geometry_unavailable",
            detail="shapely is not installed, so point-in-polygon lookup cannot run.",
        )

    pt = Point(lng, lat)
    # Bounding box prefilter in SQL, exact containment in shapely. The bbox is
    # only ever used to NARROW candidates — never to decide the answer, which
    # is precisely what the old rectangle table got wrong.
    candidates = list(
        db[_TABLE].rows_where(
            "bbox_minx <= ? AND bbox_maxx >= ? AND bbox_miny <= ? AND bbox_maxy >= ?",
            [lng, lng, lat, lat],
        )
    )

    hits = []
    for row in candidates:
        try:
            if wkt_loads(row["geom_wkt"]).contains(pt):
                hits.append(row)
        except Exception:  # noqa: BLE001
            logger.warning("FMZ %s: geometry failed to load", row.get("zone"))

    if len(hits) == 1:
        return ZoneResolution(zone=int(hits[0]["zone"]), zone_name=hits[0].get("zone_name"))

    if not hits:
        return ZoneResolution(
            zone=None,
            empty_reason="outside_known_zones",
            detail=(
                f"({lat:.4f}, {lng:.4f}) does not fall inside any Ontario FMZ polygon. "
                "It is likely outside Ontario, or on a boundary the layer does not cover."
            ),
        )

    # Genuinely ambiguous — overlapping polygons or a point on a shared edge.
    zones = sorted({int(h["zone"]) for h in hits})
    if len(zones) == 1:
        return ZoneResolution(zone=zones[0], zone_name=hits[0].get("zone_name"))
    return ZoneResolution(
        zone=None,
        empty_reason="ambiguous_zone",
        detail=(
            f"({lat:.4f}, {lng:.4f}) falls within more than one zone polygon "
            f"({', '.join(f'FMZ {z}' for z in zones)}). Confirm the zone before "
            "relying on any limit."
        ),
    )
