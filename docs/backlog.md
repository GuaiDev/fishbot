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

- **Proactive coaching layer** ✅ — Built and verified. Three pattern detectors in
  priority order: (1) location slump — consecutive blanks at previously productive spot,
  (2) species gap — species in insights never personally caught, (3) technique pattern —
  techniques that only appear in productive sessions. Fires at most once per session,
  only when thresholds crossed (min 3 sessions). Verified: Byng Island slump detected
  and surfaced naturally in log_trip response.

- **Proactive coaching — additional detectors** — current detectors: location slump,
  species gap, technique pattern. Future additions:
  - Seasonal pattern: "You catch redhorse in April but never in September — have you
    tried the Thames in fall?"
  - Bait effectiveness: "Your successful catfish sessions used cutbait, blanks used
    worm — want to test this pattern deliberately?"
  - Time-of-day pattern: "All your productive Byng sessions were before 11am — your
    afternoon sessions there have been unproductive"
  Add when trip log has enough data (suggested: 10+ stops per location).

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

- **Trip logs as SDM training data** ✅ — Built and wired. `species_mapping.py` with
  ~70 species common↔scientific. `_get_presence_points()` now pulls from stops table
  (productive stops with valid coordinates only). `sdm-contributions` CLI shows
  breakdown per model. Creek chub: 2 trip log records. White sucker: 1. Grows
  automatically with every logged trip.

- **SDM retraining trigger** — currently requires manual `uv run fishbot train-sdm`.
  Should trigger automatically when trip log presence records grow meaningfully for a
  species (suggested threshold: new trip log points exceed 20% of existing iNat+GBIF
  count for that species). Add as part of ingest scheduling work.

- **Species mapping expansion** — `species_mapping.py` covers ~70 species. As new
  species appear in trip logs that aren't mapped, they silently don't contribute to
  SDM training. Add a warning when a common name from a stop can't be mapped to a
  scientific name — log it so the mapping can be expanded. Also consider auto-lookup
  via GBIF species API for unmapped names.

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

- **Synthesis cache wired into router** ✅ — Location extraction added to router. Cache
  check before full pipeline for synthesis-mode queries. Cache hit returns via Haiku (very
  cheap). Fuzzy name matching handles slight phrasing differences. Verified: Willoway Park
  query served from cache on second ask.

- **Context validator false positive** ✅ — Validator now only warns on river names
  genuinely new to the updated context, not ones already present from previous sessions.
  `_validate_context()` signature updated to accept `existing` parameter.

- **Tool-level API usage tracking** — all API calls currently log as endpoint="chat".
  Can't see which tools (get_recent_observations, get_behavioral_insights, etc.) are
  expensive. Add tool name tracking to api_usage when tool calls fire in
  `_run_full_pipeline`. Needed for: identifying which tools to prioritize for caching,
  understanding true cost per query type, future per-user billing.

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

- **Ingest scheduling** ✅ — GitHub Actions weekly cron (Sunday 6am UTC) calling
  `/ingest/data` endpoint for 4 areas: Grand River/Dunnville, Credit River, Bronte Creek,
  Thames/London. API key protected via X-Api-Key header. Manual trigger available from
  GitHub Actions UI.

- **Trip logs as SDM training data** ✅ — see Personal Model section.

- **SDM contribution tracking as a product metric** — `uv run fishbot sdm-contributions`
  shows iNat/GBIF/TripLog breakdown per model. When FishBot has users, total trip log
  contributions across all users becomes a meaningful data asset metric: "X,000
  angler-confirmed catches informing Ontario species predictions." Track this over time.
  Eventually surface in the UI as a trust signal ("predictions informed by your catches
  + X community catches").

---

## Map & UI

- **Mapbox GL JS map rebuild** — replace current Leaflet prototype with proper
  Mapbox GL JS implementation. Better performance, satellite imagery, mobile-ready.
  Not yet started.

- **Mobile UI** — build a mobile-friendly web interface that talks to the FastAPI
  server. Required before EXIF photo logging, voice logging, and public access
  are meaningful. Not yet started.

### Native iOS/Android app
iOS Safari strips GPS from photos uploaded via file input — a known Apple privacy
decision. The geolocation fallback works but requires a permission tap. A native
app would get full EXIF access (precise GPS from photo metadata, no permission
dialog) plus: push notifications for trip reminders, background location logging,
offline trip drafts. Build after the web UI is proven and user base exists.
Flutter or React Native are the right choices for cross-platform.

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

- **API authentication** ✅ — X-Api-Key header check on `/ingest/data` endpoint.
  Dev mode allows requests without a key. Add key to Railway Variables and GitHub
  Secrets before making server public.

- **`ensure_schema()` not called on startup** ✅ — Fixed via FastAPI lifespan event.
  `ensure_schema()` called once on server boot.

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

*Last updated: Session — Proactive coaching, ingest scheduling, synthesis cache, context validator fix*
