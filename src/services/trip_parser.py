"""Parse natural language fishing trip descriptions into structured data.

Uses Claude to extract fields, then snaps the location to the nearest OHN segment.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

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
        # Scale to approximate km so distance threshold works properly (~44°N)
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


def parse_trip_from_text(
    text: str,
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> dict:
    """Call Claude to extract structured trip data, then snap to nearest OHN segment.

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
    # Strip markdown code fences if the model wraps in ```json ... ```
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

    parsed: dict = json.loads(raw)

    # Resolve lat/lng: parser may infer coordinates from named locations
    lat = parsed.get("lat") or user_lat
    lng = parsed.get("lng") or user_lng

    result = dict(parsed)
    if lat is not None and lng is not None:
        result["lat"] = lat
        result["lng"] = lng
        snap = snap_to_segment(float(lat), float(lng))
        result.update(snap)

    return result
