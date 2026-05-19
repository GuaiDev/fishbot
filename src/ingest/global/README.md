# src/ingest/global/

Data ingestion adapters that work regardless of jurisdiction.

Planned modules:
- `inaturalist.py` — species observations, all taxa (Sub-phase 1c)
- `weather.py` — conditions and forecast via Open-Meteo (Sub-phase 1d)
- `osm.py` — water features, access points, public land tags
- `sentinel.py` — satellite imagery via Copernicus/ESA
- `jrc_water.py` — JRC Global Surface Water dataset

Rules:
- Every adapter must cache all external HTTP responses under `data/cache/`
- No real API calls in tests — use recorded fixtures in `tests/fixtures/`
- Return pydantic models defined in `src/models/`, never raw dicts
- Tag every observation with an ISO 3166-2 jurisdiction code
