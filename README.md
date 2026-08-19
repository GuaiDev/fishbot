# Fishdex

A personal fishing exploration AI assistant. Built for anglers who want to find small streams and microhabitats — including microfishing targets like darters, dace and madtoms — instead of only popular gamefish spots.

## What it does

fishbot answers fishing questions from a local database of integrated public datasets, using the Claude API to reason over retrieved records. It runs as a CLI chat bot and as a web app (chat, map, trip log, FishDex) backed by a FastAPI service.

The core thesis: **fish presence and angler pressure are different signals**, and collapsing them into a single score is how most fishing apps go wrong. High report density usually means popular water, not abundant fish. Low density often means nobody has looked.

### Two related principles the design leans on

**Retrieval over prediction.** Claude reasons *over* retrieved specifics; it is never the source of a factual claim about a particular stretch of water. Every field carries structured provenance (`record` / `web` / `inference`) and, when empty, a specific reason for being empty — "nothing recorded within the radius" and "this source doesn't cover this area" are different statements and stay different all the way to the surface.

**Say why, not just what.** Raw values travel with their plain-language meaning. If a number has no honest "so what" for an angler, it isn't surfaced at all — a mid-range pH is reported as measured-but-unremarkable rather than dressed up as insight.

### Data sources integrated

| Source | What it provides | Scope |
|--------|-----------------|-------|
| [iNaturalist](https://www.inaturalist.org) | Species observations (citizen science) | Global |
| [GBIF](https://www.gbif.org) | Species occurrence records (museum + survey aggregates) | Global |
| [Open-Meteo](https://open-meteo.com) | Weather forecasts + barometric pressure trends | Global |
| [Water Survey of Canada](https://wateroffice.ec.gc.ca) | Real-time and historical stream gauge data | Canada |
| [OpenStreetMap](https://www.openstreetmap.org) | Water features, access points, parking, portage routes | Global |
| [eBird](https://ebird.org) | Piscivore observations as a biological proxy | Global |
| DFO stream temperature | Thermal regime classification by station | Canada |
| [MNRF Fish Stocking](https://www.ontario.ca/data/fish-stocking-summary) | Stocking history with species, life stage, density | Ontario |
| [MNRF/NatureServe Species Ranges](https://www.ontario.ca/page/species-risk-ontario) | Native range polygons + Species at Risk status | Ontario |
| [Ontario Hydro Network](https://geohub.lio.gov.on.ca) | Stream segments + connectivity graph, barriers | Ontario |
| [PWQMN](https://data.ontario.ca/dataset/provincial-stream-water-quality-monitoring-network) | Dissolved oxygen, pH, temperature, conductivity | Ontario |
| [CABIN](https://www.canada.ca/en/environment-climate-change/services/river-monitoring.html) | Benthic macroinvertebrate community (EPT) | Ontario |
| Ontario surficial geology (MRD 128) | Substrate class per reach | Ontario |
| MNRF regulations | Fisheries Management Zone rules | Ontario |
| Crown land + provincial parks | Public access boundaries | Ontario |

Water chemistry is used as a **constraint, never a confirmation**: readings can rule a species out of a reach, but passing them only means the water is habitable, not occupied.

### Conservation features

- **Species at Risk flagging** — SAR-listed species surface a conservation note wherever they are mentioned. Targeting them is not suggested.
- **Wild vs. stocked distinction** — stocked fish are planted where trucks can reach, not where habitat is best. Stocking records are kept separate from presence evidence.
- **Obscured observations handled honestly** — iNaturalist geoprivacy fuzzes coordinates to ~22 km. Those records are neither discarded nor treated as precise; they contribute soft evidence across the obscuration radius.
- **Presence vs. pressure** — tracked as separate signals, never collapsed into one score.
- **Indigenous/First Nations waters** — flagged as a separate jurisdiction. The bot does not predict within them.

## Current status

**Phase 1 (data layer) is complete.** All ingestion adapters are built and verified — 19 sub-phases covering observations, hydrology, water chemistry, benthic health, substrate, thermal regime, regulations and access.

**Phase 2 is in progress**, and one significant thing was tried and reversed:

A species distribution model was built to predict habitat suitability. It scored **0.51–0.61 AUC** on spatial cross-validation — barely better than random — largely because the specialist species this project exists to serve can't clear the minimum training threshold, while the generalists that can are found nearly everywhere. Worse, a single suitability score *concealed* the underlying records rather than revealing them.

It has been **retired from the product path**. What replaced it is a central context layer:

- `describe(place)` — everything known about one stretch of water, in slices (records, water, structure, access, conditions, personal history), each field carrying provenance and an empty-reason
- `explore(area)` — ranks water the user hasn't fished by observation scarcity, structure, access and remoteness, with **no habitat-quality term**. A plausibility gate rules segments out on affirmative evidence (a mapped ditch, a measured hypoxic reading) but never ranks them up
- `user_layer(user)` — patterns, demonstrated expertise and known gaps derived from logged activity, never configured

The model training code remains as a research tool, off the request path.

Also in Phase 2: accessibility scoring, untapped-potential ranking, spot discovery, and a satellite-imagery screening pass.

### Known limitations

Documented honestly rather than papered over — see `CLAUDE.md` for the full list:

- Access scores are only meaningful within ~55 km of home, where OSM access data was ingested. Beyond that, `explore()` rankings collapse into large ties, and the response reports how many candidates tied rather than presenting an arbitrary top ten as "best".
- `stream_order` is unpopulated on all ingested OHN segments — an adapter gap, reported as such rather than as missing data.
- Conservation Authority fish community data (the strongest unbiased ground truth) is not publicly available; MNRF's Broadscale Monitoring records live in an internal database with no public API.
- Non-Ontario jurisdictions (BC, AB, QC, national) are stubbed and frozen.

## Tech stack

- **Python 3.11+** with `uv` for dependency management
- **[Anthropic Claude API](https://www.anthropic.com)** — `claude-sonnet-4-6` default, with a router that sends classification and extraction to cheaper models
- **SQLite** via `sqlite-utils` for local storage
- **Pydantic v2** for all data models
- **FastAPI** + **React/Vite** for the web app
- **Typer** for the CLI
- **pytest** + **ruff** — 992 tests

## How to run

```bash
# Install dependencies
uv sync

# Start the chat bot
make run

# Run all ingestion adapters
make ingest

# Run tests
make test

# Lint / format
make lint
make format
```

Requires a `.env` file with:

```
ANTHROPIC_API_KEY=your_key_here
```

Optional keys unlock individual adapters and features:

| Key | Used by |
|---|---|
| `EBIRD_API_KEY` | eBird piscivore observations |
| `MAPBOX_TOKEN` | Satellite imagery links and map rendering |
| `YOUTUBE_API_KEY` | YouTube transcript ingestion |
| `DATASTREAM_API_KEY` | DataStream water quality |
| `FISHBOT_API_KEY` | Web API authentication |

Note that `.env.example` currently documents only `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `LOG_LEVEL` and `DATASTREAM_API_KEY` — the rest are read by code but undocumented there.

When deploying, set `DATA_DIR` to a persistent volume, or ingested data is lost on redeploy.

## Project scope

All data sources are publicly available under open licenses. No scraping of Instagram, Facebook, TikTok, FishBrain, FishAngler or similar platforms — this is enforced in code, not just documented. Synthesising public information is fine; reconstructing deliberately hidden locations is not. Spot discovery output stays personal — there are no export features that would broadcast location lists.

## License

MIT

---

Personal project. Plans to expand for public use once the data layer is solid. Not currently accepting contributions.
