"""BC Environmental Monitoring System (EMS) water quality ingestion.

Source: DataBC Open Data — WFS 2.0.0 (stations) + DataBC Distribution API (results)

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

RESULTS (water quality measurements)
  TODO: The EMS monitoring results are published via the BC Data Catalogue at:
    https://catalogue.data.gov.bc.ca/dataset/bc-env-monitoring-system-ems-monitoring-results
  The dataset is very large (multi-GB) and is not queryable by bbox via a simple API.
  Practical options:
    1. DataBC Distribution Service — download a full station CSV (large), then
       filter to nearby stations. Resource ID: 76be8cdb-95b7-4a96-aae4-f3f59455fbcb
    2. DataBC ArcGIS FeatureServer — not available for EMS results as of 2026.
    3. BC Data Catalogue CKAN datastore_search — only works for datasets registered
       as datastore resources; EMS results are file-based, not datastore.
  Recommended approach: download the full EMS results CSV once per year (30-day cache),
  index by EMS_ID, then join against stations found by this adapter. The CSV for a
  full province-wide download is ~500 MB. For a targeted ingest, filter the CSV
  to rows whose EMS_ID matches one of the nearby stations.

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
