"""Parse natural language fishing trip descriptions into structured data.

Uses Claude to extract fields, then resolves the location through a four-layer
pipeline (name match → landmark anchor → Nominatim geocode → unresolved) before
snapping to the nearest OHN segment centroid.
"""

import difflib
import json
import logging
import math
import re
import time
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from src.agent.client import get_client, get_model

logger = logging.getLogger(__name__)

_FEATURE_MATRIX_PATH = Path("data/processed/sdm_feature_matrix.parquet")
_SNAP_RADIUS_KM = 5.0  # generous radius for user-described locations

_SYSTEM_PROMPT = (
    "You are a fishing trip parser. "
    "Extract structured data from natural language fishing trip descriptions. "
    "Always respond with valid JSON only. "
    "If information is not mentioned, use null. "
    "Be generous with inference — if someone says 'near the bridge on Bronte Creek' "
    "infer it's likely in the Oakville/Burlington area."
)

_USER_PROMPT_TEMPLATE = """Parse this fishing trip log: {text}

Return JSON with these fields:
{{
  "date": "YYYY-MM-DD or null",
  "location_description": "string",
  "waterbody_name": "string or null",
  "lat": null,
  "lng": null,
  "species_caught": ["list of species"],
  "species_observed": ["list of species"],
  "species_targeted": "string or null",
  "conditions": {{
    "water_level": "low/normal/high/null",
    "water_clarity": "clear/stained/turbid/null",
    "water_temp_c": null,
    "weather": "string or null",
    "flow_trend": "rising/falling/stable/null"
  }},
  "habitat_notes": "string or null",
  "spot_type": "riffle/pool/confluence/culvert/beaver_dam/pond/lake/other/null",
  "fish_count": null,
  "was_productive": null,
  "gear": "string or null",
  "notes": "string or null"
}}"""

# ── location resolution ───────────────────────────────────────────────────────

_WATERBODY_RE = re.compile(
    r"\b([A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+)*)\s+"
    r"(Creek|River|Brook|Stream|Run|Branch|Channel|Drain|Ditch|Tributary)\b",
    re.IGNORECASE,
)
_LAKE_RE = re.compile(r"\bLake\s+([A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+)*)\b", re.IGNORECASE)

_LANDMARK_KEYWORDS = {
    "bridge", "dam", "beaver dam", "confluence", "falls", "weir",
    "culvert", "crossing", "pool below", "riffle at", "upstream of",
    "below the", "above the",
}


def _extract_waterbody_name(text: str) -> str | None:
    """Regex-extract the most prominent waterbody name from free text. No API call."""
    m = _WATERBODY_RE.search(text)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    m = _LAKE_RE.search(text)
    if m:
        return f"Lake {m.group(1)}"
    return None


def _parse_centroid_wkt(wkt: str) -> tuple[float, float] | None:
    """Parse OHN POINT (lng lat) WKT. Returns (lat, lng) or None."""
    m = re.match(r"POINT\s*\(([^ ]+)\s+([^ )]+)\)", wkt)
    if m:
        return float(m.group(2)), float(m.group(1))  # lat, lng
    return None


def _has_landmark(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _LANDMARK_KEYWORDS)


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _nominatim_geocode(query: str) -> tuple[float, float] | None:
    """Geocode via Nominatim. Appends ', Ontario, Canada'. Rate-limit: 1s sleep."""
    time.sleep(1)
    q = urllib.parse.quote(f"{query}, Ontario, Canada")
    url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=3"
    headers = {"User-Agent": "FishBot/1.0 (personal fishing intelligence tool)"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            results = json.loads(r.read())
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        logger.warning("Nominatim geocode failed for %r: %s", query, e)
    return None


def _nearest_ohn_km(lat: float, lng: float) -> float:
    """Distance in km from (lat, lng) to the nearest OHN segment centroid."""
    tree, _ = _load_snap_data()
    if tree is None:
        return 0.0  # can't verify — assume within range
    dist_km, _ = tree.query([[lat * 111.0, lng * 80.5]])
    return float(dist_km[0])


def _query_segments_by_name(name: str, db: Any) -> list[dict]:
    """Return up to 20 named OHN segments matching name (case-insensitive LIKE)."""
    rows = db.execute(
        "SELECT ogf_id, name, geom_wkt FROM stream_segments "
        "WHERE LOWER(name) LIKE LOWER(?) ORDER BY LENGTH(name) LIMIT 20",
        [f"%{name}%"],
    ).fetchall()
    out = []
    for ogf_id, seg_name, wkt in rows:
        centroid = _parse_centroid_wkt(wkt or "")
        if centroid:
            out.append({"ogf_id": ogf_id, "name": seg_name, "lat": centroid[0], "lng": centroid[1]})
    return out


def _most_fished_candidate(candidates: list[dict], db: Any) -> dict | None:
    """Return the candidate segment most visited in parsed_trips, or None."""
    if "parsed_trips" not in db.table_names():
        return None
    ids = [c["ogf_id"] for c in candidates]
    if not ids:
        return None
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT ogf_id, COUNT(*) AS cnt FROM parsed_trips "
        f"WHERE ogf_id IN ({placeholders}) GROUP BY ogf_id ORDER BY cnt DESC LIMIT 1",
        ids,
    ).fetchall()
    if rows:
        best_id = rows[0][0]
        return next((c for c in candidates if c["ogf_id"] == best_id), None)
    return None


