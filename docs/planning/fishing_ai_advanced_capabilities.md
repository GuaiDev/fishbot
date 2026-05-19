# Fishing AI Bot — Advanced Capabilities Roadmap

Addendum to the base roadmap. These are Phase 8+ capabilities — only attempt after Phases 1–5 are solid. Each section is rated by **complexity** (1–5) and **legal risk** (low/medium/high).

---

## 1. The Big Idea: Hydrological Network Analysis

**Complexity: 4/5 · Legal risk: low · Originality: high**

This is the most interesting capability you mentioned and probably the one to lead with. The intuition is correct: if 16 Mile Creek has confirmed brook trout populations and an unbarriered tributary branches off with similar habitat, that tributary almost certainly holds fish too — even if zero reports exist. Fisheries biologists model this routinely. Consumer fishing apps don't.

### The data you need (all free, all legal)

| Dataset | What it gives you | Source |
|---|---|---|
| **Ontario Hydro Network (OHN)** | Every stream, river, lake as a connected GIS network with flow direction | Ontario GeoHub (open data) |
| **Ontario Aquatic Resource Areas** | Polygon hydrology for analysis | Ontario GeoHub |
| **MNRF Barrier Datasets** | Dams, culverts, waterfalls — anywhere fish movement stops | Ontario GeoHub + Fisheries and Oceans Canada |
| **SOLRIS Land Cover** | Forest cover, urbanization, agriculture along streams | Ontario GeoHub |
| **Provincial DEM (Digital Elevation Model)** | Gradient — critical for cold-water species | Ontario GeoHub |
| **Stream temperature models** | Where it's cold enough for trout | Some published in academic literature; can derive from canopy + gradient |
| **Aquatic Habitat Inventory** | Substrate, riparian zone where surveyed | Ontario GeoHub |

### How the analysis works

