"""Species context — the local species file, routed through ContextField.

This file previously bypassed the provenance system entirely: `fishing_notes`
and three conservation statuses went straight from a JSON blob to a tool result
the model treated as retrieved fact. The text was generated during development,
not gathered from a source, and carried no marker saying so.

Everything here is therefore tagged INFERENCE until a real registry is cited.
That is not a hedge — INFERENCE is defined as "reasoning only, no source", and
model-generated text is exactly that. A verified status upgrades to RECORD with
its citation attached, and only then can the conservation flag clear.
"""

import logging

from sqlite_utils import Database

from src.models.context import (
    ContextField,
    EmptyReason,
    SpeciesContext,
)

logger = logging.getLogger(__name__)

_UNVERIFIED = (
    "generated during development, not checked against COSEWIC or the SARA "
    "registry — treat as a hypothesis, not a record"
)

_LISTED = frozenset({"Special Concern", "Threatened", "Endangered", "Extirpated"})


def describe_species(db: Database, name: str) -> SpeciesContext:
    """Everything the corpus holds about a species, with provenance on each claim.

    Fails closed: an unverified conservation status raises the flag rather than
    clearing it, because the cost of a false "safe" is someone targeting a
    protected fish.
    """
    try:
        from src.storage.species_ranges import query_species_range

        sr = query_species_range(db, name)
    except Exception:  # noqa: BLE001 - never break the caller over this slice
        logger.warning("species range lookup failed", exc_info=True)
        sr = None

    if sr is None:
        return SpeciesContext(
            species=name,
            found=False,
            conservation_status=ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA),
            habitat_note=ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA),
            angling_note=ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA),
            native_to_ontario=ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA),
            sar_reason=(
                "Species not in the local file, so nothing is known about its "
                "conservation status. Treated as potentially listed."
            ),
        )

    verified = sr.status_is_verified
    status = sr.sara_status or sr.ontario_status or sr.cosewic_status

    # An affirmative listing signal from any authority, verified or not. An
    # unverified "Endangered" is still a reason to refuse targeting guidance;
    # an unverified "Not at Risk" is not a reason to grant it, but it is also
    # not evidence of a listing. Callers that need a hard refusal gate on this
    # rather than on `sar_alert`, which is true for everything until the
    # registry import runs.
    known_listed = bool(
        {sr.sara_status, sr.ontario_status, sr.cosewic_status} & _LISTED
    )

    if verified:
        listed = {sr.sara_status, sr.ontario_status, sr.cosewic_status} & _LISTED
        alert = bool(listed)
        reason = (
            f"Listed: {', '.join(sorted(listed))} (source: {sr.status_source})."
            if listed
            else f"Verified not at risk (source: {sr.status_source})."
        )
        status_field = ContextField.recorded(
            status,
            source=sr.status_source or "registry",
            date=sr.status_verified_at.date().isoformat() if sr.status_verified_at else None,
        )
    else:
        alert = True
        reason = (
            "Conservation status has not been verified against COSEWIC or the SARA "
            "registry. Treated as potentially listed; targeting guidance withheld."
        )
        status_field = ContextField.inferred(status, meaning=_UNVERIFIED)

    return SpeciesContext(
        species=sr.species,
        scientific_name=sr.scientific_name,
        conservation_status=status_field,
        habitat_note=(
            ContextField.inferred(sr.habitat_notes, meaning=_UNVERIFIED)
            if sr.habitat_notes
            else ContextField.empty(EmptyReason.FIELD_NOT_POPULATED_BY_SOURCE)
        ),
        angling_note=(
            # Suppressed entirely while the species may be listed — the whole
            # point of failing closed is to not hand out targeting advice.
            ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
            if alert
            else ContextField.inferred(sr.fishing_notes, meaning=_UNVERIFIED)
            if sr.fishing_notes
            else ContextField.empty(EmptyReason.FIELD_NOT_POPULATED_BY_SOURCE)
        ),
        native_to_ontario=ContextField.inferred(
            sr.native_to_ontario, meaning=_UNVERIFIED
        ),
        sar_alert=alert,
        sar_reason=reason,
        targeting_guidance_suppressed=alert,
        status_known_listed=known_listed,
    )
