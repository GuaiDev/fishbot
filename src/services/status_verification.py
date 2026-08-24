"""Apply conservation statuses from a real registry, with provenance.

Deliberately NOT a live fetcher. The statuses in the local species file were
generated rather than sourced, and the whole point of this work is that
unattributed data must not be trusted — shipping an untested parser that
stamps `verified` onto records would reproduce that failure with extra steps.

Instead this takes a file the operator downloaded from COSEWIC or the SARA
public registry, together with a citation for where it came from, and applies
it. Registry assessments change on the order of years, so a manual download
with a recorded URL is both sufficient and more auditable than an API call
nobody can replay.

A species is only ever marked verified together with its source and the date
it was checked. There is no code path that sets `status_last_checked_at`
without also setting `status_source`.

That column is named for what it actually records. It is stamped on every run,
including a no-op re-application of the same export, because re-checking a
status against the registry is a real event worth dating even when the value
is unchanged. Calling it `status_verified_at` made the date claim something
else — that the value had been confirmed anew — and it moved on runs where
nothing was confirmed at all. When the value last *changed* is a different
question, and this field has never answered it.
"""

import csv
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlite_utils import Database

logger = logging.getLogger(__name__)

# Statuses the registries actually issue. Anything else is rejected rather than
# stored — a typo silently becoming an unrecognised status would clear the SAR
# flag by accident.
VALID_STATUSES = frozenset({
    "Not at Risk", "Special Concern", "Threatened",
    "Endangered", "Extirpated", "No Status",
})


_NAME_FIELDS = ("scientific_name", "species", "common_name")


def _names(row: dict) -> list[str]:
    """Every name a row supplies, normalised for comparison.

    Both sides of this join index under all of them. The previous version used
    `scientific_name or species` on the registry AND on the database, which
    reads like symmetry and is not: the fallback fires only where the column is
    missing, so a registry export carrying common names alone was keyed
    'american eel' while the database row for the same fish — which does have a
    scientific_name — was keyed 'anguilla rostrata'. Twelve rows, sixty-nine
    rows, zero possible matches, reported as a clean run.

    The lesson is not "pick the other column". It is that a key whose namespace
    depends on which columns happen to exist cannot be relied on to mean the
    same thing on both sides of a comparison.
    """
    out = []
    for field in _NAME_FIELDS:
        value = (row.get(field) or "").strip().lower()
        if value and value not in out:
            out.append(value)
    return out


def load_registry_file(path: Path) -> dict[str, dict]:
    """Read a registry export, indexed under every name each row supplies.

    Accepts CSV or JSON with, per row: any of scientific_name / species /
    common_name, and any of sara_status / ontario_status / cosewic_status.
    """
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.DictReader(f))

    out: dict[str, dict] = {}
    for row in rows:
        for key in _names(row):
            if key in out and out[key] is not row:
                # Two registry rows claiming the same name is a problem with the
                # export, and silently keeping the last one is how a wrong status
                # gets stamped 'verified'.
                logger.warning(
                    "Registry contains two entries for %r; keeping the first", key
                )
                continue
            out[key] = row
    return out


def registry_citation(registry: dict[str, dict]) -> tuple[str | None, str | None]:
    """The citation the export carries for itself, if it carries one.

    The exports written for this command already name their own source and
    URL on every row, and re-typing them on the command line is how a run ends
    up stamping the wrong citation onto a status. Reading them off the file
    removes the chance to disagree with it.

    Returns (None, None) when rows disagree — a file that cites two sources
    cannot speak for either, and guessing which one the operator meant is the
    kind of silent choice this whole path exists to avoid.
    """
    sources = {(r.get("source") or "").strip() for r in registry.values()}
    urls = {(r.get("source_url") or "").strip() for r in registry.values()}
    sources.discard("")
    urls.discard("")

    if len(sources) > 1 or len(urls) > 1:
        logger.warning(
            "Registry rows cite %d different sources and %d different URLs; "
            "pass --source and --url explicitly",
            len(sources),
            len(urls),
        )
        return None, None
    return (next(iter(sources), None), next(iter(urls), None))


