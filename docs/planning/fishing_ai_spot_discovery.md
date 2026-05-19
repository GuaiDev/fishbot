# Fishing AI Bot — Satellite Spot Discovery Roadmap

Third addendum. Adds automated discovery of fishable water bodies from satellite imagery, with accessibility filtering. Pairs directly with the hydrological network analysis in Addendum 2 — discovery finds the candidate spots, hydrology tells you what's likely to live there.

---

## The Right Mental Model

There are three problems here, often conflated:

1. **Finding water bodies** in imagery — easy, well-solved, free tools exist
2. **Classifying what kind of water body** (creek, pond, quarry, stormwater) — moderate
3. **Determining accessibility** — the actual hard problem

Most of your effort goes into #3. The CV is the easy part.

---

## 1. Imagery Sources (Free, Legal, Better Than Google for Your Use Case)

| Source | Resolution | Coverage | Notes |
|---|---|---|---|
| **SWOOP** (South Western Ontario Orthophotography Project) | **15–20 cm** | Most of Southern Ontario including GTA | Free for public use. Higher resolution than Google in many rural areas. Updated every 4–5 years. This is your primary source. |
| **NRVIS / Ontario Imagery** | 30 cm – 1 m | Rest of Ontario | Less frequent updates outside SWOOP region |
| **Sentinel-2** (ESA Copernicus) | 10 m | Global, refreshed every 5 days | Lower res but ideal for spotting change over time |
| **Landsat 8/9** | 30 m | Global, 16-day refresh | For long-term water body persistence analysis |
| **Microsoft Planetary Computer** | Various | Hosts Sentinel/Landsat + compute environment | Free for non-commercial research |
| **Google Earth Engine** | Various | Hosts everything, runs at scale | Free tier generous for personal use; Python API excellent |

**Crucially: do NOT run CV on Google Maps satellite tiles.** Their ToS prohibits it. Use Google tiles as a *display* layer in your UI (via their JS API), but run analysis on the open imagery above.

---

## 2. Water Body Detection Pipeline

This is the well-trodden part. Multiple approaches, increasing in sophistication:

### Approach A: Spectral indices (good baseline, fast)

For multispectral imagery (Sentinel-2), compute NDWI or MNDWI:

```
NDWI = (Green - NIR) / (Green + NIR)
MNDWI = (Green - SWIR) / (Green + SWIR)   ← better in urban areas
```

Threshold at ~0 to get a water mask. Five lines of code in `rasterio` + `numpy`. Catches anything wet larger than ~20m².

### Approach B: Pre-built water datasets (don't reinvent)

- **JRC Global Surface Water Dataset** — every water body on Earth, with seasonality (always-wet vs. seasonal). Hosted on Google Earth Engine.
- **Dynamic World** (Google + WRI) — near-real-time land cover including water at 10m, updated continuously.
- **OpenStreetMap** — manually-tagged water features. Surprisingly complete in populated areas. Pull via Overpass API.

For your initial dataset: union of OSM water features + JRC water + Dynamic World water. Gets you ~95% of water bodies in Ontario without writing any CV code.

### Approach C: High-res segmentation (for the small/hidden stuff)

For finding things that don't show up in coarser datasets — culvert outlets, small farm ponds, tucked-away quarries on SWOOP imagery:

- **Segment Anything Model (SAM)** by Meta — point at suspected water in high-res imagery, it produces a clean polygon. Works zero-shot.
- **Roboflow** has fine-tuned aerial segmentation models you can use off-the-shelf.
- For custom training: U-Net on labeled SWOOP tiles. Few hundred labels gets you serviceable results. Use QGIS to label.

### Special-case classifiers

Once you have a water polygon, classify it:

