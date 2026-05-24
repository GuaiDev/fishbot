"""Reddit post CRUD and FTS-backed search via sqlite-utils."""

import json
from datetime import datetime
from typing import Any

from sqlite_utils.db import Database

from src.models.reddit_post import RedditPost


def upsert_post(db: Database, post: RedditPost) -> None:
    db["reddit_posts"].upsert(_to_row(post), pk="post_id")  # type: ignore[attr-defined]


def upsert_posts(db: Database, posts: list[RedditPost]) -> int:
    if not posts:
        return 0
    db["reddit_posts"].upsert_all([_to_row(p) for p in posts], pk="post_id")  # type: ignore[attr-defined]
    return len(posts)


def search_posts(
    db: Database,
    query: str,
    limit: int = 15,
    species_filter: str | None = None,
    jurisdiction: str | None = None,
) -> list[RedditPost]:
    fetch_limit = limit * 3  # fetch extra to allow post-filter trimming

    try:
        rows = list(db["reddit_posts"].search(query, limit=fetch_limit))  # type: ignore[attr-defined]
    except Exception:
        rows = _fallback_search(db, query, fetch_limit)

    result: list[RedditPost] = []
    for row in rows:
        species_json = (row.get("extracted_species") or "").lower()
        if species_filter and species_filter.lower() not in species_json:
            continue
        if jurisdiction and row.get("jurisdiction") != jurisdiction:
            continue
        result.append(_row_to_post(row))
        if len(result) >= limit:
            break

    return result


def get_post(db: Database, post_id: str) -> RedditPost | None:
    rows = list(db["reddit_posts"].rows_where("post_id = ?", [post_id]))  # type: ignore[attr-defined]
    return _row_to_post(rows[0]) if rows else None


def _fallback_search(db: Database, query: str, limit: int) -> list[dict]:
    q = f"%{query.lower()}%"
    return list(
        db["reddit_posts"].rows_where(  # type: ignore[attr-defined]
            "(LOWER(title) LIKE ? OR LOWER(body) LIKE ?)",
            [q, q],
            limit=limit,
        )
    )


def _to_row(post: RedditPost) -> dict[str, Any]:
    return {
        "post_id": post.post_id,
        "subreddit": post.subreddit,
        "post_type": post.post_type,
        "title": post.title,
        "body": post.body,
        "url": post.url,
        "author": post.author,
        "score": post.score,
        "num_comments": post.num_comments,
        "parent_post_id": post.parent_post_id,
        "created_utc": post.created_utc.isoformat(),
        "extracted_species": json.dumps(post.extracted_species),
        "extracted_locations": json.dumps(post.extracted_locations),
        "jurisdiction": post.jurisdiction,
        "ingested_at": post.ingested_at.isoformat(),
    }


def _row_to_post(row: dict[str, Any]) -> RedditPost:
    d = dict(row)
    d["created_utc"] = datetime.fromisoformat(d["created_utc"])
    d["ingested_at"] = datetime.fromisoformat(d["ingested_at"])
    d["extracted_species"] = json.loads(d["extracted_species"] or "[]")
    d["extracted_locations"] = json.loads(d["extracted_locations"] or "[]")
    return RedditPost.model_validate(d)
