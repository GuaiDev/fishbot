"""BC Environmental Monitoring System (EMS) water quality ingestion.

Source: DataBC Open Data — WFS 2.0.0 (stations) + BC Data Catalogue object
storage (results)

STATIONS
  Layer: WHSE_ENVIRONMENTAL_MONITORING.EMS_MONITORING_LOCN_TYPES_SVW
  Endpoint: https://openmaps.gov.bc.ca/geo/pub/
            WHSE_ENVIRONMENTAL_MONITORING.EMS_MONITORING_LOCN_TYPES_SVW/ows
  This WFS returns monitoring station metadata (MONITORING_LOCATION_ID, name, lat/lng)
  within a bbox. The original layer name ENV_MONITORING_LOCATIONS_SVW returns 404 —
  it does not exist in the DataBC WFS catalogue. EMS_MONITORING_LOCN_TYPES_SVW is the
  closest available layer (43,626 stations province-wide, 295 near Fraser River).
  Note: the LONGITUDE property is stored as a positive value in this layer; use
  geometry coordinates instead.
  Verified still live 2026-07 (a HEAD request 404s — this WFS doesn't support HEAD,
  same as several other DataBC/gov.bc.ca WFS layers in this codebase; use GET).

RESULTS (water quality measurements)
  IMPORTANT — source system migrated since this TODO was first written: EMS is
  being replaced by EnMoDS (Environmental Monitoring Data System) as of
  2026-03-05, and EMS results stopped receiving new data on 2026-02-26 (per
  the dataset's own notice). The old resource ID this TODO used to cite
  (76be8cdb-95b7-4a96-aae4-f3f59455fbcb, under the dataset slug
  "bc-env-monitoring-system-ems-monitoring-results") no longer resolves —
  both the ID and the slug were wrong/stale. Verified 2026-07 via the BC Data
  Catalogue API (catalogue.data.gov.bc.ca/api/3/action/package_show):

  Current (EnMoDS) results — dataset slug
  "bc-environmental-monitoring-data-system-results", split into 4 time-tier
  CSV files served from the COMS object API (no auth needed for GET, HTTP
  Range supported):
    - "Current EnMoDS Results" (last 2 years):
      https://coms.api.gov.bc.ca/api/v1/object/84ed1220-bd51-40a8-9f29-d916144e2dfe
      — confirmed via Content-Range header: 336,131,287 bytes (~320 MB),
      appears to be a zip (filename inside the response looks like
      "20250101_to_20260711.csv" — decompress before parsing as CSV).
    - "previous 2-5 years": .../object/6edecb56-d06a-4b2e-9ab0-48584eba3df0
    - "previous 5-10 years": .../object/55e77e5a-ea9d-41e3-ab98-473fafabb0d6
    - "Historic (older than 10 years)": .../object/d88adc20-297e-4585-8de9-76a6342dd8e7
  These 4 together are genuinely multi-GB; for a targeted (non-historical)
  ingest the "last 2 years" file alone is enough for "is this water fishable
  right now" purposes.

  Old (frozen, historical-only) EMS results — dataset slug
  "bc-environmental-monitoring-system-results" — 4 similarly-tiered CSVs at
  pub.data.gov.bc.ca, useful only for pre-2026 history, not current readings.

  EnMoDS also has its own spatial locations dataset (slug
  "environmental-monitoring-data-system-enmods-spatial-sampling-locations",
  CSV or GeoPackage via the same COMS object API) — worth checking whether
  it's a superset of the EMS WFS stations layer above or whether new
  (post-migration) monitoring only shows up there and not in EMS_MONITORING_
  LOCN_TYPES_SVW; not verified either way.

  Practical options, in order of preference:
    1. Download the EnMoDS "last 2 years" zip once per month (results update
       continuously, unlike EMS's frozen annual-ish cadence), decompress,
       filter to nearby MONITORING_LOCATION_ID values, index locally.
    2. DataBC ArcGIS FeatureServer — not available for EnMoDS/EMS results.
    3. CKAN datastore_search — doesn't apply; these are file resources, not
       registered datastore tables.
  Recommended approach unchanged in spirit from the original TODO: download
  once (now monthly, not annually, given EnMoDS's more frequent updates),
  index by MONITORING_LOCATION_ID, join against stations found by this
  adapter, filter to rows near the query point for a targeted ingest.

Current behaviour: fetches stations within bbox (stores EMS_ID + lat/lng to log),
returns 0 readings with a warning until the results fetch is implemented.

Cache TTL: 30 days for stations.
"""

import hashlib
import json
import logging
import math
import time
from pathlib import Path

import httpx