def registry_species_count(registry: dict[str, dict]) -> int:
    """How many distinct species the registry holds, not how many keys.

    One row indexed under both its names must not read as two species.
    """
    return len({id(row) for row in registry.values()})


def apply_verified_statuses(
    db: Database,
    registry: dict[str, dict],
    source: str,
    source_url: str,
) -> dict:
    """Update species whose status appears in the registry. Returns a summary.

    Species absent from the registry are left untouched and therefore stay
    unverified — which keeps them failing closed.
    """
    if not source or not source_url:
        raise ValueError(
            "A citation is required: a status cannot be marked verified without "
            "recording which registry it came from."
        )

    now = datetime.now(UTC).isoformat()
    verified, skipped, rejected = 0, 0, []
    matched_no_usable_status = 0
    dropped: list[str] = []
    matched_keys: set[str] = set()

    for row in db["species_ranges"].rows:
        entry = None
        for key in _names(row):
            entry = registry.get(key)
            if entry is not None:
                matched_keys.update(_names(entry))
                break
        if entry is None:
            skipped += 1
            continue

        updates: dict = {}
        supplied, cleared = [], []
        for field in ("sara_status", "ontario_status", "cosewic_status"):
            value = (entry.get(field) or "").strip()
            if not value:
                # The registry is silent on this authority. Leaving the old
                # value in place would park a generated status on a row now
                # stamped with a real citation — Redside Dace would render
                # "Listed: Endangered, Threatened (source: COSEWIC)" when
                # COSEWIC never said Threatened; the model did. Generated
                # content wearing a record's authority is the defect this
                # whole verification path exists to remove, so an unsupplied
                # field is cleared rather than inherited.
                if row.get(field):
                    cleared.append(field)
                updates[field] = None
                continue
            if value not in VALID_STATUSES:
                rejected.append(f"{row['species']}: {field}={value!r}")
                continue
            updates[field] = value
            supplied.append(field)

        if not supplied:
            updates = {}

        if not updates:
            # Matched the registry but carried nothing usable — a different
            # fact from "not in the registry", and it must not be counted with
            # it. Merging the two is what made a total join failure look like
            # an export that simply did not cover these species.
            matched_no_usable_status += 1
            continue

        # When the registry decided, as published. Distinct from when we last
        # read the file, and the one an angler actually weighs: a 1998 "Not at
        # Risk" and a 2023 one are not the same reassurance. Cleared when the
        # export is silent, for the same reason the statuses are — a stale
        # assessment date under a fresh citation is a false attribution.
        updates.update({
            "status_source": source,
            "status_source_url": source_url,
            "status_last_checked_at": now,
            "status_assessed_on": (entry.get("assessment_date") or "").strip() or None,
        })
        db["species_ranges"].update(row["species"], updates)
        verified += 1
        if cleared:
            dropped.append(f"{row['species']}: {', '.join(cleared)}")

    db.conn.commit()
    total = db["species_ranges"].count
    registry_total = registry_species_count(registry)
    unmatched_registry = sorted(
        {
            (r.get("species") or r.get("scientific_name") or "?")
            for k, r in registry.items()
            if k not in matched_keys
        }
    )

    summary = {
        "verified": verified,
        "left_unverified": total - verified,
        "skipped_not_in_registry": skipped,
        "matched_no_usable_status": matched_no_usable_status,
        "registry_entries": registry_total,
        "unmatched_registry_entries": unmatched_registry,
        "rejected_values": rejected,
        "cleared_generated_statuses": dropped,
        "source": source,
        "source_url": source_url,
        "note": (
            f"{total - verified} species remain unverified and continue to fail "
            "closed: flagged as potentially listed, targeting guidance withheld."
        ),
    }

    # A registry that matched nothing at all is a broken join, not a narrow
    # export. Zero verified is a legitimate outcome of this design — the whole
    # point is failing closed — so the honest state and the broken state look
    # identical unless something says which one this was.
    if registry_total and verified == 0:
        logger.warning(
            "Registry held %d species and none matched any of the %d rows in "
            "species_ranges — check that the name columns line up",
            registry_total,
            total,
        )
    return summary
