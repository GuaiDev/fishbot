"""OpenStreetMap water features and access points via Overpass API.

Cache TTL: 30 days — water bodies and access infrastructure change rarely.
Rate limit: 0.5s sleep before every live request (Overpass polite use policy).
"""

import hashlib
import json
import math
import time
from pathlib import Path

import httpx

from src.jurisdictions.geo import jurisdiction_for_coords
from src.models.water_feature import AccessPoint, WaterFeature

# Primary + community mirror — tried in order on each attempt
_OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
_RETRY_DELAYS = [5, 15, 30]  # seconds between attempts; 4 total (initial + 3 retries)
_CACHE_DIR = Path("data/cache/osm")
_CACHE_TTL_SECONDS = 2_592_000  # 30 days
_USER_AGENT = "fishbot/1.0 (personal fishing assistant)"


def fetch_water_features(lat: float, lng: float, radius_km: float = 25) -> list[WaterFeature]:
    """Fetch water bodies near lat/lng within radius_km. Cached 30 days."""
    radius_m = int(radius_km * 1000)
    query = (
        f"[out:json][timeout:60];\n"
        f"(\n"
        f'  node["natural"="water"](around:{radius_m},{lat},{lng});\n'
        f'  way["natural"="water"](around:{radius_m},{lat},{lng});\n'
        f'  node["waterway"~"^(river|stream|canal|drain|ditch)$"](around:{radius_m},{lat},{lng});\n'
        f'  way["waterway"~"^(river|stream|canal|drain|ditch)$"](around:{radius_m},{lat},{lng});\n'
        f'  node["natural"="wetland"](around:{radius_m},{lat},{lng});\n'
        f'  way["natural"="wetland"](around:{radius_m},{lat},{lng});\n'
        f'  node["natural"="bay"](around:{radius_m},{lat},{lng});\n'
        f'  way["natural"="bay"](around:{radius_m},{lat},{lng});\n'
        f");\n"
        f"out geom;"
    )
    data = _overpass_query(query)
    features = []
    for element in data.get("elements", []):
        feature = _parse_water_feature(element)
        if feature is not None:
            features.append(feature)
    return features


def fetch_access_points(lat: float, lng: float, radius_km: float = 25) -> list[AccessPoint]:
    """Fetch access points near lat/lng within radius_km. Cached 30 days."""
    radius_m = int(radius_km * 1000)
    query = (
        f"[out:json][timeout:60];\n"
        f"(\n"
        f'  node["leisure"="fishing"](around:{radius_m},{lat},{lng});\n'
        f'  way["leisure"="fishing"](around:{radius_m},{lat},{lng});\n'
        f'  node["amenity"="boat_ramp"](around:{radius_m},{lat},{lng});\n'
        f'  way["amenity"="boat_ramp"](around:{radius_m},{lat},{lng});\n'
        f'  node["highway"="trailhead"](around:{radius_m},{lat},{lng});\n'
        f'  way["highway"="trailhead"](around:{radius_m},{lat},{lng});\n'
        f'  node["leisure"="nature_reserve"](around:{radius_m},{lat},{lng});\n'
        f'  way["leisure"="nature_reserve"](around:{radius_m},{lat},{lng});\n'
        f'  node["boundary"="protected_area"](around:{radius_m},{lat},{lng});\n'
        f'  way["boundary"="protected_area"](around:{radius_m},{lat},{lng});\n'
        f'  node["leisure"="park"](around:{radius_m},{lat},{lng});\n'
        f'  way["leisure"="park"](around:{radius_m},{lat},{lng});\n'
        f'  node["highway"="layby"](around:{radius_m},{lat},{lng});\n'
        f'  way["highway"="layby"](around:{radius_m},{lat},{lng});\n'
        f'  node["amenity"="parking"](around:{radius_m},{lat},{lng});\n'
        f'  way["amenity"="parking"](around:{radius_m},{lat},{lng});\n'
        f");\n"
        f"out geom;"
    )
    data = _overpass_query(query)
    points = []
    for element in data.get("elements", []):
        point = _parse_access_point(element)
        if point is not None:
            points.append(point)
    return points


