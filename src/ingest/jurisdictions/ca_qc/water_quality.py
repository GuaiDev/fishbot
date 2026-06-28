"""Quebec water quality — STUB.

TODO: Implement when a public API becomes available.

The Ministère de l'Environnement, de la Lutte contre les changements climatiques,
de la Faune et des Parcs (MELCCFP) operates the Réseau de surveillance de la
qualité de l'eau des rivières (RSQER — river water quality monitoring network)
but data is only accessible through PDF reports and no public REST API exists.

Alternative data sources for Quebec water quality:
  - WSC stream gauges (global adapter) — flow data for major QC rivers
  - DataStream (ca_national/datastream_water_quality.py) — some QC coverage
  - CABIN benthic (expanded ca_on/benthic.py) — proxy for habitat quality

Table: water_quality_readings (shared schema)
"""

import logging

logger = logging.getLogger(__name__)


def fetch_water_quality_readings(
    lat: float,
    lng: float,
    radius_km: float = 50.0,
) -> list[dict]:
    """Stub — returns empty list with a TODO warning."""
    logger.warning(
        "QC water_quality: MELCCFP RSQER has no public REST API as of 2026 — "
        "returning 0 readings. See https://www.environnement.gouv.qc.ca/eau/ "
        "for monitoring program details. DataStream may cover some QC watersheds."
    )
    return []
