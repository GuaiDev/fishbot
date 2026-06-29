# FishDex Backlog

Last updated: June 29 2026 (session 4)
Previously: FishBot

## Project rename
FishBot → FishDex. The name reflects the collection mechanic (personal
Pokédex for fishing). "Bot" undersold the product and alienated senior
anglers. FishDex works for beginners and experts, scales beyond Ontario.

## Architecture split
Development now split into two tracks:
- **Frontend:** Lovable-based UI rebuild, map redesign, branding
- **Backend:** Intelligence improvements, data expansion, coaching

---

## Legend
- ✅ Resolved
- 🔨 In progress
- 📋 Planned
- 💡 Future / research

---

# FRONTEND TRACK

## Branding ✅
- Name: FishDex (was FishBot)
- Tagline: "Find fish. Explore water."
- Color palette: #0A0C10 background, #1D9E75 accent, dark minimal
- Aesthetic: Linear/Raycast dark precision, not outdoorsy
- Lovable prompt written and saved at docs/fishdex_lovable_prompt.md

## React UI (current, to be replaced) ✅
Built as prototype, will be replaced by Lovable build:
- Chat, Log Trip, Trips, Map screens
- Multi-user auth gate
- react-leaflet@4.2.1 (v5 incompatible with React 18)
- Deployed at /app on Railway

## Lovable UI rebuild 📋
Use docs/fishdex_lovable_prompt.md to build FishDex in Lovable.
Reference images needed: Fishbrain map, FishAI explore, Beli personal map,
Linear dark UI.
Screens: Login, Chat, Log Trip, Map, Trips (renamed "My FishDex")
Key: react-leaflet@4.2.1, dark theme, collection mechanic feel.

## Map redesign — two-level architecture 📋
Full design document at docs/map_redesign_design_doc.md.
Summary:

### Level 1 — Stretches (low zoom)
~50-80 major named fishing stretches across province/country.
Examples: "Dunnville to Port Maitland", "Lower Credit", "Chatham to Windsor Thames"
Rendered as colored polygons/polylines. Tap to zoom into anatomy.

### Level 2 — Anatomy (high zoom, inside a stretch)
Confluences highlighted as nodes.
Dam tailwaters marked distinctively.
Access points shown (parking, trails, road crossings).
Stream network visible as lines.
Tap any feature → bot synthesis of why it's interesting.

### Personal map (Google Maps replacement for fishing)
Pin states: Saved → Fished → Productive
One tap to save from explore mode.
Only transitions to Fished/Productive when trip is logged.
NEVER shared with other users (gatekeep culture is non-negotiable).

### Explore map
Discovers stretches, anatomy within them.
Save action adds pin to personal collection.
Saved spots visible in explore with filter, not on personal map.

### Schema needed
- fishing_stretches table
- stretch_segments table (many-to-one OHN → stretch)
- stretch_anchors table (confluences, dams, access points)
- personal_pins table (user pins with state)

### Build plan (4 sessions)
1. Stretch definition — algorithmic clustering + manual curation
2. Anchor extraction — confluences, dams, access points
3. Personal pin system — schema + API + trip log integration
4. React/Lovable UI — two-level map with pin states

## Social layer (future, NOT on map) 💡
Catches and PBs only, never spot locations.
Friend caught a PB → notification/feed item.
Location opt-in and COARSE only ("Grand River" not coordinates).
Respects fishing gatekeep culture.

---

# BACKEND TRACK

## Core Intelligence (completed) ✅

### Trip logging ✅
Natural language parser, sessions/stops schema, mobile logging page,
EXIF GPS extraction, geolocation fallback.

### Auto-enrichment pipeline ✅
session_conditions: Open-Meteo weather + PWQMN water quality per session.
Anomaly detection vs historical baseline.
Retroactive enrichment script for historical sessions.
8 sessions enriched (sessions 4-10 + 27).

### Behavioral insights ✅
Auto-versioning on contradiction, cache invalidation on update.
Insight #37 (evening-only) correctly versioned out by #40 (morning viable).

### Synthesis cache ✅
Location-based cache, invalidates on insight update.
5 spots pre-warmed.
Time-forward and live-conditions queries bypass cache entirely (June 27 2026).
Forecast responses not written to cache.

### Message router ✅
Reflex/synthesis/memory routing. ~95% cost reduction.

### Multi-user auth ✅
Invite codes, Bearer tokens, per-user data isolation, rate limiting.
Admin endpoints, CLI commands.

