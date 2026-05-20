"""Bounding-box jurisdiction lookup for coordinate tagging at ingest time.

Phase 1 only. Checked in priority order — CA-ON first since that's home.
Overlaps (e.g. Great Lakes border zones) resolve to whichever bbox matches first.
"""

# (min_lat, max_lat, min_lng, max_lng)
_BOXES: list[tuple[str, float, float, float, float]] = [
    ("CA-ON", 41.6, 56.9, -95.2, -74.3),
    ("US-MI", 41.7, 48.3, -90.4, -82.1),
    ("US-NY", 40.5, 45.0, -79.8, -71.8),
    ("US-OH", 38.4, 42.3, -84.8, -80.5),
    ("US-MN", 43.5, 49.4, -97.2, -89.5),
    ("US-WI", 42.5, 47.1, -92.9, -86.2),
    ("CA-QC", 44.9, 62.6, -79.8, -57.1),
    ("US-PA", 39.7, 42.3, -80.5, -74.7),
]


def jurisdiction_for_coords(lat: float, lng: float) -> str:
    for code, min_lat, max_lat, min_lng, max_lng in _BOXES:
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
            return code
    return "UNKNOWN"
