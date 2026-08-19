"""Shared guard for resource discovery against external catalogues.

Adapters that pick files out of a remote catalogue (CKAN, ArcGIS, an HTML
index) filter candidate names with some matcher. When the publisher renames
things, the matcher quietly stops matching and the adapter reports "0 records"
— indistinguishable from a source that genuinely has no data.

That is how PWQMN went silently missing: Ontario renamed its resources from
"Field Data <year>" to "Data <range>", the substring filter matched none of
20 resources, and the ingest logged a cheerful zero.

The distinction that matters is not "did we get nothing" but "did we get
nothing *while candidates were sitting right there*". The second is always a
bug in us, never a fact about the world.
"""

import logging

logger = logging.getLogger(__name__)


def check_resource_discovery(
    source: str,
    matched: int,
    candidates: list[str],
    matcher: str,
) -> None:
    """Log loudly when a filter matched nothing but candidates existed.

    `matched` is how many resources the filter accepted, `candidates` the names
    it was offered, and `matcher` a human description of the rule (quoted in
    the warning so the mismatch is obvious without opening the code).
    """
    if matched > 0 or not candidates:
        return

    preview = ", ".join(repr(c) for c in candidates[:8])
    if len(candidates) > 8:
        preview += f", … (+{len(candidates) - 8} more)"

    logger.error(
        "%s: discovery matched 0 of %d available resources using %s. "
        "The publisher has probably renamed them — this is an adapter bug, "
        "not an empty source. Available names: %s",
        source,
        len(candidates),
        matcher,
        preview,
    )
