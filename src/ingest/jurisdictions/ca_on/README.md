# src/ingest/jurisdictions/ca_on/

Ingestion adapters specific to Ontario (ISO 3166-2: CA-ON).

This is the reference implementation. When adding a new jurisdiction, copy this
directory structure and replace data sources with the new jurisdiction's equivalents.

Planned modules:
- `regulations.py` — parse MNRF Fishing Regulations Summary PDFs by zone
- `stocking.py` — Ontario fish stocking CSV from Ontario Open Data Portal
- `hydrology.py` — Ontario Hydro Network (OHN) stream graph
- `barriers.py` — MNRF dam, culvert, and falls dataset
- `boat_launches.py` — MNRF public boat launch locations
- `crown_land.py` — Crown Land Use Policy Atlas (public land boundaries)
- `mnrf_surveys.py` — Broadscale Monitoring Network catch data
- `conservation_authorities.py` — Credit Valley CA, TRCA, Conservation Halton, etc.
