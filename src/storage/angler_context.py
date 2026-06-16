"""
Persistent rolling context document for the angler.
A single document that accumulates knowledge across all chat sessions.
Updated after each meaningful session ends.
"""
from datetime import datetime

from sqlite_utils import Database

CONTEXT_TEMPLATE = """## Active plans
(none yet)

## Spots on the radar
(none yet)

## Learned patterns
(none yet)

## Species intel
(none yet)
"""

_MERGE_PROMPT = """\
You are maintaining a persistent fishing knowledge document for an angler.
Update the document below by merging in the new session summary.

RULES:
1. Keep all four sections: "Active plans", "Spots on the radar", "Learned patterns", "Species intel"
2. Active plans: add new trips being planned. When a trip has been LOGGED
   (appears in the user's trip history) or the date has clearly passed,
   move it from Active plans to a one-line "Completed trips" note, then
   remove it after 2 weeks. A plan that already happened should never stay
   in Active plans. If unsure whether a plan was completed, check if a
   matching session exists in Recent trips context.
3. Spots on the radar: add any new locations mentioned with coordinates if available.
   Include brief notes on what makes each spot notable. Keep indefinitely.
4. Learned patterns: add any confirmed fishing insights (what worked, what didn't,
   timing, conditions). These are permanent — never remove them.
5. Species intel: add species-specific tactics, bait, timing, or behaviour confirmed
   in conversation. Permanent.
6. If a section has nothing yet, write "(none yet)"
7. Be concise — each entry should be 1-2 lines max
8. Do not add timestamps or dates unless they are part of an active plan
9. Output ONLY the updated document — no preamble, no explanation

EXISTING DOCUMENT:
{existing}

NEW SESSION SUMMARY:
{summary}

OUTPUT THE UPDATED DOCUMENT:"""


def load_context(db: Database) -> str | None:
    """Load the current angler context document. Returns None if none exists yet."""
    try:
        row = db["angler_context"].get(1)
        content = row["content"] if row else None
        return content if content and content.strip() else None
    except Exception:
        return None


def save_context(db: Database, content: str) -> None:
    """Save the updated angler context document, creating the row if needed."""
    db["angler_context"].upsert(
        {
            "id": 1,
            "content": content.strip(),
            "last_updated": datetime.now().isoformat(),
        },
        pk="id",
    )
    try:
        row = db["angler_context"].get(1)
        db["angler_context"].update(1, {
            "session_count": (row.get("session_count") or 0) + 1
        })
    except Exception:
        pass


def update_context(db: Database, session_summary: str, client) -> str:
    """Merge a new session summary into the existing angler context document.

    Returns the updated document text.
    """
    existing = load_context(db) or CONTEXT_TEMPLATE

    prompt = _MERGE_PROMPT.format(existing=existing, summary=session_summary)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )

    updated = response.content[0].text.strip()
    save_context(db, updated)
    return updated


def format_context_for_prompt(context: str) -> str:
    """Format the angler context document for injection into the system prompt."""
    return (
        "## What I know about your fishing\n\n"
        + context
        + "\n\n---"
    )
