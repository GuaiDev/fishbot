## Project

Personal fishing exploration bot. Multi-jurisdiction (Canada + US), Ontario first. Phase 1 = data brain under construction. Gamification, aquarium, trip planner, map UI all deferred. NOT for public release.

## My fishing context

- Home: Toronto, Ontario (CA-ON)
- Target species: ALL species including microfishing targets (darters, dace, madtoms, shiners, chubs, lampreys) — not just popular gamefish
- Fishing style: stream + small lakes primarily
- Skill: intermediate
- Top priority: exploration over catch optimization
- First-time vibe coder — explain things plainly, no jargon assumed

## Tech stack

Python 3.11+, uv, SQLite via sqlite-utils, Anthropic SDK (claude-sonnet-4-6 default), typer CLI, pytest, ruff.

## Architectural rules (enforced)

- Every location-bound record carries ISO 3166-2 jurisdiction code (CA-ON, US-MI, etc.)
- Global ingest adapters: `src/ingest/global/` — work anywhere
- Jurisdiction-specific adapters: `src/ingest/jurisdictions/<code>/` — Ontario built first, others added as adapters
- Agent talks to services (`src/services/`), never directly to ingest modules
- Every external API call goes through cache. No exceptions.
- Pydantic models live in `src/models/` — never inline schemas

## Ethical rules (decided, do not relitigate)

- Synthesizing public information is FINE: named locations in public videos, forum posts, iNaturalist observations, government datasets, YouTube transcripts
- Reconstructing deliberately-hidden information is NOT: no vision pipeline to de-anonymize locations a creator intentionally obscured
- No scraping: Instagram, Facebook, TikTok, FishBrain, FishAngler (ToS + active enforcement)
- Indigenous/First Nations waters: flag as separate jurisdiction, do not predict within them
- Spot discovery output stays personal — no export features that broadcast spot lists

## Core principle: presence vs. pressure

Crowdsourced catch and observation data measures angler activity as much as fish presence. The bot must not confuse the two:

- High report density does not imply high habitat quality. It often implies high pressure.
- Low report density does not imply absence. It often implies low access or low observer effort.
- Habitat features and systematic survey data (Conservation Authority electrofishing surveys, government datasets) are stronger signals than catch reports for predicting where fish actually live.
- "Untapped potential" inverts report density: high habitat × low reports × good access = top score.
- When citing community data, the bot should distinguish between "fish are here" (presence) and "people are here" (pressure).

Refinement: Some famous spots — Caledonia for walleye/gar, Dunnville for channel cats, the Thames for redhorse — are popular because of structural productivity (chokepoints, spawning runs, rare habitat) that pressure cannot fully erase. The bot tracks reputation, pressure estimate, and structural productivity as separate signals. A spot can be high on all three; the bot acknowledges this honestly. The user's question determines whether reputation/pressure are weighted as positive (they want a sure bet) or negative (they want solitude). Never collapse these into a single score.

This is the project's central thesis. It reshapes every prediction the bot makes.

OSM data tells us what water exists and where. It does not tell us whether fish are there or in what quantity. Never use water body size, name presence, or access quality as proxies for fish abundance or quality. These are convenience factors only. Habitat suitability and species predictions require Phase 2 data layers. When asked for "best spots", always be explicit about what data is and isn't available yet and what is being built to fill the gap.

## Conventions

- `uv add` for all dependencies (never bare pip)
- ruff for lint + format
- pytest for tests, fixtures in `tests/fixtures/`
- Conventional commits: feat, fix, refactor, docs, test, chore
- All new pydantic models get tests
- All new external API integrations get cached + have a recorded fixture for tests
- Assistant content blocks sent back to the API must be serialized to only API-accepted fields — never use `.model_dump()` directly on SDK content blocks because it includes internal fields the API rejects
- Never insert test or seed data into the production database during development. Tests must use temporary databases (e.g. pytest's `tmp_path`) to avoid polluting real user data.

## How to run

- `make run` — start CLI bot
- `make ingest` — run ingestion adapters
- `make test` — run tests
- `make lint` — check style
- `make format` — auto-format

## Where things live

- Product spec: `docs/planning/` (read before suggesting any feature)
- System prompt: `prompts/system.md` (edit without code changes)
- This file: read every session start

## Phase 1 data source roadmap

Completed:
- 1a: Project skeleton
- 1b: MVP chat bot, profile, trip log, jurisdiction registry
- 1c: iNaturalist ingestion + agent tool
- 1d: Open-Meteo weather + barometric pressure trends
- 1e: Tactical recommender
- 1f: GBIF species occurrence
- 1g: Water Survey of Canada stream gauges
- 1h: OpenStreetMap water features + access
- 1i: MNRF stocking history
- 1j: Native range maps + Species at Risk overlays
- 1k: Reddit community RAG with technique extraction
- 1m: Ontario Hydro Network + stream connectivity graph
- 1n: MNRF regulations parser (PDF → FMZ zone chunks, get_regulations agent tool)

Queued (in suggested order):
- 1l: Conservation Authority fish surveys — BLOCKED, see note below

Phase 1 data brain is otherwise complete. See Phase 2 deferred list below.

Deferred to Phase 2:
- Satellite imagery ingestion (Sentinel-2, NAIP, SWOOP)
- Satellite-derived bathymetry
- Microsoft Building Footprints + accessibility scoring
- Spot discovery pipeline
- Habitat-based species distribution models (first real ML layer)
- Multi-jurisdiction expansion (BC, Quebec, US states beyond stubs)

Sub-phases 1f through 1j are small (1-2 sessions each). 1k is medium. 1m and 1n are the next big ones.

## Data source reality check: 1l

**MNRF Broadscale Monitoring (BsM) fish community data is not publicly available.**
The actual survey records (species counts, lengths, weights from standardised lake
netting and electrofishing) live in an internal MNRF database called `fishnetv3`.
There is no public API, no bulk export, and no ArcGIS FeatureServer for this data.

**Fish ON-Line is UI-only.** The GeoHub item (`4ee94762ab4e453f95fd977bfbf59e4a`)
resolves to a Geocortex web application backed by a single MapServer with 13 layers —
all administrative (access points, management zones, bathymetry, licence issuers).
No species observation layer exists in the REST service. Species data shown in the app
is served by internal Geocortex workflows with no queryable external endpoint.
Bulk download is not possible; the open data catalogue entries are HTML links to the
app itself.

The only publicly available BsM data is **water chemistry** (pH, TP, DOC, 2008–2023)
on data.ontario.ca — not fish community records.

**TRCA RWMP is the closest real alternative.** The Toronto and Region Conservation
Authority publishes Regional Watershed Monitoring Program (RWMP) fish community data
at data.trca.ca — stream electrofishing (OSAP single-pass) across 9 Toronto-region
watersheds (Humber, Don, Rouge, Duffins, Carruthers, Highland, Petticoat, Etobicoke,
Mimico), 26 fixed stations resurveyed every ~3 years since 2000. Fields: species,
count, total weight. SAR records removed from public release.
Direct CSV: `data.trca.ca/dataset/00c1bab2-f6f5-44a9-9cc0-830960530f04/resource/
4cca6683-a08b-4d0c-8faf-4952fca0ef58/download/2020-rwmp-fish-community-data.csv`
**Caveat:** the data.trca.ca portal was consistently unresponsive during research
(May 2026). When the portal becomes reliably accessible, a TRCA adapter can be added
following the same pattern as `src/ingest/jurisdictions/ca_on/stocking.py`.
