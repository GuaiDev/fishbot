"""GBIF occurrence fetcher.

Queries fish occurrences across freshwater-relevant fish orders for a geographic bounding box.
The GBIF backbone does not link fish orders through Actinopterygii at the occurrence level —
fish orders have classKey=null and sit directly under Chordata, so taxonKey/classKey=204
returns 0 occurrences. We enumerate fish-relevant orderKeys directly and merge results.

Targets institutional record types only — museum specimens, surveys, literature, living specimens.
HUMAN_OBSERVATION is excluded because those records are almost entirely iNaturalist mirrors,
which we already ingest separately via the iNaturalist adapter.
No date filter is applied: institutional records frequently lack an event year, and GBIF silently
excludes undated records from year-range queries, wiping out the majority of museum specimens.
All HTTP responses are cached to data/cache/gbif/ with a 24-hour TTL.
Requests are rate-limited to 1/sec between pages.
"""

import hashlib
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from src.jurisdictions.geo import jurisdiction_for_coords
from src.models.gbif_observation import GBIFObservation

_API_URL = "https://api.gbif.org/v1/occurrence/search"
_CACHE_DIR = Path("data/cache/gbif")
_CACHE_TTL_SECONDS = 86400  # 24 hours
_LIMIT = 300  # GBIF max per request
_KM_PER_DEGREE = 111.0
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot; https://github.com/)"

# Fish order keys in the GBIF backbone. classKey=204 (Actinopterygii) exists but returns
# 0 occurrences because the backbone places all fish orders as direct children of Chordata
# with no classKey set. Querying by orderKey is the only reliable way to get fish records.
_FISH_ORDER_KEYS = [
    587,   # Perciformes — perch, darters, bass, sunfish, walleye
    1313,  # Salmoniformes — trout, salmon, whitefish
    1153,  # Cypriniformes — minnows, chubs, dace, shiners, carp
    548,   # Esociformes — pike, pickerel, mudminnow
    708,   # Siluriformes — catfish, madtoms
    549,   # Gadiformes — burbot
    1103,  # Acipenseriformes — sturgeon
    771,   # Petromyzontiformes — lampreys
    1167,  # Lepisosteiformes — gars
    494,   # Amiiformes — bowfin
    538,   # Clupeiformes — shad, herring, alewife
    1068,  # Osmeriformes — smelt
    550,   # Gasterosteiformes — sticklebacks
]

# Exclude HUMAN_OBSERVATION — those records are ~99% iNaturalist mirrors already ingested separately
_BASIS_OF_RECORD = [
    "FOSSIL_SPECIMEN",
    "LITERATURE",
    "LIVING_SPECIMEN",
    "MACHINE_OBSERVATION",
    "MATERIAL_SAMPLE",
    "PRESERVED_SPECIMEN",
]


def fetch_gbif_observations(
    lat: float,
    lng: float,
    radius_km: float = 50,
) -> list[GBIFObservation]:
    deg = radius_km / _KM_PER_DEGREE
    geo_params: dict[str, Any] = {
        "decimalLatitude": f"{lat - deg},{lat + deg}",
        "decimalLongitude": f"{lng - deg},{lng + deg}",
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "limit": _LIMIT,
        "basisOfRecord": _BASIS_OF_RECORD,
    }

    all_results: list[dict] = []

    for order_key in _FISH_ORDER_KEYS:
        base_params = {**geo_params, "orderKey": order_key}
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
