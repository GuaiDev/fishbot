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

- **User vs. friend catch distinction** — the trip parser lumps all anglers'
  techniques and catches into shared stop fields (technique, gear, notes) without
  tracking what each technique actually produced. This causes ambiguous memory
  responses — "friends were using bottom rigs" gets interpreted as "friends caught
  fish on bottom rigs" when they may have caught nothing. Fix: add
  `user_species_caught` separate from party-wide `species_caught`, or flag friend
  catches explicitly in the notes field during parsing. The parser should ask "what
  did YOU personally catch" vs "what did your group catch" as distinct fields.

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

- **Blank trip contradiction matching** — when a user logs an unproductive stop
  ("blanked on channel catfish"), the parser correctly sets `species_caught=[]`
  and `was_productive=False`. But `enrich_session` matches insights by species
  caught — so a blank stop never triggers a contradiction against existing insights,
  even if the spot has a high-confidence "good here" insight.
  Fix: in `match_insights_to_stop()`, also match by location proximity alone for
  unproductive stops, even when `species_caught` is empty. This way blanking at
  Willoway Park still challenges insight #34.

- **Lake-run timing tracker — Grand River / Dunnville** — no data exists on when
  lake-run channel catfish push up the Grand River from Lake Erie. Build a
  lightweight tracker: log date + fish size + water temp for every Dunnville
  session. After several sessions across different months, a timing pattern will
  emerge from real data rather than general Great Lakes knowledge. Currently flagged
  as an open research question in angler context.

- **Kool-aid vs natural cutbait comparison** — one friend caught a smallmouth on
  kool-aid soaked cutbait at Willoway. Not enough data to draw conclusions. Design
  a controlled side-by-side: same location, same rig, one rod natural cutbait, one
  rod kool-aid soaked, track strikes per rod. Run deliberately at Byng or Willoway
  next session. Currently stored as low-confidence note in behavioral insights.

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

- **Synthesis cache — wire into tools** — the `segment_synthesis` table and
  `synthesis_cache.py` service are built and ready. The next step is wiring the
  cache check/store into the heaviest synthesis tools — likely
  `get_species_habitat_predictions` or wherever watershed/geology cross-referencing
  happens. On cache miss: run full synthesis and store. On cache hit: return stored
  result. This makes the expensive Willoway-style analysis free after the first query.

- **Router — synthesis cache integration for Willoway-style questions** — when the
  router classifies a message as "synthesis" and the query is about a
  named/coordinate location, check `segment_synthesis` cache first before invoking
  the full pipeline. If hit, answer from cache with Haiku (very cheap). If miss,
  run full pipeline and store result. This is the key step to making synthesis mode
  cheap at runtime.

- **Free vs premium tier boundary** — the router mode field (`reflex` / `synthesis`
  / `memory`) flowing through `api_usage` is the foundation of the free/premium
  split. Design still pending:
  - Free tier: reflex only. Generic fishing knowledge, Haiku, no tools.
  - Premium tier: synthesis + memory. Full pipeline, personal data access.
  - Taster: first synthesis result shown free, deeper analysis gated.
  - Leading questions: reflex answers offer synthesis upgrade ("want me to find
    similar spots?") as the free→premium conversion mechanism.
  Build when ready to think about launching.

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

- **Fishing derby — hosted version** — the derby widget currently runs as a local
  browser artifact. Build a proper hosted version with:
  - Shared live leaderboard (all players see each other's catches in real time)
  - Each player opens the Railway URL on their own phone
  - Photo submission stored server-side
  - Session management (create derby → share code → friends join)
  Backend: new `/derby` endpoints on the Railway FastAPI server.
  Frontend: simple mobile web page served from Railway.

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

- **Test isolation — production DB pollution** — verification scripts that call
  `log_session()` directly write to `data/fishing.db` (production). Need a `--db`
  flag or `DATA_DIR` environment variable override for all verification and manual
  test scripts so they never touch the production database. Add
  `DATA_DIR=data/test.db uv run python scripts/...` pattern to CLAUDE.md as the
  standard approach for manual testing.

- **Derby scoring — data-driven rarity** — the fishing derby widget uses hardcoded
  point values. The real version should query iNaturalist + GBIF observation counts
  for species near the derby location and derive relative rarity scores from actual
  data. Blocked on local database being populated for target areas (Grand River /
  Dunnville not yet ingested). Backend endpoint: `POST /derby/scores` with species
  list + lat/lng → returns point table. Build after ingest is run for target areas.

- **Ingest target fishing areas** — the iNaturalist/GBIF database is sparse for
  the areas actually being fished (Grand River/Dunnville, Credit River, Bronte
  Creek). Run targeted ingest for these areas so observation-based features (rarity
  scoring, species presence, piscivore activity) work with real local data rather
  than returning empty results. Priority areas: Grand River at Dunnville, Credit
  River Mississauga/Streetsville, Bronte Creek Oakville.

---

## Known Bugs

- **OHN snap criteria too strict** — location resolver previously skipped trips
  that couldn't snap to an OHN segment. Fixed with sessions/stops schema (text_only
  fallback). Monitor for regressions.

---

*Last updated: Session — cost router, synthesis cache, location trip memory, backlog refresh*
