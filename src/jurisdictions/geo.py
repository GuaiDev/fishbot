"""Bounding-box jurisdiction lookup for coordinate tagging at ingest time.

Checked in priority order — CA-ON and US states first since that's home,
then western/Maritime Canadian provinces (smallest/most specific boxes),
then CA-QC last since its box is broad enough to swallow the Maritimes'
longitude range if checked first.
Overlaps (e.g. Great Lakes border zones) resolve to whichever bbox matches first.

Every jurisdiction registered in src/ingest/jurisdictions/config.py needs an
entry here — otherwise every global adapter (iNaturalist, GBIF, OSM, weather,
WSC, eBird) tags that jurisdiction's observations 'UNKNOWN' regardless of what
the jurisdiction-specific adapters correctly hardcode.
"""

# (min_lat, max_lat, min_lng, max_lng)
_BOXES: list[tuple[str, float, float, float, float]] = [
    ("CA-ON", 41.6, 56.9, -95.2, -74.3),
    ("US-MI", 41.7, 48.3, -90.4, -82.1),
    ("US-NY", 40.5, 45.0, -79.8, -71.8),
    ("US-OH", 38.4, 42.3, -84.8, -80.5),
    ("US-MN", 43.5, 49.4, -97.2, -89.5),
    ("US-WI", 42.5, 47.1, -92.9, -86.2),
    ("US-PA", 39.7, 42.3, -80.5, -74.7),
    ("CA-BC", 48.2, 60.1, -139.1, -116.0),
    ("CA-AB", 48.9, 60.1, -116.0, -110.0),
    ("CA-SK", 48.9, 60.1, -110.0, -101.36),
    ("CA-MB", 48.9, 60.1, -101.36, -88.9),
    ("CA-NB", 45.0, 48.1, -69.1, -63.6),
    ("CA-PE", 45.9, 47.1, -64.5, -61.9),
    ("CA-NS", 43.3, 47.1, -66.5, -59.6),
    ("CA-QC", 44.9, 62.6, -79.8, -57.1),
]


def jurisdiction_for_coords(lat: float, lng: float) -> str:
    for code, min_lat, max_lat, min_lng, max_lng in _BOXES:
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
            return code
    return "UNKNOWN"
