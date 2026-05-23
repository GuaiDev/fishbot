"""Load the curated Ontario species range database from the committed JSON file."""

import json
import logging
from pathlib import Path

from src.models.species_range import SpeciesRange

_DATA_PATH = Path("data/processed/ontario_species_ranges.json")

logger = logging.getLogger(__name__)


def load_species_database() -> list[SpeciesRange]:
    """Read and deserialize the curated species range JSON into SpeciesRange models."""
    if not _DATA_PATH.exists():
        logger.warning("Species range database not found at %s", _DATA_PATH)
        return []
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return [SpeciesRange.model_validate(entry) for entry in raw]
