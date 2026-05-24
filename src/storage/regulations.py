"""Storage layer for MNRF regulation chunks."""

from sqlite_utils.db import Database

from src.models.regulation import RegulationChunk


def upsert_regulation_chunks(db: Database, chunks: list[RegulationChunk]) -> None:
    rows = [
        {
            "zone": c.zone,
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
        rows, pk=["zone", "jurisdiction", "regulation_year"]
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
    rows = list(
        db["regulation_chunks"].rows_where(
            "jurisdiction = ?", [jurisdiction]
        )
    )
    return len(rows)