### SDM models ✅
9 species, ecology-only features, AUC 0.51-0.61 honest.
Trip log flywheel wired in.

### Map segments ✅
47,454 OHN segments imported into map_segments table.
Auto-import on Railway startup.
/map/segments and /map/my-stops endpoints.

## Multi-jurisdiction ingest pipeline ✅ (June 28 2026)
Reusable adapter pattern. Ontario complete (Phase 1). BC, AB, QC, federal, and
Maritime province stubs added in two sessions June 28 2026.

### Phase 1 (BC first jurisdiction)
- `src/ingest/jurisdictions/config.py` — central registry (JurisdictionConfig, CronArea dataclasses)
- `src/ingest/jurisdictions/JURISDICTION_TEMPLATE.md` — checklist + schema reference
- `src/ingest/jurisdictions/ca_bc/` — BC adapters:
  - `hydro_network.py` (FWA stream network via DataBC WFS) — ~1,400 segments per 10km radius
  - `fish_observations.py` (FISS fish observations via DataBC WFS) — ~4,200 obs per 10km radius
  - `water_quality.py` (BC EMS stations) — stations discoverable; results stubbed (see below)
- `src/services/bc_ingest.py` — BC service layer
- `/ingest/data-bc` endpoint — X-Api-Key protected, returns 202 (background task)
- Model additions: `stream_order` + `segment_source` on StreamSegment; `source` on Observation
- DB migrations: idempotent column additions, jurisdiction-scoped deletes on ingest

### Critical bug fixed during build
`ingest_hydro_network()` called `delete_where()` with no filter — wiped ALL stream
segments (both ON and BC) on every Ontario ingest. Fixed to scope by jurisdiction.

### DataBC WFS quirks (document for future jurisdictions)
- All BC layers are native BC Albers (EPSG:3005). Bbox must append `,CRS:84` so the
  server reprojects lon/lat input before spatial filtering — without it, 0 results.
- `srsName=EPSG:4326` only reprojects output geometry if `GEOMETRY` is explicitly in
  `propertyName`; omitting it returns null geometry.
- `startIndex` pagination requires `sortBy=<col>` on layers without a natural PK
  (GeoServer: "Cannot do natural order without a primary key").
- `propertyName` with a non-existent field name returns HTTP 400, not 404.

### BC EMS water quality results — stubbed 📋
Layer `EMS_MONITORING_LOCN_TYPES_SVW` is correct (456 stations near Fraser River).
Results live in a separate multi-GB CSV at data.gov.bc.ca, resource ID
`76be8cdb-95b7-4a96-aae4-f3f59455fbcb`. Not queryable by bbox.
Plan: download full CSV annually, filter to nearby MONITORING_LOCATION_IDs, index locally.

### Phase 2 — national + AB + QC + Maritimes expansion (June 28 2026)

**Federal/national** (`src/ingest/jurisdictions/ca_national/`):
- `dfo_critical_habitat.py` — DFO SARA critical habitat via ArcGIS REST → `critical_habitat` table
- `dfo_sar_range.py` — DFO SAR critical habitat via ESRI REST (`dfo_sara_critical_habitat/MapServer/0`) → `species_ranges` table; no fiona required
- `tidal.py` — CHS IWLS API (no auth required); `wlp-hilo` series; requires `from`/`to` date params → `tidal_readings` table
- `datastream_water_quality.py` — DataStream OData API → `water_quality_readings` table;
  requires `DATASTREAM_API_KEY` env var (free registration at datastream.org); returns 0 with warning if absent

**BC additions** (`src/ingest/jurisdictions/ca_bc/`):
- `nuseds.py` — NuSEDS salmon escapement XLSX from DFO EDH → `salmon_escapement` table; requires openpyxl
- `regulations.py` — BC 2025-2027 fishing regulations PDF; split by Region 1-8 → `regulation_chunks` table
- `fish_observations.py` — stocking extraction added: same WFS call, filters by ACTIVITY_CODE → `stocking_records` table;
  NOTE: FISS stocking records have no quantity field

**Alberta** (`src/ingest/jurisdictions/ca_ab/`):
- `stocking.py` — planned stocking XLSX from Open Alberta → `stocking_records` table; requires openpyxl;
  NOTE: AB stocking data has no coordinates — waterbody name only, lat/lng are null
- `hydro_network.py` — stub; NHN has no queryable WFS (FTP tiles only); OSM covers AB adequately
- `regulations.py` — stub (mywildalberta.ca PDF adapter not yet built)
- `water_quality.py` — stub (AEMERA portal is map-only; DataStream covers some AB watersheds)

