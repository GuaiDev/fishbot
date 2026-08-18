"""Escalation for the records lookup — and only the records lookup.

    cached local records (iNat, GBIF, user catches)
           │ empty
           v
    live web search  ──────>  tagged `web`, unverified
           │ empty
           v
    honest empty  ─────────>  with a specific empty_reason

The chain runs in Python, not as a sequence of model tool choices. That
collapses three round trips into one retrieval pass, which is both the
clarity win and the single biggest cost lever.

Nothing else escalates. You would never web-search for pH or a barrier count
— those exist in the corpus or they do not, and a search result claiming
otherwise is worse than an honest gap.
"""

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Sources the project will not consume, per its ethics rules: ToS violations
# and active enforcement. A general web search surfaces these constantly, so
# the filter has to live in code — a prompt asking the model to avoid them is
# exactly the kind of prose guardrail this architecture exists to replace.
BLOCKED_DOMAINS: frozenset[str] = frozenset(
    {
        "instagram.com",
        "facebook.com",
        "fb.com",
        "tiktok.com",
        "fishbrain.com",
        "fishangler.com",
    }
)


def is_blocked(url: str) -> bool:
    """True if the URL belongs to a forbidden source.

    Matches the registered domain and any subdomain, so
    `www.fishbrain.com` and `m.facebook.com` are both caught, while
    `notfishbrain.com` is not.
    """
    if not url:
        return True
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
    except ValueError:
        return True
    if not host:
        return True
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def filter_web_results(results: list[dict]) -> list[dict]:
    """Drop results from blocked sources. Logs what it dropped."""
    kept, dropped = [], 0
    for r in results:
        if is_blocked(str(r.get("url", ""))):
            dropped += 1
            continue
        kept.append(r)
    if dropped:
        logger.info("Dropped %d web result(s) from blocked sources", dropped)
    return kept