def _overpass_query(query_str: str) -> dict:
    """POST to Overpass API with 30-day file cache. Sleeps 0.5s before live requests."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(query_str.encode()).hexdigest()[:16]
    cache_file = _CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            return json.loads(cache_file.read_text())

    time.sleep(0.5)
    last_exc: Exception = RuntimeError("No Overpass endpoints available")
    for attempt in range(len(_RETRY_DELAYS) + 1):
        if attempt > 0:
            time.sleep(_RETRY_DELAYS[attempt - 1])
        for url in _OVERPASS_URLS:
            try:
                response = httpx.post(
                    url,
                    data={"data": query_str},
                    headers={"User-Agent": _USER_AGENT},
                    timeout=90,
                )
                response.raise_for_status()
                data = response.json()
                cache_file.write_text(json.dumps(data))
                return data
            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
                last_exc = e
    raise last_exc


def _parse_water_feature(element: dict) -> WaterFeature | None:
    etype = element.get("type")
    eid = element.get("id")
    tags = element.get("tags", {})

    feature_type = _water_feature_type(tags)
    if feature_type is None:
        return None

    centroid = _centroid(element)
    if centroid is None:
        return None
    c_lat, c_lng = centroid

    geometry = element.get("geometry", [])
    area_m2 = _polygon_area_m2(geometry) if etype == "way" else None

    return WaterFeature(
        osm_id=f"{etype}/{eid}",
        feature_type=feature_type,
        name=tags.get("name") or None,
        lat=c_lat,
        lng=c_lng,
        jurisdiction=jurisdiction_for_coords(c_lat, c_lng),
        area_m2=area_m2,
        tags=tags,
    )


def _parse_access_point(element: dict) -> AccessPoint | None:
    etype = element.get("type")
    eid = element.get("id")
    tags = element.get("tags", {})

    access_type = _access_type_from_tags(tags)
    if access_type is None:
        return None

    centroid = _centroid(element)
    if centroid is None:
        return None
    c_lat, c_lng = centroid

    return AccessPoint(
        osm_id=f"{etype}/{eid}",
        access_type=access_type,
        name=tags.get("name") or None,
        lat=c_lat,
        lng=c_lng,
        jurisdiction=jurisdiction_for_coords(c_lat, c_lng),
        tags=tags,
    )


def _water_feature_type(tags: dict) -> str | None:
    waterway = tags.get("waterway", "")
    natural = tags.get("natural", "")
    water = tags.get("water", "")

    if waterway == "river":
        return "river"
    if waterway == "stream":
        return "stream"
    if waterway == "canal":
        return "canal"
    if waterway == "ditch":
        return "ditch"
    if waterway == "drain":
        return "drain"
    if natural == "wetland":
        return "wetland"
    if natural == "bay":
        return "bay"
    if natural == "water":
        if water == "pond":
            return "pond"
        if water == "reservoir":
            return "reservoir"
        return "lake"
    return None


def _access_type_from_tags(tags: dict) -> str | None:
    if tags.get("amenity") == "boat_ramp":
        return "boat_launch"
    if tags.get("leisure") == "fishing":
        return "fishing_spot"
    if tags.get("highway") == "trailhead":
        return "trail_head"
    if tags.get("leisure") == "nature_reserve":
        return "conservation_area"
    if tags.get("boundary") == "protected_area":
        return "public_land"
    if tags.get("leisure") == "park":
        return "park"
    if tags.get("highway") == "layby":
        return "parking"
    if tags.get("amenity") == "parking":
        return "parking"
    return None


def _centroid(element: dict) -> tuple[float, float] | None:
    etype = element.get("type")
    if etype == "node":
        lat = element.get("lat")
        lon = element.get("lon")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
        return None
    if etype in ("way", "relation"):
        geometry = element.get("geometry", [])
        if not geometry:
            return None
        lats = [g["lat"] for g in geometry if "lat" in g]
        lons = [g["lon"] for g in geometry if "lon" in g]
        if not lats or not lons:
            return None
        return sum(lats) / len(lats), sum(lons) / len(lons)
    return None


def _polygon_area_m2(geometry: list[dict]) -> float | None:
    """Shoelace formula for a closed-way polygon. Returns approximate area in m²."""
    if len(geometry) < 4:
        return None
    first, last = geometry[0], geometry[-1]
    if first["lat"] != last["lat"] or first["lon"] != last["lon"]:
        return None  # open line, not a polygon

    avg_lat = sum(g["lat"] for g in geometry) / len(geometry)
    lat_m = 111_132.0
    lng_m = 111_132.0 * math.cos(math.radians(avg_lat))

    pts = [(g["lon"] * lng_m, g["lat"] * lat_m) for g in geometry]
    n = len(pts)
    area = 0.0
    for i in range(n - 1):
        area += pts[i][0] * pts[i + 1][1]
        area -= pts[i + 1][0] * pts[i][1]
    return abs(area) / 2.0
