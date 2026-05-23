# fishbot

A personal fishing exploration AI assistant. Built for anglers who want to find small streams and microhabitats, instead of only popular gamefish spots. 

## What it does

fishbot is a CLI chat bot that answers fishing questions using a local database of integrated public datasets. It uses the Claude API to reason over the data and a growing set of agent tools to pull real-time information. The core thesis: **fish presence and angler pressure are different signals**, and collapsing them into a single score is how most fishing apps go wrong.

### Data sources integrated

| Source | What it provides | Scope |
|--------|-----------------|-------|
| [iNaturalist](https://www.inaturalist.org) | Species observations (citizen science) | Global |
| [GBIF](https://www.gbif.org) | Species occurrence records (aggregates museum + survey data) | Global |
| [Open-Meteo](https://open-meteo.com) | Weather forecasts + barometric pressure trends | Global |
| [Water Survey of Canada](https://wateroffice.ec.gc.ca) | Real-time and historical stream gauge data | Canada |
| [OpenStreetMap](https://www.openstreetmap.org) | Water features, access points, parking, portage routes | Global |
| [MNRF Fish Stocking](https://www.ontario.ca/data/fish-stocking-summary) | Stocking history with species, life stage, and density | Ontario |
| [MNRF/NatureServe Species Ranges](https://www.ontario.ca/page/species-risk-ontario) | Native range polygons + Species at Risk status | Ontario |

### Conservation features

- **Species at Risk flagging**: SAR-listed species surface a conservation note in every answer that mentions them. Targeting them is not suggested.
- **Wild vs. stocked distinction**: Every stocking record carries a `wild_population` flag. The bot treats naturally reproducing populations and put-and-take fisheries differently — stocked fish don't imply habitat quality.
- **Presence vs. pressure principle**: High observation density from iNaturalist/GBIF often means high angler pressure, not high fish abundance. Low density often means low observer effort. The bot tracks these as separate signals and doesn't collapse them. Habitat features and government survey data are weighted more heavily than catch reports for predicting where fish actually live.
- **Indigenous/First Nations waters**: Flagged as a separate jurisdiction. The bot does not predict within them.

## Current status

Phase 1 — data brain under construction. Ontario focus.

Completed sub-phases:
- **1a–1b**: Project skeleton, MVP chat bot, user profile, trip log, jurisdiction registry
- **1c**: iNaturalist ingestion + agent tool
- **1d**: Open-Meteo weather + barometric pressure
- **1f**: GBIF species occurrence
- **1g**: Water Survey of Canada stream gauges
- **1h**: OpenStreetMap water features + access points
- **1i**: MNRF fish stocking history
- **1j**: Native species ranges + Species at Risk overlays

In queue:
- **1k**: Reddit community RAG with technique extraction
- **1l**: MNRF Broadscale Monitoring + Conservation Authority surveys (primary unbiased ground truth layer)
- **1m**: Ontario Hydro Network + stream connectivity graph
- **1n**: MNRF regulations parser

Phase 2 (deferred): satellite imagery, habitat-based species distribution models, multi-jurisdiction expansion (BC, Quebec, US states).

## Tech stack

- **Python 3.11+** with `uv` for dependency management
- **[Anthropic Claude API](https://www.anthropic.com)** — `claude-sonnet-4-6` default
- **SQLite** via `sqlite-utils` for local data storage
- **Pydantic v2** for all data models
- **Typer** for the CLI
- **pytest** + **ruff** for tests and linting

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

## Project scope

All data sources used are publicly available under open licenses. No scraping of Instagram, TikTok, FishBrain, or similar platforms. Spot discovery output is personal — no export features that would broadcast location lists.

## License

MIT

---

Personal project. Plans to expand for public use once the data layer is solid. Not currently accepting contributions.
