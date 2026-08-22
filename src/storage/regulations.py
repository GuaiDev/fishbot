"""Storage layer for MNRF regulation chunks."""

from sqlite_utils.db import Database

from src.models.regulation import RegulationChunk


def upsert_regulation_chunks(db: Database, chunks: list[RegulationChunk]) -> None:
    rows = [
        {
            "zone": c.zone,
            "section": c.section or "",
            "jurisdiction": c.jurisdiction,
            "regulation_year": c.regulation_year,
            "raw_text": c.raw_text,
            "char_count": c.char_count,
            "source_url": c.source_url,
            "ingested_at": c.ingested_at,
        }
        for c in chunks
    ]
    db["regulation_chunks"].upsert_all(
        rows, pk=["zone", "section", "jurisdiction", "regulation_year"], alter=True
    )


def get_regulation_chunk(
    db: Database,
    zone: int,
    jurisdiction: str = "CA-ON",
) -> RegulationChunk | None:
    """Return the most recent regulation chunk for a zone, or None."""
    rows = list(
        db["regulation_chunks"].rows_where(
            "zone = ? AND jurisdiction = ?",
            [zone, jurisdiction],
            order_by="regulation_year DESC",
            limit=1,
        )
    )
    if not rows:
        return None
    r = rows[0]
    return RegulationChunk(
        zone=r["zone"],
        jurisdiction=r["jurisdiction"],
        regulation_year=r["regulation_year"],
        raw_text=r["raw_text"],
        char_count=r["char_count"],
        source_url=r["source_url"],
        ingested_at=r["ingested_at"],
    )


def count_regulation_chunks(db: Database, jurisdiction: str = "CA-ON") -> int:
    rows = list(db["regulation_chunks"].rows_where("jurisdiction = ?", [jurisdiction]))
    return len(rows)


def get_province_wide_chunks(db: Database, sections: list[str] | None = None) -> list[dict]:
    """Rules that apply everywhere in Ontario, independent of FMZ.

    These used to be swallowed by whichever zone chunk preceded them in the
    PDF, so the bait rules were only reachable by querying FMZ 12 by accident.
    """
    from src.models.regulation import PROVINCE_WIDE

    if "regulation_chunks" not in db.table_names():
        return []
    rows = list(db["regulation_chunks"].rows_where("zone = ?", [PROVINCE_WIDE]))
    if sections:
        wanted = {s.lower() for s in sections}
        rows = [r for r in rows if str(r.get("section", "")).lower() in wanted]
    return rows
