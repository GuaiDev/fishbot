# Nova Scotia (CA-NS)
#
# Covered by federal/global sources — no province-specific adapters required:
#   iNaturalist, GBIF, WSC gauges, OSM, eBird    → src/ingest/global/
#   CABIN benthic (all provinces)                 → src/ingest/jurisdictions/ca_on/benthic.py
#   DataStream water quality (Atlantic Canada)    → src/ingest/jurisdictions/ca_national/datastream_water_quality.py
#   DFO SAR critical habitat                      → src/ingest/jurisdictions/ca_national/dfo_critical_habitat.py
#   CHS tidal predictions                         → src/ingest/jurisdictions/ca_national/tidal.py
#
# Build province-specific adapters when these become available:
#   Stream network: NS NSDNR hydrography (not publicly queryable as of 2026)
#   Fish observations: NS Inland Fisheries Division (internal, no public API)
#   Stocking: NS Fisheries Branch — no bulk public data found
#   Regulations: https://novascotia.ca/fish (DFO federal regulations apply + provincial supplement)
