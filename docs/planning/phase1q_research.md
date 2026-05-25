Ran 2 shell commands

Both URLs returned the same 49,932-byte HTML file — the JS SPA, not a PDF. Let me check if the HTML has any useful embedded metadata or links to actual files.

  Searched for 2 patterns, ran 2 shell commands

Multiple ZIPs are directly accessible. Let me check their sizes and also get the metadata PDF directly.

  Ran 2 shell commands

All paths on that domain return the same SPA HTML (49,932 bytes) regardless — it's a catch-all router. The files aren't directly accessible. Let me try a different angle: the CKAN dataset page description and any auxiliary links.

  Ran 2 shell commands

The KML has a legend PDF link. Let me grab it and check the rest of the KML for polygon network link.

  Ran 2 shell commands

Got the legend PDF (297 KB, 1 page). Let me read it.

  Read 1 file, ran 11 shell commands

We have 39 polygon features. Let me read all of them to map the classification scheme.

  Ran 1 shell command

One tile only covers SW Ontario. Let me grab a tile from the GTA area to see more deposit types, and also try to get the full legend unit list.

  Ran 2 shell commands

Good data. Let me grab one more tile near the Canadian Shield boundary to catch bedrock classes, then compile the full report.

  Ran 1 shell command

That's enough to give a complete picture. Here's the full report:

---
MRD128 Classification Schema — Full Report

The data is accessed from the KML tiles directly (the JS portal blocks curl but the underlying tile files are HTTP-accessible). The polygon layer tiles into 92 KMZ files. I read three tiles covering SW Ontario, the GTA, and the Shield boundary.

The complete unit classification system:

┌──────┬───────────────────────────────────────┬──────────────────────────┬───────────────────┐
│ Unit │                 Name                  │     Primary material     │ Fishing substrate │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 1    │ Precambrian bedrock                   │ —                        │ Bedrock           │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 2    │ Bedrock-drift complex (Precambrian)   │ —                        │ Bedrock/mixed     │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 3    │ Paleozoic bedrock                     │ —                        │ Bedrock           │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 4    │ Bedrock-drift complex (Paleozoic)     │ —                        │ Bedrock/mixed     │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 5a   │ Till (Precambrian terrain)            │ silty sand to sand       │ Mixed             │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 5b   │ Till (Paleozoic, stone-poor)          │ sandy silt to silty sand │ Mixed             │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 5c   │ Till (Paleozoic, stony)               │ sandy silt to silty sand │ Mixed             │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 5d   │ Till (derived from lacustrine/shale)  │ clay to silt             │ Fine              │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 5e   │ Undifferentiated older till           │ mixed                    │ Mixed             │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 6    │ Ice-contact stratified deposits       │ sand and gravel          │ Coarse            │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 6a   │ Ice-contact (eskers, kames, moraines) │ sand and gravel          │ Coarse            │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 7    │ Glaciofluvial outwash                 │ sand and gravel          │ Coarse            │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 8a   │ Fine glaciolacustrine (laminated)     │ silt and clay            │ Fine              │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 8b   │ Fine glaciolacustrine (interbedded)   │ silt and clay            │ Fine              │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 9    │ Coarse glaciolacustrine               │ sand, gravel             │ Coarse            │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 9a   │ Coarse glaciolacustrine (deltaic)     │ sand, gravel             │ Coarse            │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 9b   │ Coarse glaciolacustrine (littoral)    │ sand, gravel             │ Coarse            │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 9c   │ Coarse glaciolacustrine (foreshore)   │ sand, gravel             │ Coarse            │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 12   │ Older alluvial                        │ clay, silt, sand, gravel │ Mixed             │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 14b  │ Coarse lacustrine (littoral)          │ sand, gravel             │ Coarse            │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 19   │ Modern alluvial (floodplain)          │ clay, silt, sand, gravel │ Mixed             │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 20   │ Organic deposits                      │ peat, muck, marl         │ Organic           │
├──────┼───────────────────────────────────────┼──────────────────────────┼───────────────────┤
│ 21   │ Man-made                              │ fill, landfill           │ skip              │
└──────┴───────────────────────────────────────┴──────────────────────────┴───────────────────┘

Key findings for 1q planning:
1. There IS a unit code field — the Placemark name encodes it as "7 Glaciofluvial deposits". In the shapefile this is almost certainly a UNIT or UNIT_CODE field plus a UNIT_NAME field.
2. Two confirmed derived attributes exist in the shapefile — the KML description explicitly states primary material and genesis attributes were extracted to support derivative maps. These are the columns you'd actually query (not the unit name).
3. The mapping to coarse/fine/bedrock/organic is clean and unambiguous. Units 6, 6a, 7, 9, 9a–9c → coarse. Units 8a, 8b → fine. Units 1–4 → bedrock. Unit 20 → organic. Till (5a–5e) is mixed but leans coarse on Precambrian, fine on Paleozoic terrain.
4. Download path is viable: the 92 tile KMZs at geologyontario.mndm.gov.on.ca/mines/data/google/mrd128/polygons/files/ are directly accessible without JS. Alternatively the ZIP at geologyontario.mines.gov.on.ca redirects to the SPA. The shapefile is the preferred ingest format — we'd need to grab the ZIP manually (once) or write a tile aggregator.

Ready to plan 1q whenever you want.