1. **Build a stream graph.** Load OHN into Python with `geopandas` + `networkx`. Each stream segment is an edge; junctions are nodes. Add flow direction so you can ask "what's upstream/downstream of point X?"
2. **Add barriers.** Mark edges as impassable where dams/culverts/falls exist. Now you have a connectivity-aware graph.
3. **Seed with known data.** Tag stream segments where you have confirmed catches (your trip log, iNaturalist, MNRF stocking records, scientific surveys).
4. **Compute habitat similarity.** For each unsurveyed segment, compute features: gradient, canopy cover, upstream watershed area, distance to main stem, temperature proxy. Build a feature vector.
5. **Predict.** For a given species (say, brook trout), train a simple classifier (random forest or even logistic regression — you don't need fancy ML here) on segments with known presence/absence. Apply to unsurveyed segments. Output: probability of presence.
6. **Rank "untapped potential":** `score = predicted_presence_probability × (1 / report_density) × accessibility`. High predicted presence + low community reporting + reachable = your honey hole.

### Concrete example for 16 Mile Creek

The system would do something like:
- Identify all 16 Mile tributaries upstream of the QEW
- Filter to those without dam barriers
- Match gradient and forest cover against segments where brook trout have been documented
- Cross-reference against iNaturalist density (low reporting = unfished)
- Output: "Tributary X off Sixteen Mile near Limehouse Conservation Area: 78% predicted brook trout habitat, zero recent reports, public land access via [trail]"

### Tools to use

- **Python:** `geopandas`, `shapely`, `networkx`, `rasterio` (for the DEM), `scikit-learn` (for the classifier)
- **Database:** PostGIS for serious spatial queries; SQLite + SpatiaLite to start
- **Visualization:** QGIS for development, Leaflet/Mapbox for the user-facing app
- **R alternative:** the `riverdist` and `SSN2` packages are excellent if you'd rather work in R

### Realistic timeline
Two to three weeks for a working prototype focused on one watershed (say, the entire Credit River + 16 Mile system). Most of that is wrangling GIS data formats, not modeling.

---

## 2. YouTube Video Location Inference

**Complexity: 3/5 · Legal risk: low (analytical use) · Reliability: medium**

Realistic version: not "give me the GPS coordinates," but "given this video, narrow down the watershed."

### The pipeline

1. **Cheap signals first.** Video description, title, channel "About" page, pinned comments, hashtags, video chapters. These mention location far more often than you'd think.
2. **Transcript mining.** `youtube-transcript-api` is free. Pass transcripts to Claude with a prompt like *"Extract any place names, waterbody names, road names, or geographic references. Output JSON."*
3. **Frame sampling.** Pull 5–10 frames using `yt-dlp` and `ffmpeg`. Feed to Claude with vision: *"Describe any visible landmarks, signage, bridges, distinctive shoreline features, vegetation type, or anything that could indicate a specific geographic region."*
4. **Cross-reference.** Take the candidates from steps 1–3 and verify on satellite imagery. Claude can compare a frame's shoreline against satellite tiles for proposed locations.
5. **Confidence scoring.** Output a region/watershed with a confidence, not a pin. Be honest when the answer is "somewhere in southern Ontario, can't narrow further."

### Hard limits to set in your code
- **Never publish locations with high confidence** — keep this as personal analysis only. Even private use creates ethical weight; treat it like fishing-spot OSINT.
- **Respect explicit "I'm not sharing this spot" statements** from the creator. The bot should detect and honor these.
- **Don't aggregate one creator's videos to triangulate their secret patterns.** That's the line between "research" and "stalking."

Better use of the same tech: point it at your *own* old GoPro fishing footage to auto-tag your trip log. Same vision pipeline, no ethical issues.

---

## 3. Third-Party Fishing App Data

**Complexity: 1/5 (the legal version) · Legal risk: high (the scraping version)**

### What you cannot do
- Scrape **FishBrain, FishAngler, Anglr, ReelSonar/Deeper apps**. All explicitly prohibit scraping in ToS. FishBrain in particular blocks scrapers aggressively and has acted legally against them. Even if you succeeded technically, building product on scraped data means one C&D letter destroys your app.

### What you can do instead

| Source | Why it matters |
|---|---|
| **iNaturalist** | Already in base plan. Worldwide, well-API'd, growing fast. |
| **GBIF (Global Biodiversity Information Facility)** | Aggregates iNaturalist + museum records + academic surveys + government surveys. Single source of truth for species occurrence. Free API. |
| **eBird-style "iAngler"** projects | Some regions have citizen-science angling reports. Ontario has the [Ontario Catch Reporting](https://www.ontario.ca/page/fishing-rules-regulations) for tagged fish. |
| **MNRF Lake Surveys** | Broadscale Monitoring Network — every Ontario lake gets surveyed on rotation. Catch-per-unit-effort by species. **This is the gold standard data and almost nobody uses it.** |
| **Tournament results** | Bassmaster, FLW, regional tournaments publish detailed catch reports including weight and location. Scrapeable from public sites. |
| **Fishing guide reports** | Many guides publish weekly fishing reports on their websites. These are *meant* to be read and shared. Cite them. |
| **Local conservation authority data** | Credit Valley CA, Toronto Region CA, Conservation Halton — they publish stream surveys and stocking reports. |
| **University research datasets** | Trent, Guelph, Waterloo all do fisheries research. Many datasets land in public repositories. |

The MNRF lake survey data alone, properly integrated, is more valuable than what FishBrain offers — it's just less convenient, which is exactly why nobody's bothered.

---

## 4. Continuous Improvement Architecture

**Complexity: 4/5 · Legal risk: low (if you respect rate limits)**

"Continuously scan the internet" is the wrong frame. Continuous polling is expensive, fragile, and gets you rate-limited. What you actually want is **scheduled ingestion + a learning loop**.

### The right architecture

```
┌────────────────────────────────────────────────────┐
│  SCHEDULER (cron / GitHub Actions / Temporal)      │
│  - Daily: weather, conditions, new Reddit/forum    │
│  - Weekly: YouTube channels, guide reports         │
│  - Monthly: gov datasets, stocking updates         │
└────────────────────────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────┐
│  INGESTION WORKERS (one per source)                │
│  - Fetch → deduplicate → normalize → store raw     │
└────────────────────────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────┐
│  PROCESSING (cheap model for triage)               │
│  - Extract: species, location, technique, date     │
│  - Embed for semantic search                       │
│  - Score quality/relevance                         │
└────────────────────────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────┐
│  PREDICTION MODELS                                 │
│  - Habitat suitability (hydrological)              │
│  - Conditions-based bite prediction                │
│  - Retrained weekly on new data                    │
└────────────────────────────────────────────────────┘
                       ↓
┌────────────────────────────────────────────────────┐
│  FEEDBACK LOOP — this is the magic                 │
│  - Bot makes recommendation                        │
│  - User logs trip (worked / didn't)                │
│  - Outcome stored, model adjusts                   │
└────────────────────────────────────────────────────┘
```

### The self-improvement that actually works

True "AI that improves itself" via continuous training is overkill and unstable. The pragmatic version:

1. **Log every prediction the bot makes** with its features and confidence.
2. **Log every trip outcome** from your `/log` command, including whether the bot's suggestion was used.
3. **Weekly retrain** the habitat suitability model on the growing dataset. This is `scikit-learn` calling `.fit()` once a week — not LLM fine-tuning.
4. **A/B test prompts.** Keep two versions of your trip-planner prompt active. Track which produces recommendations you actually followed. Promote the winner.
5. **Embeddings refresh.** As new content lands, re-embed and re-index. The bot's RAG retrieval naturally improves.

This gives you 90% of what "self-improving AI" means in practice, with 10% of the complexity.

### Cost-efficient model routing

- **Triage / extraction:** Claude Haiku (cheap, fast) — pull species and location from a Reddit post
- **Synthesis / recommendations:** Claude Sonnet (your main bot brain)
- **Hard reasoning / planning:** Claude Opus only when needed
- **Embeddings:** `voyage-3` for retrieval quality, or `voyage-3-lite` for cost

Route requests by complexity. A pipeline processing 10,000 Reddit posts a week shouldn't be hitting Opus on every one — Haiku does the work for 1/15th the cost.

---

## 5. Habitat-Based Species Prediction (the ML layer)

**Complexity: 4/5 · Legal risk: low**

Once you have the stream graph from Section 1 and the data from Sections 3/4, you can build a real Species Distribution Model.

### Features per stream segment / lake
- Physical: gradient, depth, area, watershed size, elevation
- Connectivity: distance to nearest barrier upstream and downstream, network position
- Climate: mean annual air temp, summer max, modeled water temp
- Land cover: % forest, % agriculture, % urban in watershed
- Biological: confirmed presence of competitor/prey species
- Anthropogenic: stocking history, fishing pressure proxy (reports per km)

### Model choices
- **Start with:** random forest classifier per species. Outputs probability of presence. Interpretable via feature importance — you can ask "why does the model think there's brook trout here?" and get an answer.
- **Upgrade path:** gradient-boosted trees (`xgboost` / `lightgbm`) for marginally better accuracy.
- **Don't bother with deep learning** here. The data volume doesn't justify it and you lose interpretability.

### The killer output
For any point on the map the user clicks, generate a card:

> **Species likelihood (predicted)**
> - Brook trout: 73% (high — cold gradient, forested, no upstream barriers)
> - Brown trout: 45% (moderate — temp may be marginal in summer)
> - Smallmouth bass: 12% (low — gradient too high)
> 
> **Untapped score: 8.2/10**
> Strong habitat match, only 2 community reports in 5 years, public access via Trail X.

That's a feature no consumer fishing app currently ships. And it's defensible because it's grounded in published fisheries science, not stolen catch data.

---

## 6. Realistic Cost Picture at Advanced Scale

Personal use, daily active, all features running:

| Item | Monthly cost |
|---|---|
| Claude API (mixed Haiku/Sonnet) | $25–60 |
| Voyage embeddings | $5–10 |
| Hosting (Supabase Pro + Vercel + worker dyno) | $25–50 |
| YouTube API | free |
| Reddit API | free tier likely sufficient |
| GIS data | free |
| **Total** | **$55–120/month** |

If you ever release publicly, costs scale with users and you'd want auth + per-user rate limits before that point.

---

## Order of Attack

Don't try to do all of this at once. Suggested order from highest value, lowest risk:

1. **Hydrological network analysis** (Section 1) — most original, no legal risk, real differentiator
2. **MNRF + Conservation Authority data integration** (Section 3) — easy wins, underutilized
3. **Habitat-based SDM** (Section 5) — builds on 1+2, adds the predictive layer
4. **Continuous improvement loop** (Section 4) — once you have enough trip-log data
5. **YouTube extraction** (Section 2) — useful but not core; do it for your own content first

The dirty secret: if you only do Sections 1+3+5, you'll already have a tool that beats every consumer fishing app I'm aware of for the specific use case of *finding new spots in your home watershed*. Volume of catch data was never the moat — interpretation is.
