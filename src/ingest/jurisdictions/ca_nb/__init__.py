# New Brunswick (CA-NB)
#
# Covered by federal/global sources — no province-specific adapters required:
#   iNaturalist, GBIF, WSC gauges, OSM, eBird    → src/ingest/global/
#   CABIN benthic (all provinces)                 → src/ingest/jurisdictions/ca_on/benthic.py
#   DataStream water quality (Atlantic Canada)
#       → src/ingest/jurisdictions/ca_national/datastream_water_quality.py
#   DFO SAR critical habitat
#       → src/ingest/jurisdictions/ca_national/dfo_critical_habitat.py
#   CHS tidal predictions (Miramichi, Saint John) → src/ingest/jurisdictions/ca_national/tidal.py
#
# Build province-specific adapters when these become available:
#   Stream network: NB GNB hydrography (not publicly queryable as of 2026)
#   Fish observations: NB Fish and Wildlife (internal, no public API)
#   Stocking: NB Fisheries Branch — no bulk public data found
#   Regulations: https://www2.gnb.ca/content/dam/gnb/Departments/nr-rn/pdf/en/Fish/Fish.pdf