| Type | Distinguishing features |
|---|---|
| **Stream / creek** | Linear, narrow (<10m), shows flow direction in hydro data |
| **Pond** | Roughly oval, <2 hectares, single basin |
| **Lake** | Larger, often irregular shoreline |
| **Stormwater pond** | Geometric shape (round/oval), near subdivisions, often paired in series, recent construction in historical imagery |
| **Abandoned quarry** | Steep banks (visible in DEM!), rectangular or stepped edges, often deeper than surroundings, no inflow/outflow streams |
| **Active quarry** | Same shape signals + visible heavy equipment, road network, processing infrastructure |
| **Reservoir** | Has a dam at one end (visible linear structure perpendicular to former stream channel) |
| **Farm pond** | Small, near agricultural land, often square-ish, single house nearby |

A simple decision tree on `(area, perimeter/area ratio, nearby buildings, near road, elevation variation in 100m buffer, OSM tags)` will classify most of these correctly. Save the ML for ambiguous cases.

---

## 3. Detecting Dams, Spillways, and Hidden Infrastructure

Harder because these are linear features, often partly obscured, and not always in open datasets.

### Known dams (start here)
- **Canadian Dam Association inventory** — major dams only
- **DFO Aquatic Barriers Database** — fish-passage focused, very useful
- **Ontario MNRF dams layer** — comprehensive for the province
- **NHN (National Hydro Network)** — includes dam features in some areas

### Finding unmapped barriers (the real hunting)

A barrier shows up as a **discontinuity in stream characteristics**:

1. Take the stream network from Addendum 2
2. Walk along each stream segment in high-res imagery
3. Look for: linear features perpendicular to flow, abrupt water-surface-elevation change in the DEM, persistent water upstream that ends abruptly, parking/access infrastructure adjacent
4. Old mill dams in Southern Ontario are extremely common (the area was full of grist mills in the 1800s) and many appear as ruined linear stone features

Could train a binary classifier on labeled dam locations vs. random stream points using DEM-derived features. Or just visually triage candidates flagged by the algorithm — much faster than scanning manually.

### The fish-passage angle

For each barrier you find, the question isn't just "is there a dam" but "can fish pass it?" Apply rules: vertical drop > 0.5m = blocked for most species, 0.3–0.5m = blocked for smaller fish, fishway present = passable. Annotate the stream graph from Addendum 2 accordingly.

---

## 4. The Accessibility Problem (The Actually Hard Part)

You correctly identified this as the real barrier. Here's a framework.

### Data sources for access classification

| Data | Why it matters | Source |
|---|---|---|
| **Microsoft Building Footprints — Canada** | ML-derived footprints of every building in Canada. **Free.** Critical for detecting "homes nearby." | github.com/microsoft/CanadianBuildingFootprints |
| **OpenStreetMap** | Roads, trails, parking, gates, "private" tags, boat launches | Overpass API |
| **Crown Land Use Policy Atlas** | What land is public Crown land in Ontario | Ontario GeoHub |
| **Conservation Authority boundaries** | Credit Valley CA, TRCA, Halton, etc. — usually allow fishing | Each CA publishes their own; aggregated on GeoHub |
| **Provincial Parks + Conservation Reserves** | Public access (with fishing permitted in most) | Ontario GeoHub |
| **Municipal parks** | Most cities publish their park boundaries as GIS | Open data portals |
| **MNRF Public Access Points** | Where MNRF has formally established boat launches / shore access | Ontario GeoHub |
| **Ontario Parcel Assessment data** | Property boundaries + use codes (residential, agricultural, institutional). Licensing is restricted but municipal versions and aggregations exist | MPAC, varies |
| **DFO Tidal/Navigable Waters list** | Federally protected navigation rights apply on listed waters — this is legally significant | DFO |

### The accessibility scoring framework

For each candidate water body, compute features in a buffer around it (say 50m and 200m):

**Hard exclusions (drops score to near-zero):**
- Building footprint within 50m of shoreline (likely private residence/cottage)
- Inside marked "no trespassing" zone in OSM
- Active industrial use (visible equipment, fenced quarries)
- Inside designated First Nations reserve (separate jurisdiction; respect this absolutely)

