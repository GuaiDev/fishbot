"""Agent-facing SDM prediction service.

Wraps storage queries into a JSON string suitable for the Claude tool-call loop.
"""

import json
import logging

from src.storage.database import get_db
from src.storage.sdm_predictions import query_predictions

logger = logging.getLogger(__name__)

_COMMON_NAMES = {
    "Semotilus atromaculatus": "Creek Chub",
    "Lepomis gibbosus": "Pumpkinseed",
    "Perca flavescens": "Yellow Perch",
    "Ameiurus nebulosus": "Brown Bullhead",
    "Catostomus commersonii": "White Sucker",
    "Culaea inconstans": "Brook Stickleback",
    "Etheostoma caeruleum": "Rainbow Darter",
    "Ambloplites rupestris": "Rock Bass",
    "Micropterus nigricans": "Smallmouth / Largemouth Bass (pooled)",
}

_SUPPORTED_SPECIES = list(_COMMON_NAMES.values())


def get_species_predictions_for_agent(
    lat: float,
    lng: float,
    radius_km: float = 25.0,
    species: str | None = None,
    min_probability: float = 0.5,
    db=None,
) -> str:
    """Return habitat suitability predictions near (lat, lng) as a JSON string.

    If no predictions are in the DB, returns a setup message.
    """
    if db is None:
        db = get_db()

    if "sdm_predictions" not in db.table_names():
        return json.dumps(
            {
                "error": "SDM predictions not generated yet.",
                "setup": "Run `make train-sdm` to train models and generate predictions.",
            }
        )

    # Resolve species name — accept both scientific and common names
    sci_name = _resolve_species(species) if species else None

    rows = query_predictions(
        db, lat, lng, radius_km, species=sci_name, min_probability=min_probability
    )

    if not rows:
        no_data_msg = (
            f"No predictions found within {radius_km}km at probability >= {min_probability}."
        )
        if species:
            no_data_msg += (
                f" Either {species} has no model yet (run `make train-sdm`) or "
                f"this area has low predicted suitability."
            )
        return json.dumps({"result": no_data_msg, "supported_species": _SUPPORTED_SPECIES})

    # Group results by species
    by_species: dict[str, list[dict]] = {}
    for row in rows:
        by_species.setdefault(row["species"], []).append(row)

    predictions_out = []
    for sci, segs in sorted(by_species.items(), key=lambda kv: -_mean_prob(kv[1])):
        probs = [s["presence_probability"] for s in segs]
        mean_p = sum(probs) / len(probs)
        max_p = max(probs)
        n_above = len(probs)
        common = _COMMON_NAMES.get(sci, sci)

        # Confidence tier based on mean probability of above-threshold segments
        if mean_p > 0.65:
            tier = "high"
        elif mean_p >= 0.4:
            tier = "moderate"
        else:
            tier = "low"

        # Best-effort feature drivers from first row (model_version carries info)
        mv = segs[0].get("model_version", MODEL_VERSION)

        predictions_out.append(
            {
                "species": common,
                "scientific_name": sci,
                "segments_above_threshold": n_above,
                "max_probability": round(max_p, 3),
                "mean_probability": round(mean_p, 3),
                "confidence_tier": tier,
                "model_version": mv,
            }
        )

    # Retrieve per-species metadata (AUC, data basis) from a single representative row
    model_notes: dict[str, str] = {}
    for sci in by_species:
        row = db.execute(
            "SELECT model_version FROM sdm_predictions WHERE species = ? LIMIT 1", (sci,)
        ).fetchone()
        if row:
            model_notes[sci] = row[0]

    return json.dumps(
        {
            "species_predictions": predictions_out,
            "search_params": {
                "lat": lat,
                "lng": lng,
                "radius_km": radius_km,
                "min_probability": min_probability,
            },
            "model_note": (
                "Presence-only model (pseudo-absence). "
                "Probabilities reflect habitat suitability, not confirmed presence."
            ),
            "setup_note": (
                "Spatial CV AUC per species is stored in data/processed/sdm_models/ "
                "after running make train-sdm."
            ),
        },
        indent=2,
    )


# ── helpers ───────────────────────────────────────────────────────────────────

# Import here to avoid circular import at module level
try:
    from src.services.sdm_training import MODEL_VERSION
except ImportError:
    MODEL_VERSION = "2c-v1"

_COMMON_TO_SCIENTIFIC = {v.lower(): k for k, v in _COMMON_NAMES.items()}
# Also allow scientific name lookup
for _k in list(_COMMON_NAMES.keys()):
    _COMMON_TO_SCIENTIFIC[_k.lower()] = _k


def _resolve_species(name: str) -> str | None:
    """Map a common or scientific name to the canonical scientific name."""
    return _COMMON_TO_SCIENTIFIC.get(name.lower())


def _mean_prob(segs: list[dict]) -> float:
    return sum(s["presence_probability"] for s in segs) / len(segs) if segs else 0.0
