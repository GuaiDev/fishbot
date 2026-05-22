"""GBIF occurrence fetcher.

Queries fish observations (taxonKey=186, Actinopterygii) for a geographic bounding box.
Aggregates museum records, academic surveys, and citizen science data globally.
All HTTP responses are cached to data/cache/gbif/ with a 24-hour TTL.
Requests are rate-limited to 1/sec between pages.
"""

import hashlib
import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

from src.jurisdictions.geo import jurisdiction_for_coords
from src.models.gbif_observation import GBIFObservation

_API_URL = "https://api.gbif.org/v1/occurrence/search"
_TAXON_KEY = 186  # Actinopterygii — all bony fish
_CACHE_DIR = Path("data/cache/gbif")
_CACHE_TTL_SECONDS = 86400  # 24 hours
_LIMIT = 300  # GBIF max per request
_KM_PER_DEGREE = 111.0
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot; https://github.com/)"


def fetch_gbif_observations(
    lat: float,
    lng: float,
    radius_km: float = 50,
    days_back: int | None = None,
) -> list[GBIFObservation]:
    deg = radius_km / _KM_PER_DEGREE
    base_params: dict[str, Any] = {
        "taxonKey": _TAXON_KEY,
        "decimalLatitude": f"{lat - deg},{lat + deg}",
        "decimalLongitude": f"{lng - deg},{lng + deg}",
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "limit": _LIMIT,
    }

    if days_back is not None:
        since_year = (date.today() - timedelta(days=days_back)).year
        base_params["year"] = f"{since_year},{date.today().year}"

    all_results: list[dict] = []
    offset = 0

    while True:
        params = {**base_params, "offset": offset}
        raw = _cached_get(params)
        results = raw.get("results", [])
        all_results.extend(results)

        if raw.get("endOfRecords", True) or not results:
            break

        offset += len(results)
        time.sleep(1)

    return [_parse_observation(r) for r in all_results if _has_coords(r)]


def _cached_get(params: dict) -> dict:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    cache_file = _CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            return json.loads(cache_file.read_text())

    response = httpx.get(
        _API_URL,
        params=params,
        headers={"User-Agent": _USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    cache_file.write_text(json.dumps(data))
    return data


def _has_coords(result: dict) -> bool:
    return result.get("decimalLatitude") is not None and result.get("decimalLongitude") is not None


def _parse_observation(result: dict) -> GBIFObservation:
    lat = result["decimalLatitude"]
    lng = result["decimalLongitude"]
    species = result.get("species") or result.get("scientificName", "Unknown")

    return GBIFObservation(
        gbif_key=result["key"],
        species=species,
        common_name=result.get("vernacularName"),
        taxon_key=result.get("taxonKey", result.get("speciesKey", 0)),
        lat=lat,
        lng=lng,
        observed_on=_parse_date(result.get("eventDate")),
        country_code=result.get("countryCode"),
        dataset_name=result.get("datasetName"),
        basis_of_record=result.get("basisOfRecord", "UNKNOWN"),
        coordinate_uncertainty_m=result.get("coordinateUncertaintyInMeters"),
        jurisdiction=jurisdiction_for_coords(lat, lng),
    )


def _parse_date(event_date: str | None) -> date | None:
    if not event_date:
        return None
    try:
        return date.fromisoformat(event_date[:10])
    except (ValueError, TypeError):
        return None
