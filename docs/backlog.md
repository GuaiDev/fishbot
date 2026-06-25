# FishBot Backlog

Last updated: June 2026

## Legend
- ✅ Resolved
- 🔨 In progress / partially built
- 📋 Planned
- 💡 Future / research

---

## Core Intelligence

### Behavioral Insights & Contradiction System ✅
- Auto-versioning of contradicted insights on record
- Contradiction keywords trigger refine_insight()
- Cache invalidation when insights updated for a location
- Insight #37 (evening-only) correctly versioned out by #40 (morning viable)

### Synthesis Cache ✅
- Lazy precompute — synthesize on first query, reuse forever
- Location extraction via Haiku before pipeline
- Cache hit → Haiku reformulates cheaply
- Invalidates when behavioral insights updated for that location
- 5 spots pre-warmed: Willoway, Byng Island, North London Athletic Fields,
  Credit River Creditview, Bronte Creek Oakville

### Message Router ✅
- Haiku classifier → reflex / synthesis / memory
- Errs toward synthesis on uncertainty
- Reflex → cheap Haiku answer + leading question
- Synthesis → cache check → full pipeline on miss
- Memory → full pipeline with log tools
- ~95% cost reduction on simple queries

### SDM Models ✅
- 9 species, Random Forest, spatial block CV
- Observation bias features removed (observation_density_25km,
  distance_to_nearest_observation_km) — were 48% of signal
- Ecology-only features: substrate, stream order, temp, EPT, confluences
- Current AUC: 0.51-0.61 (honest, not inflated by sampling bias)
- Trip log catches injected as presence records (data flywheel)
- Creek chub: 2 trip log records. White sucker: 1.
- SDM confidence framing in system prompt: "worth investigating" not
  "predicted present"

### Auto-Enrichment Pipeline ✅
- session_conditions table: air temp, pressure, cloud cover, wind,
  precip history, water quality, anomaly flags, moon phase, days since rain
- Open-Meteo archive API (no key, back to 1940): weather at exact timestamp
- PWQMN local DB: nearest station water quality within 50km/45 days
- Anomaly detection: compare current vs historical baseline for month/location
- 3-second timeout via ThreadPoolExecutor — never blocks logging
- Verified: June 20 Willoway enriched with 17.2°C, 990.4 hPa, cold_air flag

---

## Trip Logging

### Sessions/Stops Schema ✅
- sessions + stops tables (replaced flat parsed_trips)
- Multi-stop sessions supported
- location_method, location_confidence, was_productive
- party_species_caught separate from user species_caught

### Natural Language Parser ✅
- Species hallucination prevention (_validate_species)
- User vs party catch distinction
- time_of_day, hour_of_day extraction from text
- Fuzzy location resolution (name match → landmark → geocode → text_only)

### Mobile Logging Page ✅
- Live at https://web-production-e2094.up.railway.app/log
- EXIF GPS extraction (Android)
- Geolocation fallback (iOS — one permission tap)
- photo_lat, photo_lng, photo_taken_at → stops table
- time_of_day derived from EXIF timestamp

### Multi-Technique Stop Logging 📋
- Current schema: one technique field per stop
- June 20 Willoway had 3 simultaneous rigs (Santee Cooper, Carolina, packbait)
  producing 3 different species profiles
- Need: array of {technique, gear, species_caught} per stop
- Schema migration + parser update required

### Voice Trip Logging 💡
- Critical path for activating personal model at scale
- Mobile page → voice memo → transcribe → parse
- Reduces logging friction dramatically
- Requires Whisper API or similar

---

## Coaching Layer

### On-Demand Coaching ✅
- get_coaching tool: species and location modes
- Queries trip logs + behavioral insights
- Honest about sparse data
- Verified: madtom query honestly states no logged catches;
  Byng Island query references actual rig/catch data

### Proactive Coaching ✅
- Fires after session logging when thresholds crossed
- Location slump detector: consecutive blanks at productive spot
- Species gap detector: species in insights never personally caught
- Technique pattern detector: techniques only in productive sessions
- Min 3 sessions before firing, max once per session

### Additional Coaching Detectors 📋
Wait until 10+ stops with time_of_day and 5+ stops per location before building:
- Time-of-day pattern: "all productive Byng sessions before 11am — why?"
  (hypothesis + question, not conclusion)
- Seasonal gap: "you fish Thames in April, never in October"
- Bait effectiveness: "cutbait sessions productive, worm sessions mixed —
  could be bait, could be conditions, which was it?"
All detectors should hypothesize and ask rather than conclude.

### Conditions-Based Pattern Detection 📋
session_conditions accumulating structured features. When 10+ sessions enriched:
- Correlate pressure_hpa + cloud_cover_pct + air_temp_anomaly_c vs catch rate
- Key hypothesis: low pressure + overcast → morning channel cat activity
- High pressure + clear → evening activity
- Post-cold-front window → aggressive feeding before conditions stabilize
This is the statistical learning layer that makes predictions principled.

---

## Personal Model