**Quebec** (`src/ingest/jurisdictions/ca_qc/`):
- `species_ranges.py` — MELCCFP GeoJSON via données.gouv.qc.ca (118 freshwater fish spp, COSEWIC status) → `species_ranges`
- `regulations.py` — stub
- `water_quality.py` — stub (MELCCFP RSQER is PDF-only; DataStream covers some QC watersheds)

**Province stubs** (MB, SK, NS, NB, PE `__init__.py`):
- Documents which federal/global sources cover each province
- iNat, GBIF, WSC, OSM, eBird work globally — just need targeted cron areas
- CABIN benthic covers all provinces (see below)
- Coastal provinces (NS, NB, PE): CHS tidal adapter applies

**CABIN benthic expanded**: `load_study`/`parse_benthic`/`build_samples` now return
all Canadian provinces via `visit_jurisdictions: dict[str, str]` (visit_id → jurisdiction).
`ingest_benthic_data()` wrapper preserved for backward compatibility.
Test suite updated to match new signatures (35 tests pass).

**New DB tables**: `critical_habitat`, `tidal_readings`, `salmon_escapement`
**New migration**: `regulation_chunks.zone_name TEXT` added via idempotent `ALTER TABLE`

**New service entry points**:
- `src/services/ab_ingest.py` — AB stocking, regulations, water quality
- `src/services/qc_ingest.py` — QC species ranges, regulations, water quality
- `src/services/national_ingest.py` — DFO critical habitat, DataStream water quality
- `src/services/tidal.py` — agent tool: `get_tidal_conditions_for_agent(lat, lng)`

**New API endpoints** (all X-Api-Key protected, BackgroundTask, return 202):
- `POST /ingest/data-ab` — Alberta-specific adapters
- `POST /ingest/data-qc` — Quebec-specific adapters
- `POST /ingest/data-national` — DFO critical habitat + DataStream water quality
- `POST /ingest/data-tidal` — CHS tidal predictions

**Jurisdiction config** (`config.py`): CA-AB, CA-QC, CA-MB, CA-SK, CA-NS, CA-NB, CA-PE
registered with cron areas and data_sources dicts. CA-BC updated with
stocking=True, regulations=True, salmon_escapement=True.

### Bug fixes — session 3 (June 28 2026)
Bugs found and fixed during first Railway test run of multi-province adapters:
- **openpyxl** added to pyproject.toml (required by NuSEDS and AB stocking XLSX adapters)
- **CHS tidal**: wrong base URL (`api-sine` → `api-iwls`); missing `/api/v1` prefix on endpoints;
  API requires `from`/`to` date params (400 without them) — now sends today 00:00Z to +7 days,
  rounded to midnight so cache key is stable within a day
- **DFO SAR range**: replaced GDB/fiona approach (GDAL unavailable on Railway) with ESRI REST;
  initial service path `CritHab_HabEss_2025` was 404 — corrected to `dfo_sara_critical_habitat`;
  field names corrected (`COMMON_E`, `SCIENTIFIC`, `SARASTAT_E`); bbox tiles returned 0 features
  because `inSR=4326` was missing — layer is Web Mercator and the server was interpreting
  WGS84 degree values as metre coordinates
- **QC species ranges**: CKAN package lists FGDB resources before GeoJSON; `or` condition in
  resource selection matched the FGDB entry first; fixed to require both format==geojson AND
  fish keyword — resolves to `Aires_repartition_poisson_eau_douce.geojson`
- **CABIN benthic**: `AttributeError` on `v.strip()` when a CSV field value is `None`
  (csv.DictReader returns None for missing trailing columns); fixed with `v is not None` guard

## Coaching improvements 📋
Wait for data accumulation (need 10+ stops with time_of_day).
Currently only 3 stops have time_of_day — not enough for pattern detection.
Build when data is there:
- Time-of-day pattern detector
- Bait effectiveness detector
- Conditions-based pattern detection (need 10+ enriched sessions)
- Seasonal gap detector

## Prediction system ✅
Root cause of June 20 Willoway failure identified and fixed (June 27 2026).
Two compounding bugs:
1. get_tactical_recommendation always fetched when="now" regardless of whether
   the question was about tomorrow or the weekend — predictions were silently
   grounded in today's conditions.
2. Forecast responses (tomorrow/in_3_days/this_weekend) have no pressure trend
   data — even a correct fetch couldn't return pressure for future windows.

