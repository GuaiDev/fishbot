# Saskatchewan (CA-SK)
#
# Covered by federal/global sources — no province-specific adapters required:
#   iNaturalist, GBIF, WSC gauges, OSM, eBird    → src/ingest/global/
#   CABIN benthic (all provinces)                 → src/ingest/jurisdictions/ca_on/benthic.py
#   DataStream water quality                      → src/ingest/jurisdictions/ca_national/datastream_water_quality.py
#   DFO SAR critical habitat                      → src/ingest/jurisdictions/ca_national/dfo_critical_habitat.py
#
# Build province-specific adapters when these become available:
#   Stream network: SaskWater hydrology (not publicly queryable as of 2026)
#   Fish observations: SK Fish and Wildlife (internal, no public API)
#   Stocking: SK Fisheries Branch — no bulk public data found
#   Regulations: https://www.saskatchewan.ca/residents/environment-public-health-and-safety/fish-and-wildlife/fish/fishing-regulations (PDF)