### Rolling Angler Context ✅
- Single-row table, Haiku-merged after each session
- Sections: Active plans, Spots on radar, Learned patterns, Species intel
- Context priority over static profile
- River name hallucination prevention (rules 8 & 9 in Haiku merge prompt)
- Coordinate embedding when present in session summaries

### Static Profile → Dynamic Inference 📋
Current profile (set once, goes stale) should be replaced by inference from
trip log history:
- Species targets → infer from what angler actually catches
- Fishing style → infer from techniques used across sessions
- Skill level → infer from species diversity and technique sophistication
- Profile becomes administrative only: home location, jurisdiction
Implement when stops table has 20+ entries. Until then, profile + context
document together are sufficient.

### Retroactive Session Enrichment 📋
Sessions 1-26 have no conditions data. For sessions with known coordinates
(Willoway Park, Byng Island, North London Athletic Fields), run
enrich_session_conditions retroactively via a script.
Session 27 already enriched manually as proof of concept.

---

## Data Sources

### Ingest Pipeline ✅
Full pipeline: iNaturalist, GBIF, WSC gauges, OSM water features,
MNRF stocking, OHN stream segments, regulations, PWQMN water quality,
CABIN benthic, eBird piscivore, provincial parks, Crown land
--lat/--lng flags for targeted area ingest

### Ingest Scheduling ✅
GitHub Actions weekly cron (Sunday 6am UTC)
4 areas: Grand River/Dunnville, Credit River/Mississauga,
Bronte Creek/Oakville, Thames River/London
API key protected via X-Api-Key header

### Species Mapping ✅
~70 species common ↔ scientific name mapping
Trip log catches → SDM presence records

### Reddit RAG 💡
Blocked on API credentials (403 on current setup).
Investigate Reddit API access requirements.
r/OntarioFishing has dense local knowledge especially for underreported
areas like Dunnville. Architecture identical to YouTube RAG when credentials
arrive.

### YouTube RAG ✅
Transcript ingestion, chunking, embedding, FTS5 search
search_knowledge_base tool in agent

---

## Prediction System

### Prediction Validation Experiment 🔨
June 20 Willoway test findings:
- Model predicted morning slow, evening prime
- Reality: morning smash fest, evening slower
- Root cause: bot had wrong weather data (forecast vs actual conditions —
  actual was 990.4 hPa low pressure, overcast, 4.9°C below normal)
- Low pressure + overcast is a known catfish trigger
- With enrichment pipeline, future predictions will use actual conditions