Fixes applied:
- get_tactical_recommendation now accepts `when` parameter, passes through to
  get_conditions_for_agent. For forecast windows, pressure call is skipped and
  a sentinel string is returned: "unavailable for forecasts — treat as neutral".
- Tool input schema updated — agent can now pass when="tomorrow" etc.
- System prompt updated: conditions routing rule explicitly requires the correct
  `when` value for future questions; cites June 20 as the reason.
- Synthesis cache bypassed for time-forward and live-conditions queries (keywords:
  tomorrow, this weekend, saturday, sunday, in 3 days, next week, forecast,
  right now, today, currently, at the moment, conditions, weather).
  Time-forward responses also excluded from cache writes.

Remaining gap: forecast windows still return no pressure trend. This is a data
availability limit (Open-Meteo doesn't provide pressure forecasts in the current
call), not a code bug. The agent is told to treat it as neutral and flag it to
the user.

## SDM improvements 📋
Current AUC 0.51-0.61 — honest but improvable.
Roadmap:
- Spatial thinning to reduce sampling bias
- Riparian canopy, impervious surface, agricultural intensity features
- Ensemble models (RF + MaxEnt + BRT)
- Integrated SDMs when enough trip log data exists

## Data expansion
Status by region:

### Ontario ✅
Grand River, Credit River, Bronte Creek, Thames (4 cron areas).
Full adapter coverage: OHN, PWQMN, MNRF stocking, MNRF regs, CABIN, GBIF, iNat, eBird, OSM.

### British Columbia ✅ (June 28 2026)
4 cron areas (Fraser, Thompson, Okanagan, Skeena).
FWA hydro + FISS observations + FISS stocking + BC regs PDF + NuSEDS salmon escapement live.
EMS water quality: stations indexed, results stubbed (multi-GB CSV — see EMS note above).

### Alberta 🔨 (June 28 2026 — partial)
3 cron areas (Bow/Calgary, North Saskatchewan/Edmonton, Oldman/Lethbridge).
Stocking (planned dates XLSX) live — no coordinates in source data.
Hydro, water quality, regulations: stubbed.
DataStream covers some AB watersheds via /ingest/data-national.

### Quebec 🔨 (June 28 2026 — partial)
4 cron areas (St. Lawrence/Montreal, Saint-Maurice, Saguenay, Gatineau).
Species ranges (MELCCFP GeoJSON, 118 spp) live.
Regulations, water quality: stubbed (DataStream covers some QC watersheds).

### Manitoba + Saskatchewan 📋
3 cron areas each. Global sources only (iNat, GBIF, WSC, OSM).
DataStream covers some MB/SK watersheds via /ingest/data-national.
No province-specific adapters with public APIs found as of 2026.

### Maritimes (NS, NB, PEI) 📋
4 cron areas (Miramichi NB, Saint John NB, Annapolis NS, Margaree NS).
Global sources + CHS tidal API for coastal/tidal reach fishing.
DataStream covers Atlantic Canada watersheds.
No province-specific fish observation APIs found as of 2026.

### Federal sources ✅ (June 28 2026)
DFO critical habitat, DFO SAR critical habitat (ESRI REST, no fiona), CHS tidal predictions,
DataStream water quality (requires DATASTREAM_API_KEY) — all adapters built and verified working.

### US states 📋
Great Lakes region first: Michigan, Minnesota, Wisconsin.
- USGS NHD (equivalent of OHN)
- FishBase species ranges
- GBIF + iNat already global

### Saltwater 💡
East Coast, West Coast, Gulf.
- OBIS (Ocean Biodiversity Information System)
- NOAA data

## Voice trip logging 💡
Critical path for activating personal model at scale.
Reduces logging friction: speak → transcribe → parse → log.
Whisper API or similar.
Build after Lovable UI is stable.

## Admin dashboard 📋
/admin page showing:
- Active users and message counts
- Cost per user per day
- Popular spots (synthesis cache hits)
- Tool usage breakdown

## Token management 📋
/admin/token endpoint added (X-Api-Key only, no Bearer needed).
fishbot token CLI command added.
Still friction: local DB ≠ Railway DB.
Accepted split for now.

## Aquarium feature 💡
Premium tier feature. Each species caught = fish added to aquarium.
Animated SVG/sprite fish swimming in a canvas.
More aquarium slots = premium conversion mechanic.
Shareable — the virality unlock.
Build after core product is solid and has users.

## Free/premium tier 💡
Router foundation in place (reflex vs synthesis).
Design pending:
- Free: reflex only (generic answers, no personal data)
- Premium: synthesis + memory + coaching + full map
- Taster: first synthesis free, deeper analysis gated

