"""MNRF regulations service — agent and CLI interface for Ontario fishing regulations."""

import json
import re

from src.storage.database import get_db
from src.storage.regulations import (
    count_regulation_chunks,
    get_regulation_chunk,
    upsert_regulation_chunks,
)

# Rough FMZ bounding boxes for lat/lng → zone estimation.
# Format: (zone, min_lat, max_lat, min_lng, max_lng)
# Ordered most-specific first. Overlap is intentional — first match wins.
# These are approximations; zone boundaries are irregular polygons.
_FMZ_BOXES: list[tuple[int, float, float, float, float]] = [
    (4,  43.9, 46.0, -82.0, -81.0),   # Bruce Peninsula / Manitoulin
    (1,  41.6, 42.9, -83.5, -78.8),   # Lake Erie north shore
    (2,  42.0, 43.8, -83.0, -81.0),   # Lake St. Clair / Huron south
    (3,  43.5, 45.0, -82.0, -80.5),   # Georgian Bay south / Huron
    (5,  43.0, 45.3, -80.5, -79.0),   # Simcoe / Muskoka south / GTA lake shore
    (6,  44.2, 45.2, -79.0, -77.0),   # Kawartha / Trent
    (9,  44.5, 45.5, -76.5, -75.5),   # Rideau Lakes
    (8,  44.0, 45.2, -77.0, -75.8),   # Frontenac / Kingston
    (7,  44.0, 45.5, -77.5, -74.5),   # Eastern Ontario / St. Lawrence
    (11, 44.7, 46.5, -79.0, -77.0),   # Haliburton / Bancroft
    (10, 45.0, 47.5, -78.5, -74.5),   # Ottawa River / Renfrew
    (13, 44.8, 46.5, -81.0, -79.5),   # Parry Sound / Muskoka north
    (12, 45.0, 47.0, -80.5, -78.5),   # Algonquin / Nipissing
    (14, 45.5, 47.5, -82.0, -79.0),   # Sudbury / North Bay
    (15, 46.0, 47.5, -84.5, -83.0),   # Sault Ste. Marie
    (16, 47.5, 49.5, -86.5, -83.0),   # Thunder Bay east / White River
    (19, 49.0, 50.5, -95.2, -92.0),   # Kenora / Lake of the Woods
    (17, 47.5, 50.0, -92.0, -86.5),   # Thunder Bay north / Atikokan
    (18, 49.0, 51.5, -95.2, -88.0),   # Sioux Lookout / Red Lake
    (20, 50.0, 56.9, -88.0, -77.0),   # Far north / James Bay
]

_MAX_SPECIES_CONTEXT = 3000  # chars returned when species filter applied
_MAX_OVERVIEW = 2000         # chars returned for zone overview (no species filter)


def ingest_regulations() -> int:
    """Download and parse MNRF regulations PDF. Returns number of zone chunks stored."""
    from src.ingest.jurisdictions.ca_on.regulations import (
        download_regulations_pdf,
        extract_zone_chunks,
    )

    pdf_path = download_regulations_pdf()
    chunks = extract_zone_chunks(pdf_path)
    if not chunks:
        return 0
    db = get_db()
    upsert_regulation_chunks(db, chunks)
    return len(chunks)


def get_regulations_for_agent(
    zone: int | None = None,
    species: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> str:
    """Return regulations text for the specified FMZ zone as a JSON string."""
    if zone is None:
        if lat is not None and lng is not None:
            zone = _estimate_fmz(lat, lng)
        if zone is None:
            return json.dumps(
                {
                    "error": (
                        "Ontario is divided into 20 Fisheries Management Zones (FMZs). "
                        "Provide 'zone' (1-20) or lat/lng coordinates for zone estimation."
                    )
                }
            )

    db = get_db()

    if "regulation_chunks" not in db.table_names() or count_regulation_chunks(db) == 0:
        return json.dumps(
            {
                "zone": zone,
                "error": (
                    "Regulations database is empty. Run `make ingest` to download and "
                    "parse the MNRF Recreational Fishing Regulations Summary PDF."
                ),
            }
        )

    chunk = get_regulation_chunk(db, zone)
    if chunk is None:
        return json.dumps(
            {
                "zone": zone,
                "error": (
                    f"No regulations found for FMZ {zone}. "
                    "Run `make ingest` to populate the database."
                ),
            }
        )

    if species:
        text, truncated = _extract_species_context(chunk.raw_text, species)
    else:
        text = chunk.raw_text[:_MAX_OVERVIEW]
        truncated = len(chunk.raw_text) > _MAX_OVERVIEW

    result: dict = {
        "zone": chunk.zone,
        "regulation_year": chunk.regulation_year,
        "jurisdiction": chunk.jurisdiction,
        "species_query": species,
        "text": text,
        "source_url": chunk.source_url,
        "disclaimer": (
            "Always verify limits, seasons, and slot sizes against the current MNRF "
            "Recreational Fishing Regulations Summary before fishing. "
            "Specific waterbodies may have special orders that override zone defaults."
        ),
    }
    if truncated:
        result["truncated"] = True
        result["truncation_note"] = (
            "Text was truncated. Full regulations available in the MNRF PDF."
        )
    if lat is not None and lng is not None and zone is not None:
        result["zone_detection"] = "approximate — provide zone directly for certainty"

    return json.dumps(result)


def _estimate_fmz(lat: float, lng: float) -> int | None:
    """Return the most likely FMZ zone for given coordinates, or None if outside Ontario."""
    for zone, min_lat, max_lat, min_lng, max_lng in _FMZ_BOXES:
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
            return zone
    return None


def _extract_species_context(text: str, species: str) -> tuple[str, bool]:
    """Find all mentions of the species in the text and return surrounding context.

    Returns (extracted_text, truncated_flag).
    """
    pattern = re.compile(re.escape(species), re.IGNORECASE)
    matches = list(pattern.finditer(text))

    if not matches:
        # Species not found by name — return zone overview so LLM can reason
        overview = text[:_MAX_OVERVIEW]
        note = (
            f"\n\n[Note: '{species}' not found by exact name in this zone's text. "
            "The species may appear under a different name or may not have special "
            "rules listed (general limits apply). Full zone overview shown above.]"
        )
        return overview + note, len(text) > _MAX_OVERVIEW

    window = 600  # chars of context around each match
    snippets: list[str] = []
    seen_ranges: list[tuple[int, int]] = []

    for m in matches[:5]:  # cap at 5 occurrences
        start = max(0, m.start() - window)
        end = min(len(text), m.end() + window)
        # Skip if this range substantially overlaps one already added
        if any(abs(start - s) < window for s, _ in seen_ranges):
            continue
        seen_ranges.append((start, end))
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet = snippet + "…"
        snippets.append(snippet)

    combined = "\n\n---\n\n".join(snippets)
    truncated = len(combined) > _MAX_SPECIES_CONTEXT
    return combined[:_MAX_SPECIES_CONTEXT], truncated