Next test: before next Willoway session, ask for prediction noting what
conditions bot cites. With enriched conditions data, morning should now
be predicted as viable (insights #34 + #40 both current, #37 versioned out).

### Prediction Confidence Calibration 📋
Model expressed high confidence on morning prediction with only 1 prior
Willoway session. Need to express lower confidence when:
- Fewer than 3 data points for a specific time window at a specific location
- Conditions data unavailable or stale
- Species composition variable (bowfin/catfish ratio fluctuation)
System prompt addition: "For time-window predictions with <3 data points,
explicitly state low confidence and explain why."

### Live Conditions in Predictions 📋
When predicting for today/tomorrow:
1. Fetch current pressure + temp via get_stream_conditions_for_agent
2. Compare to historical pattern (low pressure → morning, high → evening)
3. Flag when prediction is based on forecast vs actual measured conditions
The enrichment pipeline gives ground truth for past sessions; predictions
for future sessions need live condition data wired in explicitly.

---

## Infrastructure

### Cost Architecture ✅
Router: reflex (Haiku, no tools) / synthesis (cache → pipeline) / memory
Tool-level usage tracking via tool_usage table
fishbot tool-stats command
All costs logged to api_usage with endpoint field

### ensure_schema() on Startup ✅
FastAPI lifespan event calls ensure_schema() on server boot

### API Authentication ✅
X-Api-Key header on /ingest/data and /log-trip
Dev mode allows without key

### SDM Retraining Automation 📋
Currently manual: uv run fishbot train-sdm
Should trigger when trip log presence records grow meaningfully
(suggested: new trip log points exceed 20% of existing iNat+GBIF for a species)
Add to ingest scheduling or as separate weekly GitHub Actions job

### Cache Prewarm Automation 📋
scripts/prewarm_cache.py requires manual runs.
After weekly ingest, automatically prewarm cache for spots in the angler
context document. New spots added to "Spots on radar" should get synthesis
cached on next ingest run.

### Tool-Level Cost Tracking 📋
tool_usage table tracks which tools are called.
Next step: add actual cost in $ per tool call based on token counts.
Needed for: identifying expensive tools to prioritize for caching,
future per-user billing.

### Local vs Railway Database Sync 📋
Current state: local database has Jason's full trip history (22+ sessions).
Railway database started fresh with multi-user auth.
Decision: accept the split. Local CLI for personal analysis; Railway is the
beta environment where new trips from all users accumulate including Jason
logging new trips via the web app.
If a one-time migration is needed: export local sessions → /admin/import
endpoint or direct DB copy via Railway CLI.

### Token Management 📋
Admin token currently retrieved manually via /admin/bootstrap + curl.
Consider: fishbot token command that retrieves/refreshes the admin token
without needing to curl manually. Or store in a local .env file.

---

## UI / Product

### React Web UI ✅
Built and deployed at https://web-production-e2094.up.railway.app/app
Three screens: Chat (home), Log Trip, Trips history.
Dark theme, mobile-first, bottom nav, + button always visible in chat.
Vite + React, served from FastAPI at /app.

### Native iOS/Android App 💡
iOS Safari strips GPS from photos (Apple privacy decision).
Geolocation fallback works but requires permission tap.
Native app would provide: full EXIF access, push notifications,
background location, offline trip drafts.
Flutter or React Native for cross-platform.
Build after web UI is proven and user base exists.

### Multi-User Architecture ✅
- users, invite_codes, user_sessions, daily_usage tables
- user_id added to all personal tables (sessions, stops, behavioral_insights,
  angler_context, session_conditions, chat_sessions, chat_messages)
- Synthesis cache and SDM predictions remain shared (no user_id)
- Invite code auth: generate via CLI or admin API
- 50 message/day rate limit for beta users
- Admin endpoints: /admin/bootstrap, /admin/invite, /admin/invites, /admin/users
- CLI: fishbot invite --note "name", fishbot users
- React: Login screen, auth gate in App.jsx, 401/429 handling

### Map screen — personal mode + explore mode ✅
Built and deployed. React map with two toggleable modes:
- Personal mode: user's logged stops as green/grey dots
- Explore mode: 47,454 OHN segments colored by SDM score (red→blue)
- Scoring mode selector: balanced / easy access / adventure
- Bottom sheet on tap: stream details, species predictions, Google Maps + SWOOP links
- Viewport-bounded API: /map/segments returns only segments in current view
- map_segments table imported from map_data.json (47,454 rows)
- Auto-import on Railway startup if table is empty
- react-leaflet downgraded to v4 (v5 incompatible with React 18)

### Admin Dashboard 💡
Simple web page at /admin showing:
- Active users and message counts
- Cost per user per day
- Which spots are being asked about most (synthesis cache hit counts)
- Which tools are firing most (tool_usage table)
Useful for monitoring beta tester activity and model performance.

### Map — explore mode improvements (next session) 📋
Current state: dots appear when zoomed in past zoom 11, colored by score.
Improvements needed:
- Heatmap at low zoom (below zoom 11) showing hotspot density
  Use leaflet.heat plugin — already used in src/map/index.html
  Pre-aggregate heatmap data from map_segments table
- "Zoom in to see spots" hint disappears when dots are visible
- Filter panel: stream order filter, confluence-only toggle, species filter
- Performance: currently fetches 300 segments per viewport pan — test
  whether this feels responsive on mobile or needs further optimization

### Map — personal mode improvements 📋
- Empty state currently shows but needs better copy
- Add "Save to explore later" button on explore mode segments
  Creates a saved_spots table, segments show differently in personal mode
  This is the "explore → personal" pipeline that solves cold-start problem
- Show trip count per location (if same spot fished multiple times)
- Color intensity reflects catch rate, not just productive/unproductive binary

### Map — token management 📋
Admin token expires and requires bootstrap curl to refresh.
Add a CLI command: fishbot token → prints current valid admin token
or refreshes it automatically. Reduces friction for generating invite codes.

### Admin dashboard 📋
Track beta tester activity:
- Messages per user per day
- Which spots are being asked about (synthesis cache hit counts)
- Cost per user
Simple /admin page served from FastAPI, protected by admin role.

### Free / Premium Tier Boundary 📋
Router mode field (reflex/synthesis/memory) in api_usage is the foundation.
Design pending:
- Free: reflex only. Generic fishing knowledge, Haiku, no tools.
- Premium: synthesis + memory + coaching. Full pipeline, personal data.
- Taster: first synthesis result shown free, deeper analysis gated.
- Leading questions: reflex answers offer synthesis upgrade as conversion.
Build when multi-user architecture exists.

---

## Open Research Questions

### Lake-Run Channel Catfish Timing — Dunnville
When do lake-run Erie cats push up the Grand River?
General pattern: May-June spawn timing, possible fall push.
This year ran cold — likely delayed.
Track: date + fish size + water temp for every Dunnville session.
Pattern will emerge after 5+ sessions across different months.

### Bowfin / Channel Catfish Ratio — Willoway
June 20: channels dominant all day, 1 bowfin.
Prior session: bowfin dominant, channels rare until night.
Hypothesis: water temp, flow, or barometric pressure drives ratio.
Need: structured conditions data for both sessions to correlate.
June 20 now enriched (990.4 hPa, 17.2°C, cold_air). Prior session not enriched.
Retroactive enrichment would enable comparison.

### Kool-Aid vs Natural Cutbait
One controlled comparison planned: same location, same rig, one rod natural,
one rod kool-aid soaked. Track strikes per rod.
Run deliberately at Byng or Willoway next session.