---

## Infrastructure

### Railway deployment 🔨
URL: https://web-production-e2094.up.railway.app
Volume vol_wc8gnr3fyrcdcydx is attached but DATA_DIR env var is NOT set in
Railway dashboard. Database is writing to the container's ephemeral filesystem
and is wiped on every redeploy.
Fix: set DATA_DIR to the volume's mount path in Railway → service → Variables.
Once set, db_path in /admin/db-stats response will show an absolute path
confirming the volume is being used.

### Token refresh ✅
POST /admin/token with X-Api-Key returns fresh Bearer token.
No Bootstrap needed going forward.

### Local vs Railway split
Local: Jason's 22 sessions, all behavioral insights, full trip history.
Railway: Fresh database, beta tester data.
Accepted split — local for personal analysis, Railway for beta.

### /chat endpoint message assembly bug ✅ (June 27 2026)
Endpoint was reading body.get("messages", []) instead of building the messages
array from the documented schema fields (message + conversation_history).
Result: curl calls with {"message": "..."} produced an empty messages array,
causing "at least one message is required" from the Claude API.
Fix: endpoint now builds messages from history + appends current message.
make run was unaffected (CLI bypasses the HTTP endpoint entirely).
Deploy status: committed (067b616), Railway redeploy pending confirmation.

### FISS context overflow — fixed ✅ (June 29 2026)
46,294 FISS observations were being returned to Claude, exceeding context limits.
Root cause: query_observations had no LIMIT; all survey records returned regardless
of count. Fix: hard cap of 50 results (ORDER BY observed_on DESC), plus a separate
COUNT(*) query so total_count is included in the tool response. iNat records with
real dates sort first; FISS sentinel dates (1900-01-01) sort last.
Files: src/storage/observations.py, src/services/observations.py, src/services/gbif.py.

### /admin/db-stats diagnostic endpoint 🔨 (June 29 2026)
Temporary endpoint for Railway database diagnosis. Returns:
- db_path: resolved DB_PATH (shows whether relative or absolute)
- db_exists: bool — whether the file actually exists at that path
- data_dir_env: value of DATA_DIR env var, or "NOT SET"
- observations_by_source: count/lat-lng/date range per source
Remove once Railway persistence is confirmed working.

### Known dead code
ChatRequest Pydantic model (src/api/main.py:154) is unused — endpoint takes
body: dict directly. Harmless but should be cleaned up or wired in.

### GitHub Actions weekly ingest ✅
Sunday 6am UTC. 25 cron areas total (June 28 2026):
- 4 ON — hit /ingest/data
- 4 BC — hit /ingest/data + /ingest/data-bc
- 3 AB — hit /ingest/data + /ingest/data-ab
- 4 QC — hit /ingest/data + /ingest/data-qc
- 3 MB + 3 SK — hit /ingest/data only
- 4 Maritimes (Miramichi NB, Saint John NB, Annapolis NS, Margaree NS) — hit /ingest/data
- 2 tidal (Miramichi NB, Annapolis NS) — additionally hit /ingest/data-tidal

### Ingest background tasks ✅ (June 28 2026)
Both /ingest/data and /ingest/data-bc return 202 immediately via FastAPI BackgroundTasks.
Prevents Railway from killing the connection during long ingest runs.
Each source logs start, record count, and full traceback on error (logger.exception).

### Railway logging root cause fixed ✅ (June 28 2026)
Background task INFO messages were silently dropped — uvicorn's dictConfig leaves the
root logger at WARNING. Fixed: logging.basicConfig(stdout, INFO) at module import +
lifespan re-asserts setLevel(INFO) after uvicorn's own setup runs.

---

## Open research questions

### Lake-run channel catfish timing — Dunnville
When do lake-run Erie cats push up the Grand?
Track date + fish size + water temp for every Dunnville session.

### Bowfin / channel catfish ratio — Willoway
June 20: channels dominant. Prior session: bowfin dominant.
Hypothesis: conditions-driven. Need retroactive enrichment of prior session.

### Kool-aid vs natural cutbait
Controlled comparison planned: same location, same rig, one rod each.
Run at Byng or Willoway next session.

---

## Key credentials (save these)
- Railway API key: fdf0f9f1381176065637fe72a69cd651bb6ac117cbcabcf60d26988127a574a9
- Railway URL: https://web-production-e2094.up.railway.app
- Admin token endpoint: POST /admin/token with X-Api-Key header
- GitHub repo: GuaiDev/fishbot (rename to fishdex when ready)
