"""iNaturalist observation fetcher.

Queries fish observations (taxon_id=47178, Actinopterygii) for a geographic area.
All HTTP responses are cached to data/cache/inaturalist/ with a 24-hour TTL.
Requests are rate-limited to 1/sec between pages.
"""

import hashlib
import json
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

from src.jurisdictions.geo import jurisdiction_for_coords
from src.models.observation import Observation

_API_URL = "https://api.inaturalist.org/v1/observations"
_TAXON_ID = 47178  # Actinopterygii — all bony fish
_CACHE_DIR = Path("data/cache/inaturalist")
_CACHE_TTL_SECONDS = 86400  # 24 hours
_PER_PAGE = 200


def fetch_observations(
    lat: float,
    lng: float,
    radius_km: float = 50,
    days_back: int = 90,
) -> list[Observation]:
    since = (date.today() - timedelta(days=days_back)).isoformat()
    base_params = {
        "taxon_id": _TAXON_ID,
        "lat": lat,
        "lng": lng,
        "radius": radius_km,
        "d1": since,
        "order_by": "observed_on",
        "order": "desc",
        "per_page": _PER_PAGE,
    }

    all_results: list[dict] = []
    page = 1
    total = None

    while True:
        params = {**base_params, "page": page}
        raw = _cached_get(params)
        results = raw.get("results", [])
        all_results.extend(results)

        if total is None:
            total = raw.get("total_results", 0)

        if len(all_results) >= total or not results:
            break

        page += 1
        time.sleep(1)

    return [_parse_observation(r) for r in all_results if _has_location(r)]


def _cached_get(params: dict) -> dict:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(
        json.dumps(params, sort_keys=True).encode()
    ).hexdigest()[:16]
    cache_file = _CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            return json.loads(cache_file.read_text())

    response = httpx.get(_API_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    cache_file.write_text(json.dumps(data))
    return data


def _has_location(result: dict) -> bool:
    return bool(result.get("location"))


def _parse_observation(result: dict) -> Observation:
    lat_str, lng_str = result["location"].split(",")
    lat, lng = float(lat_str), float(lng_str)

    taxon = result.get("taxon") or {}
    photos = result.get("photos") or []
    photo_url = photos[0]["url"] if photos else None
    user = result.get("user") or {}

    return Observation(
        observation_id=result["id"],
        species=taxon.get("name", "Unknown"),
        common_name=taxon.get("preferred_common_name"),
        taxon_id=taxon.get("id"),
        lat=lat,
        lng=lng,
        observed_on=date.fromisoformat(result["observed_on"]),
        quality_grade=result.get("quality_grade", ""),
        photo_url=photo_url,
        observer=user.get("login"),
        place_guess=result.get("place_guess"),
        jurisdiction=jurisdiction_for_coords(lat, lng),
    )
