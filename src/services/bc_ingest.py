"""Service entry point for BC-specific data ingest.

Orchestrates the three CA-BC adapters:
  - FWA stream network  (ca_bc/hydro_network.py)
  - FISS fish observations (ca_bc/fish_observations.py)
  - BC EMS water quality (ca_bc/water_quality.py — stub)

Called from the CLI `ingest-bc` command or the /ingest/data-bc API endpoint.
Global sources (iNat, GBIF, WSC, OSM, eBird) are handled by the standard
ingest pipeline and do not need to be called here.
"""

import importlib
import logging
from datetime import datetime

from src.storage.database import get_db

logger = logging.getLogger(__name__)


def ingest_bc_hydro_network(
    lat: float,
    lon: float,
    radius_km: float = 50.0,
) -> tuple[int, int]:
    """Fetch and store FWA stream segments for a BC location. Returns (seg_count, 0).

    Barriers are not separately indexed in FWA (no equivalent to OHN barrier layer),
    so barrier_count is always 0.
    """
    _fwa = importlib.import_module("src.ingest.jurisdictions.ca_bc.hydro_network")
    db = get_db()

    logger.info("Fetching FWA stream segments (%.0fkm radius)…", radius_km)
    segments = _fwa.fetch_watercourses(lat, lon, radius_km)

    now = datetime.utcnow().isoformat()

    # Delete only CA-BC rows from the previous ingest for this jurisdiction
    if "stream_segments" in db.table_names():
        db["stream_segments"].delete_where("jurisdiction = ?", ["CA-BC"])

    seg_rows = [
        {
            "ogf_id": s.ogf_id,
            "watercourse_type": s.watercourse_type,
            "name": s.name,
            "flow_verified": int(s.flow_verified),
            "permanency": s.permanency,
            "flow_classification": s.flow_classification,
            "stream_order": s.stream_order,
            "length_m": s.length_m,
            "geom_wkt": s.geom_wkt,
            "start_node": s.start_node,
            "end_node": s.end_node,
            "jurisdiction": s.jurisdiction,
            "segment_source": s.segment_source,
            "ingested_at": now,
        }
        for s in segments
    ]
    if seg_rows:
        db["stream_segments"].insert_all(seg_rows, pk="ogf_id", replace=True)

    logger.info("FWA ingest done: %d segments stored", len(segments))
    return len(segments), 0


def ingest_fiss_observations(
    lat: float,
    lng: float,
    radius_km: float = 50.0,
) -> int:
    """Fetch and store FISS fish observations for a BC location. Returns count stored."""
    from src.storage.observations import upsert_observations

    _fiss = importlib.import_module("src.ingest.jurisdictions.ca_bc.fish_observations")
    db = get_db()

    logger.info("Fetching FISS fish observations (%.0fkm radius)…", radius_km)
    observations = _fiss.fetch_observations(lat, lng, radius_km)
    if observations:
        upsert_observations(db, observations)
    logger.info("FISS ingest done: %d observations stored", len(observations))
    return len(observations)


def ingest_bc_water_quality(
    lat: float,
    lng: float,
    radius_km: float = 50.0,
) -> int:
    """Fetch BC EMS water quality readings for a BC location. Returns count stored.

    Currently returns 0 — results fetch is not yet implemented; see
    src/ingest/jurisdictions/ca_bc/water_quality.py for the TODO.
    """
    _wq = importlib.import_module("src.ingest.jurisdictions.ca_bc.water_quality")
    readings = _wq.fetch_water_quality_readings(lat, lng, radius_km)
    return len(readings)


def ingest_bc_data(
    lat: float,
    lng: float,
    radius_km: float = 50.0,
) -> dict[str, int]:
    """Run all BC-specific ingest adapters for a location. Returns counts per source."""
    fwa_segs, fwa_barriers = ingest_bc_hydro_network(lat, lng, radius_km)
    fiss_count = ingest_fiss_observations(lat, lng, radius_km)
    wq_count = ingest_bc_water_quality(lat, lng, radius_km)
    return {
        "fwa_segments": fwa_segs,
        "fwa_barriers": fwa_barriers,
        "fiss_observations": fiss_count,
        "water_quality_readings": wq_count,
    }
