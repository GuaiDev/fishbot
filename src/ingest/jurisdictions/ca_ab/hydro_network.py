"""Alberta stream network ingestion — STUB.

Alberta uses the federal National Hydrographic Network (NHN) for official
stream segment data. The NHN is available as GeoPackage tiles via FTP but
has no queryable WFS or ArcGIS REST endpoint that can be filtered by bbox
without downloading large province-wide tiles first.

TODO: Implement NHN tile-based ingestion:
  FTP base: ftp://ftp.maps.canada.ca/pub/nrcan_rncan/vector/geobase_nhn_rhn/
  Tile index: each 1-degree tile is a separate GeoPackage (~100 MB each)
  Layers: NHN_HN_NLFLOW_1 (stream network linear segments)
  Approach: pre-tile the province by 1°×1° grid, download relevant tiles,
            filter NHNFlowcode geometry to target bbox, write to stream_segments.

Alternative for near-term Alberta coverage:
  - WSC stream gauges (already global) give flow data for major AB rivers
  - OSM (already global) gives stream geometry reasonable to order 3+
  - Together these cover the Bow, North Saskatchewan, Oldman, Athabasca adequately

For a dedicated NHN adapter, see the FWA adapter (ca_bc/hydro_network.py) for
the pagination and storage pattern. The NHN uses similar WKT geometry and
Strahler orders.

This stub returns (0, 0) and logs a clear message so downstream callers don't fail.
"""

import logging

logger = logging.getLogger(__name__)


def fetch_watercourses(
    lat: float,
    lon: float,
    radius_km: float = 50.0,
) -> list:
    """Stub — returns empty list with a warning.

    TODO: Implement NHN GeoPackage tile-based fetch.
    See module docstring for implementation notes.
    """
    logger.warning(
        "AB hydro_network: NHN adapter not yet implemented — "
        "returning 0 stream segments for (%.4f, %.4f). "
        "Alberta stream coverage comes from OSM (global adapter). "
        "See src/ingest/jurisdictions/ca_ab/hydro_network.py for TODO.",
        lat, lon,
    )
    return []