def _pick_closest_candidate(candidates: list[dict], lat: float, lng: float) -> dict:
    return min(candidates, key=lambda c: _haversine(lat, lng, c["lat"], c["lng"]))


def _result(
    lat: float | None,
    lng: float | None,
    method: str,
    confidence: float,
    candidates: list[int],
    needs_user_input: bool = False,
    prompt_message: str | None = None,
) -> dict:
    return {
        "lat": lat,
        "lng": lng,
        "method": method,
        "confidence": confidence,
        "candidates": candidates,
        "needs_user_input": needs_user_input,
        "prompt_message": prompt_message,
    }


def resolve_location(location_text: str, db: Any) -> dict:
    """Resolve a free-text location to OHN segment coordinates.

    Layer 1 — named waterbody lookup in stream_segments.
    Layer 2 — Nominatim geocode + closest-candidate selection (landmark anchor).
    Layer 3 — Nominatim geocode on the full query text.
    Layer 4 — unresolved, escalate to user.
    """
    # ── Layer 1: Named waterbody lookup ──────────────────────────────────────
    waterbody_name = _extract_waterbody_name(location_text)
    candidates: list[dict] = []

    if waterbody_name:
        candidates = _query_segments_by_name(waterbody_name, db)

        if len(candidates) == 1:
            c = candidates[0]
            return _result(c["lat"], c["lng"], "name_match", 0.85, [c["ogf_id"]])

        if 2 <= len(candidates) <= 5:
            # Try sub-location disambiguation via difflib against segment names,
            # then fall back to centroid of candidates.
            qualifier_words = [
                w for w in location_text.split()
                if len(w) > 4 and w.lower() not in waterbody_name.lower().split()
            ]
            if qualifier_words:
                seg_names = [c["name"] for c in candidates]
                best_names = difflib.get_close_matches(
                    " ".join(qualifier_words), seg_names, n=1, cutoff=0.4
                )
                if best_names:
                    matched = next(c for c in candidates if c["name"] == best_names[0])
                    return _result(
                        matched["lat"], matched["lng"], "name_match", 0.75,
                        [matched["ogf_id"]]
                    )
            avg_lat = sum(c["lat"] for c in candidates) / len(candidates)
            avg_lng = sum(c["lng"] for c in candidates) / len(candidates)
            return _result(avg_lat, avg_lng, "name_match", 0.75, [c["ogf_id"] for c in candidates])

        if len(candidates) >= 6:
            # ── Layer 2: Landmark anchor ──────────────────────────────────────
            # Geocode the full location text (which may include landmark details)
            # and pick the candidate closest to the result.
            if _has_landmark(location_text) or True:  # always try for 6+ candidates
                geo = _nominatim_geocode(location_text)
                if geo:
                    geo_lat, geo_lng = geo
                    best = _pick_closest_candidate(candidates, geo_lat, geo_lng)
                    dist = _haversine(geo_lat, geo_lng, best["lat"], best["lng"])
                    if dist <= 15.0:
                        method = "landmark" if _has_landmark(location_text) else "name_match"
                        conf = 0.9 if method == "landmark" else 0.75
                        return _result(best["lat"], best["lng"], method, conf, [best["ogf_id"]])

            # Fall back: most-fished candidate or user prompt
            mf = _most_fished_candidate(candidates, db)
            if mf:
                return _result(
                    mf["lat"], mf["lng"], "name_match", 0.4, [mf["ogf_id"]],
                    needs_user_input=True,
                    prompt_message=(
                        f"I found {len(candidates)} '{waterbody_name}' segments but couldn't "
                        "narrow it down. Could you add a landmark — road, bridge, or area? "
                        "(e.g. 'Bronte Creek at Britannia Rd')"
                    ),
                )

    # ── Layer 3: Nominatim geocode on full text ───────────────────────────────
    geo = _nominatim_geocode(location_text)
    if geo:
        geo_lat, geo_lng = geo
        if _nearest_ohn_km(geo_lat, geo_lng) <= 2.0:
            return _result(geo_lat, geo_lng, "geocode_fallback", 0.6, [])

    # ── Layer 4: Unresolved ────────────────────────────────────────────────────
    return _result(
        None, None, "unresolved", 0.0, [],
        needs_user_input=True,
        prompt_message=(
            f"I couldn't pin '{location_text}' to a specific stream segment. "
            "Could you add one of: a road/bridge name, a nearby intersection, "
            "or rough coordinates? (e.g. 'Bronte Creek at Britannia Rd')"
        ),
    )


