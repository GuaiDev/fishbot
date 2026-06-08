"""YouTube transcript ingestion pipeline for FishBot's RAG knowledge base.

Searches YouTube for fishing-related videos, pulls transcripts, chunks them,
and stores everything in SQLite with FTS5 for semantic keyword search.

No embedding API required — search uses SQLite FTS5 (already a project dependency).
The Anthropic API has no embeddings endpoint; Voyage AI (a separate company)
would be needed for vector embeddings, which is unnecessary complexity here.

Requires: YOUTUBE_API_KEY in .env
"""

import os
import time
from datetime import UTC, datetime

from googleapiclient.discovery import build
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

LOCATION_KEYWORDS = [
    "river",
    "lake",
    "creek",
    "ontario",
    "quebec",
    "alberta",
    "bc",
    "british columbia",
    "manitoba",
    "saskatchewan",
    "nova scotia",
    "new brunswick",
    "grand river",
    "thames",
    "credit",
    "niagara",
    "dunnville",
    "london",
    "toronto",
    "ottawa",
    "winnipeg",
    "vancouver",
]


def _is_location_query(query: str) -> bool:
    return any(kw in query.lower() for kw in LOCATION_KEYWORDS)


def search_youtube(query: str, max_results: int = 15) -> list[dict]:
    """Search YouTube for fishing videos matching the query.

    Appends 'Canada fishing' for location queries, 'fishing tips' for general ones.
    Returns list of dicts with video_id, title, channel_name, published_at, url.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY environment variable not set")

    if _is_location_query(query):
        search_query = f"{query} Canada fishing"
    else:
        search_query = f"{query} fishing tips"

    youtube = build("youtube", "v3", developerKey=api_key)
    response = (
        youtube.search()
        .list(
            q=search_query,
            part="snippet",
            type="video",
            maxResults=max_results,
            relevanceLanguage="en",
            videoCategoryId="17",  # Sports category — improves fishing relevance
        )
        .execute()
    )

    results = []
    for item in response.get("items", []):
        results.append(
            {
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "channel_name": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
                "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
            }
        )
    return results


def fetch_transcript(video_id: str) -> str | None:
    """Fetch the transcript for a YouTube video.

    Tries manual English transcript first, falls back to auto-generated.
    Returns the full transcript as a single string, or None if unavailable.
    """
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        try:
            transcript = transcript_list.find_manually_created_transcript(["en"])
        except Exception:
            transcript = transcript_list.find_generated_transcript(["en"])

        fetched = transcript.fetch()
        full_text = " ".join(snippet.text for snippet in fetched)
        return full_text.strip() or None

    except (TranscriptsDisabled, NoTranscriptFound):
        return None
    except Exception as e:
        print(f"  [TRANSCRIPT ERROR] {video_id}: {e}")
        return None


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """Split transcript into overlapping chunks of ~400 words.

    Overlap ensures context isn't lost at chunk boundaries.
    """
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += chunk_size - overlap
    return chunks


def ingest_query(query: str, db, max_videos: int = 15) -> dict:
    """Full pipeline: search → transcript → chunk → store.

    Skips videos already in the database (deduplication by video_id).
    Returns {"ingested": int, "skipped_no_transcript": int, "skipped_duplicate": int}.
    """
    print(f"\nSearching YouTube for: '{query}'")
    videos = search_youtube(query, max_results=max_videos)
    print(f"Found {len(videos)} videos")

    ingested = 0
    skipped_no_transcript = 0
    skipped_duplicate = 0

    for video in videos:
        video_id = video["video_id"]

        existing = list(
            db["knowledge_sources"].rows_where(
                "source_type = ? AND source_id = ?", ["youtube", video_id]
            )
        )
        if existing:
            print(f"  [SKIP duplicate] {video['title'][:60]}")
            skipped_duplicate += 1
            continue

        print(f"  Fetching transcript: {video['title'][:60]}")
        transcript = fetch_transcript(video_id)
        if not transcript:
            print("  [SKIP no transcript]")
            skipped_no_transcript += 1
            continue

        source_row_id = db["knowledge_sources"].insert(
            {
                "source_type": "youtube",
                "source_id": video_id,
                "title": video["title"],
                "url": video["url"],
                "channel_name": video["channel_name"],
                "published_at": video["published_at"],
                "search_query": query,
                "transcript_raw": transcript,
                "ingested_at": datetime.now(UTC).isoformat(),
            },
            ignore=True,
        ).last_pk

        chunks = chunk_text(transcript)
        print(f"  Storing {len(chunks)} chunks...")

        now = datetime.now(UTC).isoformat()
        for i, chunk in enumerate(chunks):
            db["knowledge_chunks"].insert(
                {
                    "source_id": source_row_id,
                    "chunk_index": i,
                    "chunk_text": chunk,
                    "created_at": now,
                }
            )

        ingested += 1
        print(f"  [OK] {len(chunks)} chunks stored")

        time.sleep(0.5)

    return {
        "ingested": ingested,
        "skipped_no_transcript": skipped_no_transcript,
        "skipped_duplicate": skipped_duplicate,
    }


def search_knowledge(query: str, db, top_k: int = 5) -> list[dict]:
    """Full-text search over all ingested knowledge chunks.

    Uses SQLite FTS5 (already a project dependency via sqlite-utils).
    Returns the top_k most relevant chunks with their source metadata.

    Note: FTS5 rank is based on BM25-style term frequency — effective for
    fishing queries where specific species/location names are highly distinctive.
    """
    # Escape FTS5 special characters in the query
    fts_query = query.replace('"', '""')

    rows = list(
        db.execute(
            """
            SELECT
                kc.chunk_text,
                ks.title,
                ks.url,
                ks.channel_name,
                ks.source_type,
                fts.rank
            FROM knowledge_chunks_fts fts
            JOIN knowledge_chunks kc ON kc.id = fts.rowid
            JOIN knowledge_sources ks ON kc.source_id = ks.id
            WHERE knowledge_chunks_fts MATCH ?
            ORDER BY fts.rank
            LIMIT ?
            """,
            [fts_query, top_k],
        ).fetchall()
    )

    return [
        {
            "chunk_text": row[0],
            "title": row[1],
            "url": row[2],
            "channel_name": row[3],
            "source_type": row[4],
            "rank": row[5],
        }
        for row in rows
    ]
