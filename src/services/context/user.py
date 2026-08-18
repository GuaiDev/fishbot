"""Derived user layer.

Precomputed from logged activity. Never raw rows, and never a configured
profile: what someone cares about and how experienced they are is derived
from what they log, not from what they told a form once.

The core epistemic rule lives here in code rather than in prompt prose:

  * General ecological knowledge applied to observed conditions is legitimate
    immediately, at n=1. That is not this module's business — it needs no
    comparison set, so nothing here gates it.
  * Claims about the user's *own* patterns need a comparison set. A pattern
    is only `is_claimable` with both arms present. Same facts, different
    grammar: principles now, personal tendencies when earned.
"""

import json
import logging
from collections import Counter
from datetime import UTC, datetime

from sqlite_utils import Database

from src.models.context import DerivedPattern, UserLayer

logger = logging.getLogger(__name__)

# A species has to show up this often before we treat it as something the
# angler targets rather than something they happened to catch.
_TARGET_MIN_CATCHES = 3

# Microfishing and specialist taxa. Logging these is a strong signal of
# demonstrated expertise: nobody catches a madtom by accident on a nightcrawler.
_SPECIALIST_MARKERS = (
    "darter",
    "dace",
    "madtom",
    "shiner",
    "chub",
    "sculpin",
    "lamprey",
    "stickleback",
    "redhorse",
    "sucker",
    "logperch",
)


def build_user_layer(db: Database, user_id: int = 1) -> UserLayer:
    """Recompute the derived layer for one user.

    Called when a session is logged, not per question — the coaching path
    this replaces loaded every stop ever logged and filtered in Python on
    every single request.
    """
    now = datetime.now(UTC).isoformat()

    if "stops" not in db.table_names():
        return UserLayer(user_id=user_id, computed_at=now, known_gaps=["no trips logged yet"])

    rows = list(
        db.execute(
            "SELECT st.species_caught, st.was_productive, st.technique, st.gear, "
            "       st.water_clarity, st.water_level, st.location_name, s.date "
            "FROM stops st JOIN sessions s ON st.session_id = s.id "
            "WHERE st.user_id = ?",
            [user_id],
        ).fetchall()
    )
    if not rows:
        return UserLayer(user_id=user_id, computed_at=now, known_gaps=["no trips logged yet"])

    session_count = db.execute(
        "SELECT COUNT(*) FROM sessions WHERE user_id = ?", [user_id]
    ).fetchone()[0]

    species_counter: Counter[str] = Counter()
    blanks = 0
    clarity_outcomes: list[tuple[str, bool]] = []

    for species_json, productive, _technique, _gear, clarity, _level, _loc, _date in rows:
        caught = _species_list(species_json)
        species_counter.update(s.strip().lower() for s in caught if s.strip())
        if not productive:
            blanks += 1
        if clarity:
            clarity_outcomes.append((str(clarity).strip().lower(), bool(productive)))

    return UserLayer(
        user_id=user_id,
        total_sessions=int(session_count),
        total_stops=len(rows),
        blank_rate=round(blanks / len(rows), 3) if rows else None,
        species_logged=sorted(species_counter),
        target_species=_infer_targets(species_counter),
        expertise=_infer_expertise(species_counter, len(rows)),
        patterns=_derive_patterns(clarity_outcomes),
        known_gaps=_known_gaps(rows),
        computed_at=now,
    )


def _species_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(s) for s in parsed] if isinstance(parsed, list) else []


def _infer_targets(counter: Counter[str]) -> list[str]:
    """What someone targets, read off what they repeatedly log.

    No hardcoded species list and no configured profile — if the system needs
    to know someone targets redhorse, it learns it from their logs.
    """
    return sorted(sp for sp, n in counter.items() if n >= _TARGET_MIN_CATCHES)


def _infer_expertise(counter: Counter[str], stop_count: int) -> str:
    """Demonstrated, not declared.

    Register calibrates to this: telling an angler who logs madtoms on a
    tanago hook something obvious, confidently, destroys credibility.
    """
    if stop_count == 0:
        return "unknown"

    distinct = len(counter)
    specialist_hits = sum(
        n for sp, n in counter.items() if any(m in sp for m in _SPECIALIST_MARKERS)
    )

    if specialist_hits >= 3 or distinct >= 12:
        return "advanced"
    if stop_count >= 10 or distinct >= 5:
        return "intermediate"
    if stop_count >= 3:
        return "novice"
    return "unknown"


def _derive_patterns(clarity_outcomes: list[tuple[str, bool]]) -> list[DerivedPattern]:
    """Personal-tendency claims, each carrying its own comparison set.

    A pattern is emitted even when it is not yet claimable — the sample sizes
    travel with it, so the caller can say "one session is a hypothesis, not a
    rule" instead of silently over- or under-claiming.
    """
    if not clarity_outcomes:
        return []

    by_clarity: dict[str, list[bool]] = {}
    for clarity, productive in clarity_outcomes:
        by_clarity.setdefault(clarity, []).append(productive)

    # A comparison needs at least two conditions to compare.
    if len(by_clarity) < 2:
        only = next(iter(by_clarity))
        return [
            DerivedPattern(
                statement=f"only ever logged {only} water — no comparison available",
                sample_size=len(by_clarity[only]),
                comparison_size=0,
                confidence="low",
            )
        ]

    ranked = sorted(
        by_clarity.items(),
        key=lambda kv: (sum(kv[1]) / len(kv[1]), len(kv[1])),
        reverse=True,
    )
    best_clarity, best_outcomes = ranked[0]
    rest = sum(len(v) for _, v in ranked[1:])

    best_rate = sum(best_outcomes) / len(best_outcomes)
    other_rate = sum(sum(v) for _, v in ranked[1:]) / rest if rest else 0.0

    if best_rate <= other_rate:
        return []

    pattern = DerivedPattern(
        statement=f"more productive in {best_clarity} water",
        sample_size=len(best_outcomes),
        comparison_size=rest,
        confidence="low",
    )
    if pattern.is_claimable:
        pattern.confidence = "medium" if pattern.sample_size < 6 else "high"
    return [pattern]


def _known_gaps(rows: list) -> list[str]:
    """Which fields are missing too often to support a given kind of claim.

    This is what lets a surface say "I can't tell you that yet, and here is
    what would fix it" rather than quietly reasoning from absent data.
    """
    total = len(rows)
    if total == 0:
        return []

    # Column order matches the SELECT in build_user_layer.
    checks = {
        "technique": (2, "can't compare techniques"),
        "gear": (3, "can't compare rigs"),
        "water clarity": (4, "can't tell you how clarity affects your results"),
        "water level": (5, "can't tell you how flow affects your results"),
    }

    gaps = []
    for label, (idx, consequence) in checks.items():
        missing = sum(1 for r in rows if not r[idx])
        if missing / total > 0.5:
            gaps.append(f"{label} unrecorded on {missing}/{total} stops — {consequence}")
    return gaps