# ── cKDTree snap ──────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_snap_data() -> tuple:
    """Lazy-load feature matrix and build KD tree. Cached after first call."""
    if not _FEATURE_MATRIX_PATH.exists():
        return None, None

    try:
        import pandas as pd
        from scipy.spatial import cKDTree

        df = pd.read_parquet(
            _FEATURE_MATRIX_PATH,
            columns=["ogf_id", "centroid_lat", "centroid_lng", "stream_order", "watercourse_name"],
        )
        df = df.dropna(subset=["centroid_lat", "centroid_lng"])
        coords = np.array(
            [[lat * 111.0, lng * 80.5] for lat, lng in zip(df["centroid_lat"], df["centroid_lng"])]
        )
        tree = cKDTree(coords)
        return tree, df.reset_index(drop=True)
    except Exception as e:
        logger.warning("Failed to load snap index: %s", e)
        return None, None


def snap_to_segment(lat: float, lng: float) -> dict:
    """Return the nearest OHN segment within _SNAP_RADIUS_KM, or {} if none found."""
    tree, df = _load_snap_data()
    if tree is None or df is None:
        return {}

    query = np.array([[lat * 111.0, lng * 80.5]])
    dist_km, idx = tree.query(query)
    dist_km = float(dist_km[0])
    idx = int(idx[0])

    if dist_km > _SNAP_RADIUS_KM:
        return {}

    row = df.iloc[idx]
    name = row["watercourse_name"]
    return {
        "ogf_id": int(row["ogf_id"]),
        "distance_to_segment_m": round(dist_km * 1000, 1),
        "segment_stream_order": (
            int(row["stream_order"]) if row["stream_order"] == row["stream_order"] else None
        ),
        "segment_watercourse_name": str(name) if name and str(name) != "nan" else None,
    }


# ── main entry point ──────────────────────────────────────────────────────────


def parse_trip_from_text(
    text: str,
    user_lat: float | None = None,
    user_lng: float | None = None,
    db: Any = None,
) -> dict:
    """Call Claude to extract structured trip data, resolve location, snap to OHN segment.

    When db is provided and Claude doesn't return coordinates, resolve_location() is
    called to infer lat/lng from the location description. Returns a special
    {"status": "needs_location", "message": ...} dict when location is genuinely
    unresolvable and no lat/lng hint is available.

    Returns a dict with all parsed fields plus ogf_id, distance_to_segment_m,
    segment_stream_order, segment_watercourse_name when a segment is found.
    """
    client = get_client()
    model = get_model()

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _USER_PROMPT_TEMPLATE.format(text=text)}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

    parsed: dict = json.loads(raw)

    lat = parsed.get("lat") or user_lat
    lng = parsed.get("lng") or user_lng
    loc_meta: dict = {}

    # Layer resolution when Claude didn't infer coordinates
    if (lat is None or lng is None) and db is not None:
        location_text = (
            parsed.get("waterbody_name")
            or parsed.get("location_description")
            or text
        )
        loc = resolve_location(location_text, db)
        if loc["needs_user_input"] and loc["lat"] is None:
            return {"status": "needs_location", "message": loc["prompt_message"]}
        if loc["lat"] is not None:
            lat = loc["lat"]
            lng = loc["lng"]
            loc_meta = {
                "location_method": loc["method"],
                "location_confidence": loc["confidence"],
            }

    result = dict(parsed)
    if lat is not None and lng is not None:
        result["lat"] = lat
        result["lng"] = lng
        snap = snap_to_segment(float(lat), float(lng))
        result.update(snap)

    result.update(loc_meta)
    return result
