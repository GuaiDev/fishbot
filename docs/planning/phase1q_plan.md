# Phase 1q — Ontario Surficial Geology (Substrate Type)

**Source:** Ontario Geological Survey MRD 128-REV — Surficial Geology of Southern Ontario
**Scale:** 1:50,000 | **Coverage:** Southern Ontario only | **Updated:** 2010 (stable)
**Agent value:** Substrate class (coarse/fine/bedrock/organic) constrains habitat suitability for
substrate-sensitive species (redhorse, darters, madtoms) independent of community observations.

---

## Data access

The GeologyOntario portal (`geologyontario.mines.gov.on.ca`) serves a JavaScript SPA that blocks
curl on all paths. However, the underlying polygon tile files are directly accessible:

- **Tile index KML:** `http://www.geologyontario.mndm.gov.on.ca/mines/data/google/mrd128/polygons/doc.kml`
  — lists 92 tiles as `<NetworkLink>` elements, each with a bounding box and relative `.kmz` href.
- **Tile KMZs:** `http://www.geologyontario.mndm.gov.on.ca/mines/data/google/mrd128/polygons/files/{name}.kmz`
  — ZIP archives containing `doc.kml` with actual polygon geometries and attribute Placemarks.
- **No authentication required.** Both URLs confirmed HTTP 200 with real data.

Each tile KMZ contains KML Placemarks where:
- `<name>` encodes unit code + name: `"7 Glaciofluvial deposits"`, `"8a Fine-textured glaciolacustrine deposits"`
- `<description>` encodes primary material: `"sand and gravel, minor silt, clay and till"`
- `<Polygon>` / `<MultiGeometry>` contains actual coordinate rings

---

## Classification → substrate mapping

Confirmed unit codes from three sampled tiles (SW Ontario, GTA, Shield boundary):

| Codes | Geological type | Substrate class |
|-------|----------------|-----------------|
| 1, 3 | Bedrock (Precambrian / Paleozoic) | `bedrock` |
| 2, 4 | Bedrock-drift complex | `bedrock` |
| 5a, 5b, 5c, 5e | Till (Precambrian / Paleozoic terrain) | `mixed` |
| 5d | Till (derived from lacustrine / shale) | `fine` |
| 6, 6a, 7 | Ice-contact stratified / glaciofluvial outwash | `coarse` |
| 8a, 8b | Fine glaciolacustrine (silt, clay) | `fine` |
| 9, 9a, 9b, 9c | Coarse glaciolacustrine (sand, gravel) | `coarse` |
| 12, 14b | Post-glacial lacustrine / older alluvial | `mixed` |
| 19 | Modern alluvial (floodplain) | `mixed` |
| 20 | Organic (peat, muck, marl) | `organic` |
| 21 | Man-made (fill, landfill) | skip |

Unit code is parsed from the leading token in `<name>` (everything before the first space).
Primary material is parsed from `<description>` after stripping HTML tags.

---

## Implementation checklist

### Step 1 — Pydantic model
- [ ] Create `src/models/geology_unit.py` with `GeologyUnit(BaseModel)`:
  - `unit_id: str` — composite key: `f"{tile_id}_{seq:04d}"`
  - `tile_id: str` — e.g., `"-79.5_43.5_-79_44"`
  - `unit_code: str` — e.g., `"7"`, `"8a"`, `"9c"`
  - `unit_name: str` — full geological name
  - `primary_material: str | None`
  - `substrate_class: str` — `"coarse" | "fine" | "bedrock" | "organic" | "mixed"`
  - `jurisdiction: str = "CA-ON"`
  - `polygon_wkt: str` — WKT polygon geometry for Shapely point-in-polygon
  - `bbox_minx: float`, `bbox_miny: float`, `bbox_maxx: float`, `bbox_maxy: float`

### Step 2 — Ingest module
- [ ] Create `src/ingest/jurisdictions/ca_on/geology.py`:
  - Constants: `_TILE_INDEX_URL`, `_TILE_BASE_URL`, `_TILE_DIR = Path("data/raw/mrd128_tiles/")`, `_TTL = 30 * 86400`
  - `_classify_substrate(unit_code: str) -> str` — lookup table mapping unit codes to the four classes; default `"mixed"` for unknowns
  - `_parse_wkt(placemark_el) -> str | None` — extract `<Polygon>` or `<MultiGeometry>` coords and convert to WKT; skip points/lines
  - `_parse_tile(kmz_path: Path, tile_id: str) -> list[GeologyUnit]` — unzip KMZ with `zipfile`, parse `doc.kml`, yield one `GeologyUnit` per valid polygon Placemark
  - `download_tile_index() -> list[tuple[str, tuple, str]]` — fetch index KML, parse `<NetworkLink>` elements, return `[(tile_id, (west, south, east, north), kmz_filename)]`
  - `download_tile(tile_id: str, kmz_filename: str) -> Path` — TTL-cached download to `_TILE_DIR/{tile_id}.kmz`
  - `load_geology() -> list[GeologyUnit]` — orchestrates tile index download + all tile downloads + parsing; logs progress per tile
  - Add `uv add shapely` for point-in-polygon queries at the storage layer

