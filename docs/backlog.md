# FishBot Backlog

This file tracks features, improvements, and design decisions that have been
deliberately deferred. Updated every session. Nothing should live only in a
chat window.

---

## Trip Logging

- **Productivity signal redesign** — current boolean `was_productive` may not
  capture enough nuance (e.g. catching 1 fish after 6 hours vs 10 fish in 1 hour).
  Revisit when personal model layer is designed.

- **Catch count per stop** — consider adding `fish_caught_count` integer to `stops`
  table to give the model richer signal beyond the boolean. Deferred until personal
  model design.

- **Species confidence tiers for commercial use** — beginner anglers can't always
  ID species. Design a tiered system: user-confirmed / uncertain ("I think it was X")
  / unidentified group. Parser handles "uncertain" tagging but no UI or downstream
  handling exists yet. Needs proper design when commercial product is built.

- **EXIF photo coordinates** — phone photos embed GPS coordinates. Use these to
  auto-resolve trip location without user typing anything. Deferred until mobile
  UI is built.

- **Voice logging** — dictate trips instead of typing. Works today via phone
  keyboard mic into terminal. A proper hold-to-speak button deferred until UI
  is built.

- **`parsed_trips` table cleanup** — old flat schema table left intact as fallback.
  Remove once `sessions`/`stops` schema is confirmed stable across several sessions.

- **Seasonal location awareness in personal model** — user is in London Ontario
  Sept–Apr and Oakville/GTA May–Aug. Personal model should never recommend London
  spots in summer or Oakville spots in winter. Implement when personal model layer
  is built.

- **Double-parse bug in review mode** — in batch_log_historical_trips_v2.py, the
  parse-for-review step and the actual log step call the parser twice, so what you
  review isn't guaranteed to match what gets stored. Fix when review mode is next used.

---

## Personal Model

- **Personal model layer** — not yet built. Will be a separate model layer on top
  of the shared objective SDM, learning individual fishing patterns from trip logs.
  Key inputs: stops table, species caught, conditions, productivity, seasonal location.
  Commercial "pal" concept depends on this.

- **Confidence escalation from trip logs** — when a stop in the `stops` table
  confirms or contradicts a stored behavioral insight (same species, same location
  within 1km), automatically update the insight's confidence level and call
  `refine_insight()` if needed. Currently requires manual recording. This closes
  the feedback loop between trip logs and recommendations — a confirmed catch at
  Willoway Park should bump insight #34 from medium → high confidence automatically.

---

## Agent Behaviour

- **Rolling angler context — reviewed vs draft plans** — the current rolling context
  document captures plans and patterns but doesn't distinguish between "plan we built
  together and refined" vs "first-draft plan not yet reviewed." When a plan has been
  discussed and refined across multiple sessions, the context should note it as
  reviewed so the bot doesn't re-critique it from scratch next session.

- **Mapbox satellite vision in chat** — when user provides coordinates, fetch Mapbox
  satellite tile and run Claude vision assessment (water type, structure, cover, depth
  indicators). Already used in `vision_screening.py` — adapt for conversational use.
  Makes geographic assessment work anywhere in the world, not just OHN coverage areas.
  Currently users must describe what they see at a location.

- **Trust user location knowledge** — when user provides coordinates or describes a
  spot from personal experience, the bot should accept it as ground truth. Internal
  water databases (OHN, OSM) have incomplete coverage — user firsthand knowledge is
  more reliable for specific spots. Partially addressed in system prompt but needs
  ongoing attention.

---

## Data Sources

- **Reddit RAG** — ingest fishing subreddit posts for local knowledge. Same
  architecture as YouTube (search → ingest → chunk → embed → store →
  search_knowledge_base tool already handles it). Waiting on credentials. When
  ready, add `src/ingest/community/reddit_ingest.py` following the same pattern
  as `youtube_ingest.py`.

- **YouTube transcript quality filtering** — some auto-caption transcripts are poor
  quality (music videos, non-English content mislabeled). Add minimum length filter
  and fishing-relevance check before storing. Also consider scaling up from 5 to
  15-20 videos per query once quality is confirmed.

---

## Map & UI

- **Mapbox GL JS map rebuild** — replace current Leaflet prototype with proper
  Mapbox GL JS implementation. Better performance, satellite imagery, mobile-ready.
  Not yet started.

- **Mobile UI** — build a mobile-friendly web interface that talks to the FastAPI
  server. Required before EXIF photo logging, voice logging, and public access
  are meaningful. Not yet started.

---

## Infrastructure

- **Populate Railway database** — the live Railway server has a fresh empty database.
  Options: (1) run `/ingest` endpoint with key Ontario fishing queries to build
  knowledge base on the server, (2) write a script to copy local `data/fishing.db`
  to the Railway volume. Defer until UI exists.

- **API authentication** — `/ingest` endpoint is unprotected. Add `X-API-Key`
  header check before making the server public. Implement when UI is being built.

- **`ensure_schema()` not called on startup** — tables only exist after manually
  calling ensure_schema(). Should be called automatically when the app starts.
  Low priority until there's a proper app entrypoint.

- **Agent efficiency — token usage tracking** — `api_usage` table now exists and
  is being populated. Build a dashboard or reporting tool to understand cost per
  query over time. Foundation for future per-user billing in commercial version.

---

## Known Bugs

- **OHN snap criteria too strict** — location resolver previously skipped trips
  that couldn't snap to an OHN segment. Fixed with sessions/stops schema (text_only
  fallback). Monitor for regressions.

---

*Last updated: Session — recommendation ledger, conflict detection, rolling context*
