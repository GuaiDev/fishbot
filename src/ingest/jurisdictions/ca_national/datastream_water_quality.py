"""DataStream water quality — Manitoba and Atlantic Canada.

DataStream is a DFO-funded open water quality database covering:
  - Lake Winnipeg watershed (MB)
  - Atlantic Canada (NS, NB, PEI, NL)

API: OData v4 at https://api.datastream.org/v1/odata/v4/
Requires DATASTREAM_API_KEY environment variable (free registration at
  https://datastream.org/en/api).

Table: water_quality_readings (shared schema with PWQMN, BC EMS, etc.)

Cache TTL: 7 days per location query.
"""

import hashlib
import json
import logging
import math
import os
import time
from pathlib import Path

import httpx

_BASE_URL = "https://api.datastream.org/v1/odata/v4"
_LOCATIONS_URL = f"{_BASE_URL}/Locations"
_RECORDS_URL = f"{_BASE_URL}/Records"
_PAGE_SIZE = 1000
_CACHE_DIR = Path("data/cache/datastream")
_CACHE_TTL_SECONDS = 7 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

# DataStream parameter names → local column names
_PARAM_MAP: dict[str, str] = {
    "Dissolved Oxygen": "do_mgl",
    "Dissolved Oxygen, %Sat": None,  # skip
    "pH": "ph",
    "Temperature, Water": "temp_c",
    "Specific Conductance": "conductivity_us_cm",
    "Turbidity": "turbidity_fnu",
    "Conductivity": "conductivity_us_cm",
}

logger = logging.getLogger(__name__)


def fetch_water_quality_readings(
    lat: float,
    lng: float,
    radius_km: float = 100.0,
) -> list[dict]:
    """Fetch DataStream water quality readings within radius_km of lat/lng.

    Returns 0 records with a clear warning if DATASTREAM_API_KEY is not set.
    """
    api_key = os.environ.get("DATASTREAM_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "DataStream: DATASTREAM_API_KEY not set — skipping water quality fetch. "
            "Register free at https://datastream.org/en/api to enable."
        )
        return []

    stations = _fetch_locations(lat, lng, radius_km, api_key)
    if not stations:
        logger.info(
            "DataStream: no monitoring locations found within %.0fkm of (%.4f, %.4f)",
            radius_km, lat, lng,
        )
        return []

    logger.info("DataStream: %d locations found, fetching records …", len(stations))
    rows: list[dict] = []
    for station in stations:
        try:
            raw_records = _fetch_records(station["id"], api_key)
            parsed = _parse_records(station, raw_records)
            rows.extend(parsed)
        except Exception as exc:
            logger.warning(
                "DataStream: failed to fetch records for location %s: %s", station["id"], exc
            )

    logger.info("DataStream: %d water quality readings fetched", len(rows))
    return rows


def _fetch_locations(lat: float, lng: float, radius_km: float, api_key: str) -> list[dict]:
    """Return DataStream locations within a bbox around lat/lng."""
    min_lon, min_lat, max_lon, max_lat = _bbox(lat, lng, radius_km)
    # OData geo filter — DataStream supports a geographic bounding box via custom param
    params = {
        "$filter": (
            f"geo.intersects(geo.point(Longitude, Latitude), "
            f"geography'POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},"
            f"{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}))')"
        ),
        "$top": str(_PAGE_SIZE),
        "$select": "Id,MonitoringLocationName,LatitudeE7,LongitudeE7,MonitoringLocationTypeCode",
    }
    try:
        data = _cached_get(_LOCATIONS_URL, params, _CACHE_TTL_SECONDS, api_key)
    except Exception as exc:
        logger.error("DataStream: locations fetch failed: %s", exc)
        return []

    stations = []
    for loc in data.get("value", []):
        slat = (loc.get("LatitudeE7") or 0) / 1e7
        slng = (loc.get("LongitudeE7") or 0) / 1e7
        if slat == 0 and slng == 0:
            continue
        stations.append({
            "id": str(loc.get("Id") or ""),
            "name": str(loc.get("MonitoringLocationName") or "Unknown"),
            "lat": slat,
            "lng": slng,
        })
    return stations


def _fetch_records(location_id: str, api_key: str) -> list[dict]:
    """Fetch water quality records for a specific location."""
    params = {
        "$filter": f"MonitoringLocationID eq '{location_id}'",
        "$top": str(_PAGE_SIZE),
        "$select": (
            "Id,ActivityStartDate,CharacteristicName,"
            "ResultSampleFractionText,ResultValue,ResultUnit"
        ),
        "$orderby": "ActivityStartDate desc",
    }
    data = _cached_get(_RECORDS_URL, params, _CACHE_TTL_SECONDS, api_key)
    return data.get("value", [])


def _parse_records(station: dict, raw_records: list[dict]) -> list[dict]:
    """Group raw records by date and map to water_quality_readings rows."""
    # Group measurements by date (one row per station-date)
    by_date: dict[str, dict] = {}
    for rec in raw_records:
        sampled_at = (rec.get("ActivityStartDate") or "")[:10]
        if not sampled_at:
            continue
        param = rec.get("CharacteristicName") or ""
        col = _PARAM_MAP.get(param)
        if col is None:
            continue
        value_raw = rec.get("ResultValue")
        try:
            value = float(value_raw)
        except (TypeError, ValueError):
            continue

        key = f"{station['id']}_{sampled_at}"
        entry = by_date.setdefault(key, {
            "record_id": key,
            "station_id": station["id"],
            "station_name": station["name"],
            "lat": station["lat"],
            "lng": station["lng"],
            "jurisdiction": _jurisdiction_for(station["lat"], station["lng"]),
            "sampled_at": sampled_at,
            "do_mgl": None,
            "ph": None,
            "temp_c": None,
            "conductivity_us_cm": None,
            "turbidity_fnu": None,
        })
        entry[col] = value

    return list(by_date.values())


def _jurisdiction_for(lat: float, lng: float) -> str:
    from src.jurisdictions.geo import jurisdiction_for_coords
    return jurisdiction_for_coords(lat, lng) or "CA"


# ── HTTP + file cache ──────────────────────────────────────────────────────────


def _cached_get(url: str, params: dict, ttl: int, api_key: str) -> dict:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw_key = url + str(sorted(params.items()))
    key = hashlib.sha256(raw_key.encode()).hexdigest()[:16]
    cache_file = _CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl:
            return json.loads(cache_file.read_text())

    response = httpx.get(
        url,
        params=params,
        headers={
            "User-Agent": _USER_AGENT,
            "x-api-key": api_key,
        },
        timeout=60,
    )
    if response.status_code >= 400:
        logger.error(
            "DataStream HTTP %d — url=%s body=%s",
            response.status_code, url, response.text[:300],
        )
    response.raise_for_status()
    data = response.json()
    cache_file.write_text(json.dumps(data))
    return data


# ── geometry helpers ───────────────────────────────────────────────────────────


def _bbox(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_deg = radius_km / 111.0
    lng_deg = radius_km / (111.320 * math.cos(math.radians(lat)))
    return (lng - lng_deg, lat - lat_deg, lng + lng_deg, lat + lat_deg)