### Step 3 — Storage
- [ ] Create `src/storage/geology.py`:
  - `upsert_geology_units(db, units: list[GeologyUnit])` — upsert by `unit_id`; store `polygon_wkt` and bbox columns
  - `query_substrate_at_point(db, lat: float, lng: float) -> GeologyUnit | None` — bbox pre-filter (`bbox_minx <= lng <= bbox_maxx AND bbox_miny <= lat <= bbox_maxy`), then Shapely `Point(lng, lat).within(shape)` on candidates; return first match
  - `query_substrate_area(db, lat: float, lng: float, radius_km: float) -> list[GeologyUnit]` — expand bbox by radius, collect candidates, Shapely filter; returns list of intersecting units

### Step 4 — Service and agent tool
- [ ] Create `src/services/geology.py`:
  - `ingest_geology_data() -> int` — calls `load_geology()`, upserts, returns count
  - `get_substrate_for_agent(lat: float, lng: float, radius_km: float = 10) -> str` — returns JSON:
    ```json
    {
      "query": {"lat": 43.5, "lng": -79.5, "radius_km": 10},
      "substrate_at_point": {"unit_code": "7", "unit_name": "Glaciofluvial deposits", "substrate_class": "coarse", "primary_material": "sand and gravel"},
      "nearby_units": [...],
      "substrate_summary": {"dominant_class": "coarse", "classes_present": ["coarse", "mixed"]},
      "habitat_note": "...",
      "data_caveat": "Southern Ontario coverage only (1:50,000). Substrate class indicates valley fill type — not stream channel substrate directly. Glaciofluvial / coarse units strongly predict gravel/cobble stream beds."
    }
    ```
  - `_substrate_habitat_note(substrate_class: str) -> str` — short ecological implication per class

### Step 5 — Agent integration
- [ ] Add `get_substrate_for_agent` to `src/services/geology.py`
- [ ] Add `get_substrate` tool definition in `src/agent/chat.py` `_tools()` list with `lat`, `lng`, `radius_km` params
- [ ] Add `get_substrate` handler in `_execute_tool()`
- [ ] Tool description must note: southern Ontario only; substrate class is land surface geology, not confirmed channel substrate; combine with benthic EPT data for stronger habitat inference

### Step 6 — CLI integration
- [ ] Add `ingest_geology_data()` call in `src/cli/main.py` `ingest` command
- [ ] Add `| Geology units: {geology_count}` to the summary line

### Step 7 — Tests and fixtures
- [ ] Save one real tile KMZ as `tests/fixtures/mrd128_tile_sample.kmz` (use `-83.5_42_-83_42.5.kmz` — 74 KB, already downloaded during research)
- [ ] Create `tests/test_ingest_geology.py`:
  - `test_classify_substrate_coarse` — unit `"7"` → `"coarse"`, `"6a"` → `"coarse"`
  - `test_classify_substrate_fine` — unit `"8a"` → `"fine"`, `"5d"` → `"fine"`
  - `test_classify_substrate_bedrock` — unit `"1"` → `"bedrock"`, `"3"` → `"bedrock"`
  - `test_classify_substrate_organic` — unit `"20"` → `"organic"`
  - `test_classify_substrate_skip_manmade` — unit `"21"` returns nothing or is excluded
  - `test_parse_tile_unit_codes` — fixture tile yields expected unit codes (5d, 8a, 9c, 14b, 19, 20, 21)
  - `test_parse_tile_polygon_wkt` — all returned units have non-empty `polygon_wkt`
  - `test_parse_tile_bbox` — all returned units have valid bbox with minx < maxx, miny < maxy
  - `test_geology_unit_model_valid` — model instantiation with required fields
  - `test_geology_unit_optional_material` — `primary_material=None` is valid

### Step 8 — Lint, test, commit
- [ ] `uv add shapely`
- [ ] `make test --timeout=60` (tile parsing may be slow for 92 tiles; fixture test should be fast)
- [ ] `make lint`
- [ ] Commit: `feat(phase-1q): Ontario surficial geology substrate layer — MRD128 tile aggregator`
- [ ] Update `project_phase1_progress.md` memory to mark 1q done

---

## Design notes

**Why tile aggregator over manual shapefile download:**
The 92 polygon tile KMZs are directly HTTP-accessible and small (74 KB – 3.9 MB each). A tile
aggregator is fully automated and fits the "every external API call goes through cache" rule.
The JS-gated ZIP (shapefile) requires human interaction and loses the automation property.

**Why Shapely over bbox-only queries:**
Geology polygons are large and irregular. A bounding box match at tile resolution (0.5° × 0.5°)
is too coarse — a single tile often contains 10–20 distinct units. Point-in-polygon with Shapely
costs microseconds per record and avoids misclassifying a location on the edge of a fine-clay
lacustrine plain as "coarse" because the coarse glaciofluvial unit's bbox overlaps.

**Southern Ontario limitation:**
MRD 128 covers southern Ontario only. For queries north of ~46°N (Shield margin), return a
`"no_data"` substrate class with a note. EDS 014 (province-wide, 1:1M) exists but is too
coarse for point queries — do not attempt to supplement with it.

**Habitat implication framing (matches CLAUDE.md core principle):**
Substrate class constrains species plausibility — it does not confirm presence.
A coarse (glaciofluvial) substrate means a gravel/cobble stream bed is likely, which is
necessary but not sufficient for species like river redhorse or blackside darter.
Combine with benthic EPT (1p) and water quality (1o) for layered habitat assessment.
