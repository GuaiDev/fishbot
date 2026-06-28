# Manitoba (CA-MB)
#
# Covered by federal/global sources — no province-specific adapters required:
#   iNaturalist, GBIF, WSC gauges, OSM, eBird    → src/ingest/global/
#   CABIN benthic (all provinces)                 → src/ingest/jurisdictions/ca_on/benthic.py
#   DataStream water quality (Lake Winnipeg basin)→ src/ingest/jurisdictions/ca_national/datastream_water_quality.py
#   DFO SAR critical habitat                      → src/ingest/jurisdictions/ca_national/dfo_critical_habitat.py
#
# Build province-specific adapters when these become available:
#   Stream network: Manitoba Water Stewardship hydrography (not publicly queryable as of 2026)
#   Fish observations: Manitoba Wildlife Atlas (internal database, no public API)
#   Stocking: no bulk public data found
#   Regulations: https://www.gov.mb.ca/sd/fish_and_wildlife/fishing/index.html (PDF)
