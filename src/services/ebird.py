"""eBird piscivore activity service — agent and CLI interface."""

import importlib
import json
import logging
from collections import defaultdict
from datetime import date

from src.storage.bird_observations import query_bird_observations, upsert_bird_observations
from src.storage.database import get_db

# src/ingest/global/ can't be imported normally — "global" is a keyword
_ebird_ingest = importlib.import_module("src.ingest.global.ebird")
fetch_piscivore_observations = _ebird_ingest.fetch_piscivore_observations

logger = logging.getLogger(__name__)

# Osprey and merganser: confirmed active pursuit of fish
# Heron and kingfisher: strong presence indicators but wider foraging range
# Cormorant: productive habitat signal but also follows invertebrate prey
_CONFIDENCE_HIGH = {"osprey1", "commer1"}
_CONFIDENCE_MODERATE = {"grbher3", "belkin1"}
# doccor alone → "low"


def fetch_and_store(
    lat: float,
    lng: float,
    radius_km: float = 50,
    days_back: int = 30,
) -> int:
    """Fetch piscivore observations and upsert to DB. Returns count stored."""
    obs = fetch_piscivore_observations(lat, lng, radius_km, days_back)
    if obs:
        upsert_bird_observations(get_db(), obs)
    return len(obs)


def get_piscivore_activity_for_agent(
    lat: float,
    lng: float,
    radius_km: float = 50,
    days_back: int = 30,
) -> str:
    """Return JSON piscivore activity summary for a location.

    Uses cached DB data.  Observations are grouped by species and sorted by
    recency.  fish_presence_confidence is derived from which species are
    active: osprey/merganser = high, heron/kingfisher = moderate, cormorant
    alone = low, no sightings = none.
    """
    db = get_db()
    records = query_bird_observations(db, lat, lng, radius_km, days_back)

    if not records:
        return json.dumps(
            {
                "query": {"lat": lat, "lng": lng, "radius_km": radius_km, "days_back": days_back},
                "observation_count": 0,
                "observations": [],
                "summary": {},
                "fish_presence_confidence": "none",
                "habitat_note": (
                    "No piscivore bird activity recorded within the query area and time window. "
                    "This may reflect low observer effort rather than fish absence — "
                    "eBird coverage varies significantly by location. "
                    "Run `make ingest` to populate."
                ),
                "attribution": "Data from eBird.org (Cornell Lab of Ornithology)",
            }
        )

    # Group by species
    by_species: dict[str, list] = defaultdict(list)
    for r in records:
        by_species[r.species_code].append(r)

    active_codes = set(by_species.keys())
    most_recent = max(r.observed_on for r in records)

    obs_out = []
    for r in records:
        obs_out.append(
            {
                "species_code": r.species_code,
                "common_name": r.common_name,
                "observed_on": r.observed_on.isoformat(),
                "how_many": r.how_many,
                "location_name": r.location_name,
                "lat": r.lat,
                "lng": r.lng,
                "significance": r.piscivore_significance,
            }
        )

    species_summary = []
    for code, recs in sorted(by_species.items()):
        counts = [r.how_many for r in recs if r.how_many is not None]
        species_summary.append(
            {
                "species_code": code,
                "common_name": recs[0].common_name,
                "sighting_count": len(recs),
                "max_count": max(counts) if counts else None,
                "most_recent": max(r.observed_on for r in recs).isoformat(),
                "significance": recs[0].piscivore_significance,
            }
        )

    # Confidence logic
    if active_codes & _CONFIDENCE_HIGH:
        confidence = "high"
    elif active_codes & _CONFIDENCE_MODERATE:
        confidence = "moderate"
    elif active_codes:
        confidence = "low"
    else:
        confidence = "none"

    habitat_note = _build_habitat_note(active_codes, most_recent, by_species)

    return json.dumps(
        {
            "query": {"lat": lat, "lng": lng, "radius_km": radius_km, "days_back": days_back},
            "observation_count": len(records),
            "observations": obs_out,
            "summary": {
                "species_active": species_summary,
                "total_sightings": len(records),
                "most_recent_observation": most_recent.isoformat(),
                "species_count": len(by_species),
            },
            "fish_presence_confidence": confidence,
            "habitat_note": habitat_note,
            "attribution": "Data from eBird.org (Cornell Lab of Ornithology)",
        }
    )


def _build_habitat_note(
    active_codes: set[str],
    most_recent: date,
    by_species: dict[str, list],
) -> str:
    parts: list[str] = []
    days_ago = (date.today() - most_recent).days

    if "osprey1" in active_codes:
        n = len(by_species["osprey1"])
        parts.append(
            f"Osprey recorded {n} time(s) — strongest fish presence signal. "
            "Osprey only hunt where fish are at the surface and catchable."
        )
    if "commer1" in active_codes:
        n = len(by_species["commer1"])
        parts.append(
            f"Common Merganser recorded {n} time(s) — confirms fish at depth. "
            "Mergansers dive and pursue fish actively."
        )
    if "grbher3" in active_codes:
        n = len(by_species["grbher3"])
        parts.append(
            f"Great Blue Heron recorded {n} time(s) — indicates shallow fish-bearing water. "
            "Herons forage widely; activity near a specific spot is a credible signal."
        )
    if "belkin1" in active_codes:
        n = len(by_species["belkin1"])
        parts.append(
            f"Belted Kingfisher recorded {n} time(s) — confirms small fish in accessible water."
        )
    if "doccor" in active_codes:
        n = len(by_species["doccor"])
        parts.append(
            f"Double-crested Cormorant recorded {n} time(s) — productive fish habitat signal, "
            "though cormorants also target invertebrates."
        )

    recency = (
        "today" if days_ago == 0
        else f"{days_ago} day(s) ago"
    )
    parts.append(
        f"Most recent observation: {recency}. "
        "Bird activity reflects conditions at time of sighting."
    )
    parts.append(
        "Absence of piscivore records does not confirm fish absence — observer coverage varies."
    )

    return " ".join(parts)
