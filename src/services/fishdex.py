"""Aggregation service behind the "My FishDex" collection screen (GET /fishdex).

Shapes real catches + the regional species pool into the state the design
handoff (design_handoff_fishdex_collection/README.md, "State Management")
specifies: caughtSpecies[] and regionSpeciesPool[], both carrying a `family`
so the frontend can compute the flat/grouped adaptive layout and per-family
completion counts. See species_family.py for the family classification.
"""

from typing import Any

from sqlite_utils.db import Database

from src.services.species_family import canonical_scientific_name, get_family
from src.services.species_mapping import COMMON_TO_SCIENTIFIC
from src.storage.catches import get_all_catches_for_user
from src.storage.species_ranges import query_deduped_species_ranges_for_jurisdiction


def get_fishdex_data(db: Database, user_id: int, jurisdiction: str = "CA-ON") -> dict[str, Any]:
    # confirmed_only: a catch's species is a text-parser/photo-vision
    # suggestion until the user confirms or corrects it (see /catches/pending
    # and /catches/{id}/confirm-species) — the collection screen must never
    # present an unconfirmed guess as a caught species.
    catches = get_all_catches_for_user(db, user_id, confirmed_only=True)

    # Canonical display names from the regional pool (e.g. "Smallmouth Bass"),
    # keyed by scientific name, so a caught species that's also in the pool
    # gets the pool's exact capitalization rather than a naive title-case guess.
    # Deduped/canonicalized so a taxonomic-split alias (e.g. "Northern
    # Largemouth Bass") can't double-count the region pool or resolve a real
    # catch to a confusing duplicate label — see query_deduped_species_ranges_for_jurisdiction.
    pool_rows = query_deduped_species_ranges_for_jurisdiction(db, jurisdiction)
    canonical_names = {
        canonical_scientific_name(sr.scientific_name): sr.species
        for sr in pool_rows
        if sr.scientific_name
    }

    by_species: dict[str, list[dict]] = {}
    for c in catches:
        key = (c.get("species") or "").strip().lower()
        if not key:
            continue
        by_species.setdefault(key, []).append(c)

    caught_species = []
    for common_name_key, rows in by_species.items():
        scientific_name = COMMON_TO_SCIENTIFIC.get(common_name_key)
        if scientific_name:
            scientific_name = canonical_scientific_name(scientific_name)
            family, family_common_name = get_family(scientific_name)
        else:
            family, family_common_name = ("Unclassified", "Other")

        display_name = canonical_names.get(scientific_name) or common_name_key.title()

        photo_rows = [r for r in rows if r.get("photo_url")]
        representative_photo_url = photo_rows[-1]["photo_url"] if photo_rows else None

        # biggest_size is a free-text column that no current input path
        # populates (no NL size extraction, no manual entry field yet) —
        # report honestly rather than fabricating a figure. Best-effort
        # parse in case it does get populated by a future entry path.
        max_length_inches = None
        is_personal_best = False
        for r in rows:
            raw = r.get("biggest_size")
            if not raw:
                continue
            try:
                val = float(str(raw).strip().split()[0])
            except (ValueError, IndexError):
                continue
            if max_length_inches is None or val > max_length_inches:
                max_length_inches = val
                is_personal_best = True

        caught_species.append({
            "id": scientific_name or common_name_key,
            "commonName": display_name,
            "scientificName": scientific_name,
            "family": family,
            "familyCommonName": family_common_name,
            "count": len(rows),
            "maxLengthInches": max_length_inches,
            "isPersonalBest": is_personal_best,
            "personalBestLength": max_length_inches if is_personal_best else None,
            # No acknowledgment-state table exists yet to track "seen" new
            # finds per the handoff's "until acknowledged" language — a
            # species caught exactly once is used as an honest proxy for
            # "newly added to the dex" instead of inventing dismissal state.
            "isNewFind": len(rows) == 1,
            "representativePhotoUrl": representative_photo_url,
        })

    region_species_pool = []
    for sr in pool_rows:
        sci = canonical_scientific_name(sr.scientific_name) if sr.scientific_name else None
        if sci:
            family, family_common_name = get_family(sci)
        else:
            family, family_common_name = ("Unclassified", "Other")
        region_species_pool.append({
            "id": sci or sr.species.lower(),
            "commonName": sr.species,
            "scientificName": sci,
            "family": family,
            "familyCommonName": family_common_name,
        })

    return {
        "caughtSpecies": caught_species,
        "regionSpeciesPool": region_species_pool,
    }