**Strong positive signals:**
- Overlaps Conservation Authority land
- Overlaps Provincial Park / Conservation Reserve
- Overlaps Crown Land
- Overlaps municipal park
- Has MNRF-designated access point
- OSM `leisure=fishing` tag exists

**Moderate positive signals:**
- Public road within 200m with no buildings between road and water
- OSM trail terminates near water
- Visible parking area adjacent in imagery
- Listed in DFO Navigable Waters

**Ambiguous (yellow flag, need manual check):**
- Rural setting with no buildings nearby but no public land designation
- Farmland surrounding (legally needs permission, but sometimes granted)
- Linear easement features visible (sometimes utility ROW = de facto walking access)

**Composite score:**

```
access_score = base
             - 100 × (has_building_within_50m)
             - 30 × (has_building_within_200m)
             + 50 × (on_conservation_authority_land)
             + 50 × (on_crown_land)
             + 40 × (municipal_park)
             + 30 × (has_mnrf_access_point)
             + 20 × (road_within_200m_no_buildings_between)
             + 15 × (osm_trail_terminates_near)
             [...]
```

Output as a 0–100 score with the contributing factors enumerated, so you can see *why* something scored what it did.

### The "walk through fields" case

You called this out specifically — sometimes you park on a public road and walk 500m through ambiguous land to reach a spot. Real-world legal status here:

- **Walking on the road right-of-way** (the strip from the pavement to the property line, often 5–10m) is generally legal even past private property
- **Walking down a utility easement** depends on the easement terms but often allowed
- **Crossing private agricultural land** requires permission — even if unfenced, even if no signs
- **Walking along a natural watercourse** has been argued under common-law navigability rights for some waters, but this is legally contested and varies by waterbody

What the bot can flag, vs. what only you can decide: the bot should output the access geometry (road frontage length, distance from nearest legal public point, intervening parcels). You make the call on whether to ask permission, walk a road right-of-way, or skip it.

### A practical UI for accessibility

When the user clicks a candidate spot, show:

> **Sixteen Mile Creek tributary — 2.3 km north of Hwy 5**
> 
> **Access score: 64/100 — likely accessible with effort**
> 
> ✓ No buildings within 200m
> ✓ Conservation Halton land covers eastern shore
> ✗ Western shore appears to be private agricultural parcel
> ! 350m walk from nearest public road (Steeles Ave W)
> ! No designated trail; route crosses Conservation Authority land
> 
> **Confidence: medium.** Verify on satellite and consider contacting Conservation Halton.

---

## 5. The Discovery Pipeline End-to-End

Putting it all together:

```
1. TILE THE REGION
   Break target area (e.g., GTA + 50km) into ~1km² tiles

2. FIND WATER
   For each tile: union of OSM water + JRC + Dynamic World + 
   high-res segmentation on SWOOP for tiles flagged as 
   "potentially missed features"

3. POLYGONIZE & DEDUPE
   Convert to clean polygons. Merge fragments. 
   Filter out anything <100m² (puddles).

4. CLASSIFY
   Decision tree → creek / pond / quarry / stormwater / reservoir / etc.

5. SCORE ACCESSIBILITY
   Apply framework from Section 4. Compute features in 50m and 
   200m buffers.

6. CROSS-REFERENCE WITH HYDROLOGY (Addendum 2)
   Connect water bodies to the stream network graph. 
   Determine if upstream of confirmed catch locations or 
   downstream of stocking points.

7. PREDICT SPECIES
   Run habitat suitability model from Addendum 2.

8. RANK
   final_score = species_probability × untapped_index × access_score
```

Output: a ranked list of candidate spots with predicted species, access details, and a one-tap "show me on the map" link.

---

## 6. Tools to Use