_STATIONS_WFS_URL = (
    "https://openmaps.gov.bc.ca/geo/pub/"
    "WHSE_ENVIRONMENTAL_MONITORING.EMS_MONITORING_LOCN_TYPES_SVW/ows"
)
_STATIONS_TYPE_NAME = "pub:WHSE_ENVIRONMENTAL_MONITORING.EMS_MONITORING_LOCN_TYPES_SVW"
_PAGE_SIZE = 500
_CACHE_DIR = Path("data/cache/bc_ems")
_CACHE_TTL_SECONDS = 30 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

logger = logging.getLogger(__name__)


def fetch_water_quality_readings(
    lat: float,
    lng: float,
    radius_km: float = 50.0,
) -> list:
    """Fetch BC EMS water quality readings within radius_km of lat/lng.

    Currently returns an empty list — stations are discovered and logged
    but result data fetching is not yet implemented (see module TODO above).
    """
    stations = _fetch_stations(lat, lng, radius_km)
    if not stations:
        logger.info("BC EMS: no monitoring stations found within %.0fkm", radius_km)
        return []

    station_ids = [s["ems_id"] for s in stations if s.get("ems_id")]
    logger.warning(
        "BC EMS: found %d stations near (%.4f, %.4f) — "
        "MONITORING_LOCATION_IDs: %s … "
        "water quality results fetch not yet implemented; returning 0 readings. "
        "See water_quality.py TODO for how to implement result ingestion.",
        len(stations),
        lat,
        lng,
        ", ".join(str(s) for s in station_ids[:5]),
    )
    # TODO: implement results fetch — see module docstring for approach
    return []


# ── stations fetch ─────────────────────────────────────────────────────────────


def _fetch_stations(lat: float, lng: float, radius_km: float) -> list[dict]:
    """Return list of {ems_id, name, lat, lng} for stations within bbox."""
    min_lon, min_lat, max_lon, max_lat = _bbox(lat, lng, radius_km)
    # ",CRS:84" tells the server to interpret bbox as lon/lat and reproject into
    # the layer's native BC Albers CRS. Without it, 0 results are returned.
    bbox_str = f"{min_lon:.5f},{min_lat:.5f},{max_lon:.5f},{max_lat:.5f},CRS:84"

    base_params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": _STATIONS_TYPE_NAME,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": bbox_str,
        # sortBy=OBJECTID required for startIndex pagination on this layer —
        # GeoServer rejects startIndex without a sort key when there's no PK.
        "sortBy": "OBJECTID",
        # propertyName omitted — MONITORING_LOCATION_ID replaces EMS_ID and
        # the LONGITUDE property is stored as a positive value in this layer.
        # Use geometry coordinates for reliable lon/lat.
    }

    features: list[dict] = []
    start = 0
    while True:
        params = {**base_params, "startIndex": start, "count": _PAGE_SIZE}
        try:
            data = _cached_get(_STATIONS_WFS_URL, params)
        except Exception as exc:
            logger.error("BC EMS stations WFS failed at startIndex=%d: %s", start, exc)
            break
        page = data.get("features", [])
        features.extend(page)
        logger.info("BC EMS stations WFS startIndex=%d: %d on page", start, len(page))
        if len(page) < _PAGE_SIZE:
            break
        start += _PAGE_SIZE

    stations = []
    for feat in features:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates", [])
        if len(coords) >= 2:
            # Geometry coords are reliable; LONGITUDE property is stored unsigned.
            feature_lon, feature_lat = coords[0], coords[1]
        else:
            continue
        stations.append({
            "ems_id": props.get("MONITORING_LOCATION_ID"),
            "name": props.get("MONITORING_LOCATION_NAME"),
            "lat": feature_lat,
            "lng": feature_lon,
        })

    return stations


# ── HTTP + file cache ──────────────────────────────────────────────────────────


def _cached_get(url: str, params: dict) -> dict:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw_key = url + str(sorted(params.items()))
    key = hashlib.sha256(raw_key.encode()).hexdigest()[:16]
    cache_file = _CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            return json.loads(cache_file.read_text())

    response = httpx.get(
        url,
        params=params,
        headers={"User-Agent": _USER_AGENT},
        timeout=60,
    )
    if response.status_code >= 400:
        logger.error(
            "BC EMS WFS HTTP %d — response body: %s",
            response.status_code,
            response.text[:500],
        )
    response.raise_for_status()
    data = response.json()
    cache_file.write_text(json.dumps(data))
    return data


# ── geometry helpers ───────────────────────────────────────────────────────────


def _bbox(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_deg = radius_km / 111.0
    lon_deg = radius_km / (111.320 * math.cos(math.radians(lat)))
    return (lon - lon_deg, lat - lat_deg, lon + lon_deg, lat + lat_deg)
