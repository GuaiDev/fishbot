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
it was checked. There is no code path that sets `status_verified_at` without
also setting `status_source`.
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


def load_registry_file(path: Path) -> dict[str, dict]:
    """Read a registry export keyed by scientific name.

    Accepts CSV or JSON with, per row: scientific_name (or species), and any of
    sara_status / ontario_status / cosewic_status.
    """
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.DictReader(f))

    out: dict[str, dict] = {}
    for row in rows:
        key = (row.get("scientific_name") or row.get("species") or "").strip().lower()
        if key:
            out[key] = row
    return out


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

    for row in db["species_ranges"].rows:
        key = (row.get("scientific_name") or row.get("species") or "").strip().lower()
        entry = registry.get(key)
        if entry is None:
            skipped += 1
            continue

        updates: dict = {}
        for field in ("sara_status", "ontario_status", "cosewic_status"):
            value = (entry.get(field) or "").strip()
            if not value:
                continue
            if value not in VALID_STATUSES:
                rejected.append(f"{row['species']}: {field}={value!r}")
                continue
            updates[field] = value

        if not updates:
            skipped += 1
            continue

        updates.update({
            "status_source": source,
            "status_source_url": source_url,
            "status_verified_at": now,
        })
        db["species_ranges"].update(row["species"], updates)
        verified += 1

    db.conn.commit()
    total = db["species_ranges"].count
    return {
        "verified": verified,
        "left_unverified": total - verified,
        "skipped_not_in_registry": skipped,
        "rejected_values": rejected,
        "source": source,
        "source_url": source_url,
        "note": (
            f"{total - verified} species remain unverified and continue to fail "
            "closed: flagged as potentially listed, targeting guidance withheld."
        ),
    }
