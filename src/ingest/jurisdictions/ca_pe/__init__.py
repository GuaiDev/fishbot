# Prince Edward Island (CA-PE)
#
# Covered by federal/global sources — no province-specific adapters required:
#   iNaturalist, GBIF, WSC gauges, OSM, eBird    → src/ingest/global/
#   CABIN benthic (all provinces)                 → src/ingest/jurisdictions/ca_on/benthic.py
#   DataStream water quality (Atlantic Canada)    → src/ingest/jurisdictions/ca_national/datastream_water_quality.py
#   DFO SAR critical habitat                      → src/ingest/jurisdictions/ca_national/dfo_critical_habitat.py
#   CHS tidal predictions (coastal)               → src/ingest/jurisdictions/ca_national/tidal.py
#
# Build province-specific adapters when these become available:
#   Stream network: PEI streams are small; OSM coverage is reasonable
#   Fish observations: PEI Agriculture & Fisheries (internal, no public API)
#   Stocking: PEI Fisheries Branch — no bulk public data found
#   Regulations: DFO federal regulations apply — https://www.dfo-mpo.gc.ca/fisheries-peches/regs/index-eng.html
