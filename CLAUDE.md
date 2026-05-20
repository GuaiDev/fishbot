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
- Habitat features and systematic survey data (MNRF Broadscale Monitoring, Conservation Authority surveys, government datasets) are stronger signals than catch reports for predicting where fish actually live.
- "Untapped potential" inverts report density: high habitat × low reports × good access = top score.
- When citing community data, the bot should distinguish between "fish are here" (presence) and "people are here" (pressure).

Refinement: Some famous spots — Caledonia for walleye/gar, Dunnville for channel cats, the Thames for redhorse — are popular because of structural productivity (chokepoints, spawning runs, rare habitat) that pressure cannot fully erase. The bot tracks reputation, pressure estimate, and structural productivity as separate signals. A spot can be high on all three; the bot acknowledges this honestly. The user's question determines whether reputation/pressure are weighted as positive (they want a sure bet) or negative (they want solitude). Never collapse these into a single score.

This is the project's central thesis. It reshapes every prediction the bot makes.

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
