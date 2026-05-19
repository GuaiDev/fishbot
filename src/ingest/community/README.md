# src/ingest/community/

Adapters for community-generated content where ToS permits.

Planned modules:
- `reddit.py` — public Reddit API (r/FishingOntario, r/Fishing, r/microfishing, etc.)
- `youtube.py` — YouTube Data API v3 + transcript extraction via youtube-transcript-api
- `forums.py` — polite scraping of public fishing forums (robots.txt respected, 1-2s delay)
- `tournament_results.py` — Bassmaster, FLW, MLF, regional Ontario tournament results
- `guide_reports.py` — guide service and outfitter weekly fishing reports

Ethical constraints (see CLAUDE.md):
- No scraping of Instagram, Facebook, TikTok, FishBrain, or FishAngler
- Synthesizing public information is fine; reconstructing deliberately-hidden info is not
- Respect explicit "don't share this spot" statements in ingested content
