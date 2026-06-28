"""DFO Species at Risk — Critical Habitat (national).

ArcGIS MapServer, bbox query with resultOffset pagination.
Returns critical habitat polygons for federally-listed aquatic SAR across Canada.

Source:
  https://egisp.dfo-mpo.gc.ca/arcgis/rest/services/open_data_donnees_ouvertes/
  CritHab_HabEss_2025/MapServer/0/query

Table: critical_habitat
  habitat_id, species_name, species_common_name, habitat_type,
  jurisdiction, geom_centroid_lat, geom_centroid_lng, sara_status,
  source='DFO_SAR'

Cache TTL: 30 days per bbox tile.
"""

import hashlib
import json
import logging
import math
import time
from datetime import datetime
from pathlib import Path

import httpx

from src.jurisdictions.geo import jurisdiction_for_coords

_QUERY_URL = (
    "https://egisp.dfo-mpo.gc.ca/arcgis/rest/services/"
    "open_data_donnees_ouvertes/CritHab_HabEss_2025/MapServer/0/query"
)
_PAGE_SIZE = 1000
_CACHE_DIR = Path("data/cache/dfo_critical_habitat")
_CACHE_TTL_SECONDS = 30 * 86400
_USER_AGENT = "fishbot/1.0 (personal fishing exploration bot)"

logger = logging.getLogger(__name__)

# Candidate field names for each attribute — the service may rename fields between releases.
_SCIENTIFIC_NAME_FIELDS = ["SCIENTIFIC_NAME", "Scientific_Name", "NomScientifique", "SCI_NAME"]
_COMMON_NAME_FIELDS = ["COMMON_NAME", "Common_Name", "NomCommun", "COMMON_NAME_EN", "SPECIES_EN"]
_HABITAT_TYPE_FIELDS = [
    "HABITAT_TYPE_EN", "HabitatType", "TYPE_EN", "HABITAT_TYPE", "TYPE_HABITAT_EN"
]
_STATUS_FIELDS = ["STATUS_EN", "SARA_STATUS", "COSEWIC_STATUS", "Status_EN", "SCHEDULE"]


def _pick(attrs: dict, candidates: list[str]) -> str:
    for key in candidates:
        val = (attrs.get(key) or "").strip()
        if val:
            return val
    return ""


def fetch_critical_habitat(
    lat: float,
    lng: float,
    radius_km: float = 100.0,
) -> list[dict]:
    """Fetch DFO critical habitat records within radius_km of lat/lng.

    Returns list of row dicts ready for upsert into critical_habitat table.
    Cached 30 days per request page.
    """
    min_lon, min_lat, max_lon, max_lat = _bbox(lat, lng, radius_km)
    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    base_params = {
        "f": "json",
        "geometry": bbox_str,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "returnCentroid": "true",
        "resultRecordCount": str(_PAGE_SIZE),
    }

    rows: list[dict] = []
    offset = 0
    now = datetime.utcnow().isoformat()

    while True:
        params = {**base_params, "resultOffset": str(offset)}
        try:
            data = _cached_get(_QUERY_URL, params)
        except Exception as exc:
            logger.error("DFO critical habitat request failed at offset=%d: %s", offset, exc)
            break

        features = data.get("features", [])
        logger.info(
            "DFO critical habitat: offset=%d → %d features (exceededTransferLimit=%s)",
            offset, len(features), data.get("exceededTransferLimit", False),
        )

        for feat in features:
            attrs = feat.get("attributes") or {}
            geom = feat.get("geometry") or {}
            centroid = feat.get("centroid") or {}

            # Use returnCentroid centroid if available; otherwise use geometry envelope center
            if centroid.get("x") is not None:
                clon, clat = centroid["x"], centroid["y"]
            elif "xmin" in geom:
                clon = (geom["xmin"] + geom["xmax"]) / 2
                clat = (geom["ymin"] + geom["ymax"]) / 2
            else:
                # Polygon rings — compute centroid from first ring mean
                rings = geom.get("rings", [])
                if rings and rings[0]:
                    pts = rings[0]
                    clon = sum(p[0] for p in pts) / len(pts)
                    clat = sum(p[1] for p in pts) / len(pts)
                else:
                    continue

            oid = attrs.get("OBJECTID") or attrs.get("FID") or attrs.get("objectid")
            if oid is None:
                continue

            species_sci = _pick(attrs, _SCIENTIFIC_NAME_FIELDS)
            species_common = _pick(attrs, _COMMON_NAME_FIELDS)
            habitat_type = _pick(attrs, _HABITAT_TYPE_FIELDS)
            sara_status = _pick(attrs, _STATUS_FIELDS)

            jur = jurisdiction_for_coords(clat, clon) or "CA"

            rows.append({
                "habitat_id": f"DFO_{oid}",
                "species_name": species_sci or f"OID_{oid}",
                "species_common_name": species_common or None,
                "habitat_type": habitat_type or None,
                "jurisdiction": jur,
                "geom_centroid_lat": round(clat, 5),
                "geom_centroid_lng": round(clon, 5),
                "sara_status": sara_status or None,
                "source": "DFO_SAR",
                "ingested_at": now,
            })

        if not data.get("exceededTransferLimit", False) or len(features) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    logger.info("DFO critical habitat: %d records fetched", len(rows))
    return rows


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
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS error: {data['error']}")
    cache_file.write_text(json.dumps(data))
    return data


# ── geometry helpers ───────────────────────────────────────────────────────────


def _bbox(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_deg = radius_km / 111.0
    lng_deg = radius_km / (111.320 * math.cos(math.radians(lat)))
    return (lng - lng_deg, lat - lat_deg, lng + lng_deg, lat + lat_deg)