| Task | Tool |
|---|---|
| Imagery + planetary-scale compute | **Google Earth Engine** (Python API) |
| Local raster work | `rasterio`, `rioxarray`, `xarray` |
| Vector / GIS | `geopandas`, `shapely`, `pyproj` |
| Stream/road networks | `networkx`, `osmnx` |
| Segmentation | `segment-anything`, `torch`, optionally fine-tune via `lightning` |
| OSM data | `osmium`, `pyrosm`, Overpass API |
| Map display | Leaflet + Google Maps tiles for users; QGIS for development |
| Tile management | `mercantile`, `morecantile` |
| Visualization in CLI | `folium` for quick map inspection |

---

## 7. Realistic Phasing

**Don't try to scan all of Ontario.** Start with one region you'd realistically fish.

| Phase | Time | What you get |
|---|---|---|
| 7a — OSM + JRC water union for GTA | 1 day | A baseline map of every known water body in the region |
| 7b — Microsoft building footprints + basic access scoring | 2 days | First-cut accessibility filter; eliminates the obvious private spots |
| 7c — Public land overlays | 2 days | Conservation areas, parks, Crown land integrated |
| 7d — Classification rules | 3 days | Stormwater pond vs. pond vs. quarry vs. creek separation |
| 7e — Cross-reference with Addendum 2 hydrology | 2 days | Stream connectivity + species predictions per candidate |
| 7f — High-res SWOOP segmentation for missed spots | 1–2 weeks | Find the truly hidden stuff — the small farm ponds and abandoned quarries that don't show up in coarse datasets |
| 7g — Barrier/dam detection on stream network | 1 week | Annotates the stream graph with fish-passage info |
| 7h — UI: map view with ranked candidates + filtering | 1 week | The thing you'd actually use |

**Roughly 5–7 weeks of evening/weekend work to a usable tool covering Southern Ontario.**

---

## 8. Ethics Note (Same as Before, Different Domain)

A tool that automatically reveals every quiet farm pond in the GTA could get those spots over-fished within a season. Two ways to handle this:

1. **Personal use only** — never publish raw discovery output. Use it to find your own spots. Aggregate trip outcomes with privacy preserved.
2. **If you do publish:** show *types* of opportunity (e.g., "there are 12 high-potential stormwater ponds within 20km of you") without exact pins, requiring the user to do their own scouting. This preserves the discovery work as a moat while not commodifying anyone's local secrets.

Your call, but worth deciding before the tool gets good enough to matter.

---

## 9. One More Idea: Temporal Analysis

Sentinel-2 refreshes every 5 days. Over time you can detect:

- **Stocking events** — sudden water-surface activity, vehicles at access points around known stocking dates
- **Seasonal water bodies** — vernal pools that dry up are useless for fishing but flag adjacent permanent waters
- **Algal blooms** — green-shift in NIR bands; affects fishability
- **Water level changes** — reservoirs drawn down (worst time to fish) vs. recently filled (often great)
- **New developments** — new stormwater ponds appearing as subdivisions go in. These are usually stocked with bass within a year or two.

A weekly cron job comparing the current Sentinel-2 tile against the previous month's median surfaces all of this. Goes in the continuous-improvement pipeline from Addendum 2.

---

## Order of Attack (Updated Overall)

Bringing all three addenda together, this is what I'd build, in order:

1. **Base CLI bot** (original roadmap, Phase 1–3)
2. **Hydrological network analysis on one watershed** (Addendum 2, Section 1)
3. **OSM + JRC water union + Microsoft building footprints + basic accessibility scoring** (this doc, Phase 7a–c)
4. **Species prediction model on stream segments** (Addendum 2, Section 5)
5. **Discovery pipeline cross-referenced with predictions** (this doc, Phase 7e)
6. **Map UI** (original roadmap Phase 5 + this doc Phase 7h)
7. Everything else

Steps 2–5 are where the magic compounds: stream graph + access filter + species model + discovery = "here are 40 water bodies near you you've never heard of, ranked by predicted brook trout probability and ease of access." Nothing else on the market does that.
