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
  **✅ Resolved:** Fixed in this session — `party_species_caught` field added to stops table
  and parser. `get_trips_at_location` now clearly distinguishes "you caught: X
  (others in party: Y)" from party-only catches.

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
  **✅ Resolved:** Fixed in this session — `match_insights_to_stop()` now has a location-only
  branch for unproductive stops with coordinates. Blank at a known spot now triggers
  contradiction checking even with empty `species_caught`.

- **SDM observation bias features** ✅ — Removed `observation_density_25km` and
  `distance_to_nearest_observation_km` from SDM training. All 9 models retrained with
  ecology-only features. AUC scores dropped 0.05–0.09 (expected — scores were inflated
  by sampling bias). Models now predict habitat, not observer effort.

- **Lake-run timing tracker — Grand River / Dunnville** — no data on when lake-run
  channel catfish push up the Grand River from Lake Erie. Log date + fish size + water
  temp for every Dunnville session. Pattern will emerge from real data over time.
  Currently flagged as open research question in angler context.

- **Kool-aid vs natural cutbait comparison** — one session data point — not enough to
  conclude anything. Design a controlled side-by-side: same location, same rig, one rod
  natural, one rod kool-aid soaked, track strikes per rod. Run deliberately at Byng or
  Willoway next session.

- **Dynamic profile from trip history (Option B)** — the static profile (set once via
  `fishbot profile`) will go stale over time as fishing interests evolve. Long-term fix:
  deprecate preference fields in the profile entirely and infer them from trip log history
  instead. Species targets, fishing style, skill indicators — all derived from what the
  angler actually catches and where they fish, not from what they declared at signup. The
  profile becomes purely administrative (home location, jurisdiction). Implement when the
  `stops` table has enough history to make inference reliable (suggested: 20+ stops).

- **Coaching layer — on-demand** ✅ — Built and verified. `get_coaching` tool with
  species and location modes. Pulls actual trip log data, behavioral insights; Haiku
  generates diagnosis. Verified: madtom query honestly states no logged catches; Byng
  Island query references actual Santee Cooper / 5lb cat / turbid conditions data.

- **Proactive coaching layer** — on-demand coaching is built. Next: proactive coaching
  that fires after logging a session when meaningful patterns emerge:
  - 3+ consecutive blanks at a previously productive spot
  - 5+ attempts at a target species with zero personal catches
  - Technique underperformance vs. personal baseline
  Fires at most once per session, one observation with offer to help. Never lectures.
  Premium tier. Connect to confidence escalation system — dropping confidence on an
  insight the user keeps acting on is the main trigger signal.

- **SDM improvement roadmap** — current AUC: 0.51–0.61 (honest but weak). Long-term
  improvement path:
  1. Spatial thinning of presence records to break urban clustering bias
  2. Add missing features: riparian canopy cover, upstream impervious surface %,
     agricultural land use intensity, seasonal flow variability
  3. Ensemble models (Random Forest + MaxEnt + BRT)
  4. Trip log data as unbiased presence records — every logged catch in an
     undersampled area (Dunnville, rural Grand River) is high-value training data
  5. Eventually: integrated SDMs that model observation process alongside ecology

- **SDM retraining automation** — models should retrain automatically when new ingest
  data meaningfully expands presence records for a species (suggested threshold: +20%
  presence records). Currently requires manual `uv run fishbot train-sdm`. Add to
  scheduled refresh.

---

## Agent Behaviour

- **SDM confidence framing** ✅ — System prompt updated with DO/DO NOT framing, AUC
  range (0.51–0.61) cited inline, models framed as "exploration tool not presence
  confirmation." Verified: bot correctly hedges predictions and surfaces AUC caveat in
  responses.

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

- **Synthesis cache — wire into tools** — `segment_synthesis` table and
  `synthesis_cache.py` are built and ready. Next step: wire cache check/store into the
  heaviest synthesis tools (likely `get_species_habitat_predictions` or wherever
  watershed/geology cross-referencing happens). Cache miss → run full synthesis + store.
  Cache hit → return stored result via Haiku (very cheap). This is what makes the
  expensive Willoway-style analysis nearly free after the first query.

- **Router — synthesis cache integration for Willoway-style questions** — when the
  router classifies a message as "synthesis" and the query is about a
  named/coordinate location, check `segment_synthesis` cache first before invoking
  the full pipeline. If hit, answer from cache with Haiku (very cheap). If miss,
  run full pipeline and store result. This is the key step to making synthesis mode
  cheap at runtime.

- **Free/premium tier boundary** — router mode field (`reflex`/`synthesis`/`memory`)
  flowing through `api_usage` is the foundation of the split. Design pending:
  - Free: reflex only. Generic fishing knowledge, Haiku, no tools.
  - Premium: synthesis + memory + coaching. Full pipeline, personal data.
  - Taster: first synthesis result shown free, deeper analysis gated.
  - Leading questions: reflex answers offer synthesis upgrade as conversion mechanism.
  Build when ready to think about launching.

- **Context document — coordinate embedding** — Rule 9 added to Haiku merge: when session
  summaries include coordinates, embed them in spot entries e.g. "Willoway Park, Grand River
  (42.917, -79.774)". Monitor that this is actually happening as new trips get logged with
  coordinates. Over time, the spots section should become a precise coordinate-linked reference,
  not just text descriptions.

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

- **Ingest scheduling** — three target areas ingested manually this session (Grand
  River/Dunnville, Credit River, Bronte Creek). Should run on a weekly schedule
  automatically. Add a GitHub Actions workflow or Railway cron job to run
  `fishbot ingest --lat X --lng Y --radius Z` for each target area weekly.

- **Trip logs as SDM training data** — every species catch logged by users is an
  unbiased presence record that improves SDM accuracy in undersampled areas. Build a
  pipeline that periodically extracts confirmed species catches from the `stops` table
  and adds them to the SDM feature matrix as presence records before retraining. This
  is the data flywheel that improves predictions in rural/remote areas where citizen
  science is sparse.

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

*Last updated: Session — SDM retrain (bias features removed), on-demand coaching layer, SDM confidence framing, proactive coaching, SDM roadmap*
