# Fishing AI Bot — Complete Feature Catalog

The full list of criteria, data sources, and capabilities to consider. Treat this as a menu — not all of it needs to be built, but knowing the universe of options helps prioritize. Organized roughly by category, with feasibility notes.

Legend: 🟢 easy / cheap, 🟡 moderate effort, 🔴 hard / expensive / ethically tricky, ⭐ high-impact

---

## 1. Water & Physical Environment

### Water temperature ⭐
- Surface temperature drives almost everything in fish behavior
- Each species has preferred temperature ranges; deviation predicts activity
- Sources: 🟢 satellite-derived (Landsat thermal band, MODIS); 🟢 USGS / Water Survey Canada gauges where instrumented; 🟢 crowd-sourced via your trip logs
- Bonus: thermocline depth in summer-stratified lakes (predicts where fish stack)

### Water clarity / turbidity ⭐
- Drives lure color and size selection
- Affects sight-feeding species (bass) vs scent-feeders (catfish) differently
- Sources: 🟢 Sentinel-2 (turbidity from red/NIR ratio); 🟢 stream gauges report turbidity; 🟢 your own Secchi-disk readings logged

### Water level / flow rate ⭐
- Critical for rivers and reservoirs
- Real-time flow data from Water Survey of Canada — free, comprehensive
- Rising water often triggers feeding; crashing water shuts it down
- Sources: 🟢 wateroffice.ec.gc.ca API; reservoir managers publish drawdown schedules

### Dissolved oxygen
- Limits where fish can survive in summer (low DO in deep water during stratification)
- Largely modeled rather than measured; provincial water quality monitoring publishes some
- Sources: 🟡 provincial water quality datasets; modeled from temperature + depth + trophic status

### pH, conductivity, total dissolved solids
- Identify whether a system can support certain species (brook trout intolerant of high TDS, for example)
- Sources: 🟡 Provincial Water Quality Monitoring Network publishes for many sites

### Lake trophic status (oligotrophic / mesotrophic / eutrophic)
- Defines the entire fishery: oligotrophic = trout, eutrophic = bass and panfish
- Often documented in MNRF lake reports
- Sources: 🟢 MNRF lake survey reports; derivable from chlorophyll-a satellite estimates

### Ice in / ice out dates
- For ice fishing season planning
- For spring fishing — first 2 weeks after ice-out is often phenomenal
- Sources: 🟢 historical records published by various agencies; predictable from cumulative degree-days

### Lake turnover prediction
- Spring and fall turnover when stratification breaks: known to scatter fish
- Predictable from surface temperature trajectory
- Sources: 🟢 derive from satellite surface temps over time

### Algal blooms
- Cyanobacterial blooms make fishing terrible and can be dangerous
- Detect from Sentinel-2 chlorophyll index
- Sources: 🟢 Sentinel-2 derived; some agencies publish bloom alerts

### Stream gradient
- Already in Addendum 2; bears repeating — determines species composition
- Sources: 🟢 derived from DEM

### Bottom composition (substrate)
- Where surveyed, MNRF and conservation authorities classify (cobble, gravel, sand, mud, bedrock)
- Drives spawning, invertebrate community, fish holding
- Sources: 🟡 Aquatic Habitat Inventory where available; ⭐ derivable from acoustic data if user has sonar logs

---

## 2. Weather, Atmosphere, and Timing

### Current conditions
- Temperature, wind, cloud cover, precipitation
- Sources: 🟢 Open-Meteo (free, no key); Environment Canada API

### Barometric pressure trend ⭐
- Falling pressure = often great fishing; rising = often slow
- Trend matters more than absolute value
- Sources: 🟢 same weather APIs; just need 24-48hr history

### Wind direction and speed ⭐
- Determines which shore to fish (wind blows food into windward shore)
- Limits accessibility for shore vs boat
- Old angler's rule: "Wind from the west, fishing is best; wind from the east, fishing is least" — partial truth, regional
- Sources: 🟢 weather APIs

### Front passage prediction ⭐
- The 12-24hrs before a front arrives can be epic
- Post-front bluebird sky is famously tough
- Sources: 🟡 derive from pressure trajectory + cloud cover changes

### Precipitation history
- Recent rain affects water clarity, flow, fish position
- Heavy rain → muddy water → fish move to clearer tributaries or hold tight
- Sources: 🟢 weather APIs with history

### Cumulative growing degree days
- Predicts hatch timing for fly fishing
- Predicts spawn timing for bass, walleye, trout
- Sources: 🟢 compute from temperature history

### Moon phase and lunar period ⭐
- Solunar theory — major and minor feeding periods
- Some swear by it, evidence is mixed but real for some species
- Sources: 🟢 astronomical computation, no API needed

### Daylight, civil twilight, sunrise/sunset
- Defines legal fishing hours in some regulations
- Defines prime time windows
- Sources: 🟢 astronomical computation

### Season / day-of-year
- Encoded into all predictions: same lake, same conditions, different month = different fish behavior
- Built into the model rather than a standalone feature

---

## 3. Biology and Ecology

### Spawning calendars by species ⭐
- Pre-spawn aggregation = best fishing of the year for many species
- Spawning species should not be targeted (ethics + sometimes regulations)
- Post-spawn recovery patterns
- Sources: 🟢 species-specific from MNRF literature; published timing windows

### Hatch calendars (for fly fishing)
- When mayflies, caddis, stoneflies emerge on which rivers
- "Match the hatch" — choose fly to imitate
- Sources: 🟡 regional fly shops publish; could crowd-source

### Forage availability
- What baitfish, crayfish, insects are present and what life stage
- Implies lure type and presentation
- Sources: 🟡 MNRF survey data + ecological inference

### Migration patterns
- Spring runs (steelhead, walleye, suckers)
- Fall runs (salmon, brown trout)
- Migration timing by river, often very predictable
- Sources: 🟢 MNRF migration reports; fishing community reports

### Stocking history per waterbody ⭐
- Already in Addendum 2
- Critical for predicting non-native populations (rainbow trout in put-and-take lakes)
- Add: years since last stock (some species persist, some don't)

### Native vs introduced species
- Affects ethical decisions (kill invasives like round goby? release natives?)
- Sources: 🟢 MNRF native range maps

### Predator-prey dynamics
- Where pike are abundant, follow the baitfish schools
- Sources: 🟡 modeled rather than directly observed; correlate species in surveys

### Species at risk
- Don't target. Often legally protected.
- Includes species you might not realize: redside dace, eastern sand darter, lake sturgeon
- Sources: 🟢 federal Species at Risk Act database; provincial SAR list

### Invasive species reporting
- Help track them: round goby, sea lamprey, zebra mussels
- iNaturalist + EDDMapS Ontario integration
- Sources: 🟢 EDDMapS API

---

## 4. Bathymetry & Underwater Structure

The depth chart question deserves its own section.

### Satellite-derived bathymetry ⭐⭐
- Real, established technique. NOAA does it operationally.
- Best results in clear inland waters: most Ontario lakes work
- Stumpf algorithm: log ratio of blue/green Sentinel-2 bands → depth
- Works to ~10-15m in clear water, less in stained water
- Calibrate against any known depths (anglers' sonar reports, published soundings)
- Identifies: shorelines, flats, the inside edge of dropoffs, shallow humps
- Doesn't see: anything below the photic zone, structure under stained water
- Sources: 🟡 Sentinel-2 imagery + custom processing; Python: `eos-sdk` / `pyaqua`

### Existing bathymetric datasets
- 🟢 **MNRF Lake Contour Maps** — many Ontario lakes have been mapped; downloadable as GIS layers or PDFs
- 🟢 **Canadian Hydrographic Service (CHS)** — Great Lakes, major waterways, free vector charts (S-57 format)
- 🟢 **NOAA bathymetric data** — Great Lakes coverage
- 🟢 **GEBCO** — global ocean and large lake bathymetry, free
- 🟡 **iBoating** — has free chart layers viewable but licensing varies

### Crowd-sourced sonar
- 🟡 Navionics SonarChart Live — anglers upload tracks, builds detailed contours over time
- 🔴 No public API. If you own a compatible sonar, you could export your own tracks to GPX/KML and build your personal layer
- ⭐ If you let users upload their sonar logs (GPX from Lowrance, Garmin, Humminbird), you could build a private crowdsourced layer for *your* community

### Dropoff and edge detection ⭐
- The actually-useful output. From bathymetry, compute:
  - Slope at every point (gradient of depth)
  - Identify steep slopes adjacent to flats (classic dropoffs)
  - Identify breaks (where slope changes character)
  - Identify saddles between humps
  - Identify points (peninsulas in the lake bottom)
- These are exactly the spots fish stack
- Sources: 🟢 once you have a depth raster, computational geometry on it

### Bottom hardness inference
- From multi-frequency sonar, hard bottoms reflect differently
- If user uploads sonar logs with structure data, you can map hardness
- Sources: 🟡 user sonar exports; advanced

### Structure overlays
- Submerged timber, weed lines, rock piles
- Some MNRF surveys document; some come from old aerial photos pre-flooding (for reservoirs)
- Sources: 🟡 mostly assembled manually; weed lines visible in satellite imagery

### Wreck and artificial structure databases
- Submerged artificial reefs and fish habitat structures are sometimes mapped
- Sources: 🟢 MNRF Aquatic Habitat Inventory; municipal stocking lakes often documented

---

## 5. Tactical Assistance (the "help buddy" piece)

### Lure / bait recommendations ⭐
- Given: species, water clarity, depth, temperature, time of day, season
- Output: lure type, color, size, presentation speed, recommended depth
- This is exactly what an experienced fishing buddy provides
- Implementation: Claude can do this directly given context; eventually build a structured recommendation engine
- Sources: encode fishing knowledge from books (legally — buy them, don't scrape), community wisdom, your own logged outcomes

### Color selection by water clarity
- Stained → chartreuse, orange, black
- Clear → natural, translucent, white
- Sun direction matters: backlit lures = silhouette colors
- 🟢 Rules-based recommendation engine

### Lure depth calculation
- Crankbaits have published dive curves
- Given line type, line weight, retrieve speed, lure weight → estimated running depth
- 🟢 Mostly published data + math

### Knot recommendations
- For species, line type, lure type
- Tutorial videos / animations
- 🟢 Static content well-suited to a knowledge base

### Line / leader / hook size suggestions
- Based on species, structure, water clarity
- 🟢 Rules-based

### Rod and reel recommendations
- For your gear inventory and target species
- Often: "with the gear you own, use the [X] for this"
- Compares to budget alternatives for what you don't own

### Presentation depth and speed
- Slow in cold water, fast in warm
- Vertical for deep structure, horizontal for shallow flats
- Suspending lures around 50°F transition
- 🟢 Rules-based with seasonal/temperature variables

### Live bait recommendations
- Where legal (regulations vary)
- Match the local forage species
- Where to buy bait nearby
- 🟡 Bait shop directory needed

### Real-time tactical adjustments
- "Wind picked up, switch to a heavier jig"
- "Pressure dropping, downsize and slow down"
- Voice or chat assistant while on the water
- 🟡 Requires good UX

---

## 6. Crowd & Historical Data (recap from earlier addenda)

### Recent catch reports (text mining)
- Reddit, fishing forums, YouTube transcripts, guide reports
- Extract: species, lure, water body, conditions, success
- Already covered in base roadmap

### Tournament results
- Bassmaster, FLW, regional tournaments publish detailed reports
- Pattern data: what won, where, when
- 🟢 publicly available, scrapeable

### Historical patterns by date
- "What's been working in this watershed in mid-May historically?"
- Aggregated from all sources over years
- ⭐ Highly valuable for trip planning

### Citizen science integration
- iNaturalist (already covered)
- GBIF (already covered)
- eBird-style angling reports (limited)
- Add: your own contributions feed back into the database

---

## 7. Access & Logistics

### Drive time and route
- From your location to candidate spots
- 🟢 OSRM or GraphHopper for open-source routing

### Parking availability
- OSM tags parking, where mapped
- Visible in imagery (gravel areas, established parking)
- 🟡 mix of OSM + visual inspection

### Cellular coverage
- Important: most fishing spots have spotty coverage
- Inform offline data needs
- 🟢 carrier coverage maps; crowd-sourced data from OpenSignal

### Boat launches
- Public ramps with parking, depth at ramp, fee/free
- Sources: 🟢 MNRF launch database; OSM

### Wheelchair / disability access
- Where designated, often documented by conservation authorities
- Sources: 🟢 some accessible-fishing-spot directories

### Restrooms, water, services
- Useful for full-day trips
- Sources: 🟢 OSM tags

### Trail conditions and length
- How far you'll actually walk
- Sources: 🟢 OSM trails; user-contributed

### Camping / lodging proximity
- Multi-day trip planning
- Sources: 🟢 OSM; Parks Canada / Ontario Parks reservation APIs

### Bait and tackle shops
- Real-time info on what's hot locally
- Local intel that can't be gotten online
- Sources: 🟡 Google Places API for locations; quality varies

### Gas stations on route
- Cottage-country fishing means planning for fuel
- 🟢 routing tools handle this

---

## 8. Personal Context

### Your gear inventory
- Track what rods, reels, line, lures, baits you own
- Bot recommends based on what you have, not what you'd ideally have
- 🟢 simple structured data

### Budget tracking
- Total annual fishing budget
- Trip costs (gas, bait, licenses, food)
- Gear purchases
- 🟢 simple ledger

### Trip log with outcomes
- Date, location, conditions, gear used, species caught, sizes, what worked
- ⭐ The most valuable training data you'll ever generate
- 🟢 structured form + photos

### Personal records
- Biggest fish per species
- Total species caught (life list)
- Days fished per year
- Catches per hour by location

### Skill level and learning goals
- Bot calibrates explanations
- "Help me learn to drop-shot" → focused tutorials + trip recommendations to practice

### Time available
- 3-hour after-work trip vs full weekend = different recommendations

### Vehicle / capabilities
- Sedan vs 4WD truck vs canoe vs kayak vs powered boat
- Determines which spots are accessible to you specifically

### Companions
- Solo, with friends, with kids
- Kid-friendly spots: easy access, lots of action, low danger
- Date-friendly spots: scenic, comfortable
- ⭐ Filters change dramatically by use case

### Privacy settings
- Which logged spots are private vs shareable with trusted friends
- What goes in your personal-only "honey hole" list

### Health / physical considerations
- Can you walk 5km? Climb steep banks? Wade?
- Filters routes

### Personal calendar integration
- Optimize within available time windows
- 🟡 calendar API connections

---

## 9. Safety

### Weather alerts ⭐
- Lightning especially — lethal danger on water
- Severe weather warnings
- Sources: 🟢 Environment Canada alerts API

### Cold water immersion warnings
- Water temp + wind temp determine hypothermia risk
- Important for spring and late fall

### Wildlife alerts
- Bear sightings, recent encounters
- Sources: 🟡 parks and conservation areas publish some; community-reported

### Tick zones
- Lyme disease risk areas, increasing each year in Southern Ontario
- 🟢 public health Lyme risk maps

### Sun and UV
- Critical info for long days on water
- 🟢 weather APIs

### Water hazards
- Submerged hazards, low-head dams (drowning machines)
- Strong currents
- 🟡 mostly community-sourced

### Cell coverage for emergencies
- Already mentioned; safety-critical not just convenience

### Float plan logging
- Tell your bot: "I'm fishing X from 6am-2pm" with optional emergency contact alerts if you don't check in
- 🟡 simple cron-style check-in feature

### Boat-specific safety
- Required equipment checklist
- Weather thresholds for your boat size
- Wave forecasts on Great Lakes

---

## 10. Regulatory & Legal

### Open seasons by zone and species ⭐
- The most-violated regulation: fishing for closed-season species
- Sources: 🟢 parse MNRF regulations PDFs; bot can confirm before each trip

### Size limits
- Slot limits, minimum, maximum
- Different by zone

### Catch limits
- Daily, possession
- Sometimes per-species per-water-body specific

### Special regulations
- Catch-and-release only zones
- Single barbless hook zones
- Bait restrictions (no live bait in some zones)
- Fly-fishing-only stretches

### License requirements
- Out-of-province validation
- Conservation license vs sport license
- Steelhead tag, salmon tag, sturgeon tag (where applicable)

### Boundary lines
- Provincial zones, lake-specific overrides
- Federal vs provincial waters

### First Nations consultation areas
- Some waters require additional permissions or have separate regulations
- Treaty rights areas

### Conservation officer reporting
- How to report violations
- Tagged-fish reporting hotline

### Border waters (US-Canada)
- Special licensing on Lake of the Woods, St. Clair, etc.

---

## 11. Conservation & Ethics

### Catch-and-release best practices
- Per-species: how long out of water, how to handle, when to release vs keep
- Particularly: deep-water catfish, lake trout (barotrauma)

### Spawning bed protection
- Bot warns when targeting bedding fish

### Invasive species spread prevention
- Drain bilges, clean gear between waters
- Don't move live fish
- 🟢 educational content

### Sensitive habitat awareness
- Brook trout headwaters, lake sturgeon spawning shoals
- Stay out of marked areas

### Reporting tagged fish
- Some species have research tags; reporting helps science

### Sustainable harvest recommendations
- "This species is overfished here; consider release"
- "This invasive species should be killed and reported"

### Photography ethics
- Don't lay fish on dry ground/rocks
- Quick water-side hero shots only

### Habitat enhancement opportunities
- Stream cleanup events nearby
- Tree planting along stream banks
- Citizen science projects

---

## 12. Learning & Skill Development

### Species identification
- From photos, fish ID using Claude vision or a specialized model
- iNaturalist's Seek model is open-source and great
- 🟢 vision LLM

### Knot tutorials
- Animated GIFs, video links, interactive
- 🟢 static content

### Technique deep dives
- Drop shot, ned rig, swimbait, fly casting, trolling
- Curated learning paths by goal

### Reading water for stream fishing
- Identifying riffles, pools, runs, holding lies
- ⭐ Could overlay AI annotations on uploaded creek photos: "Likely lie here, slack water behind boulder there"

### Mistake debriefs from your trip log
- "You used a topwater in 50°F water; bass typically don't commit at that temperature. Try a suspending jerkbait next time."
- ⭐ Powerful learning feedback loop

### Local history
- Why this lake fishes the way it does — geology, stocking history, dam construction
- Old maps, historical photos

### Fishing journals from past anglers
- Old fishing books, public domain, give a sense of how the fishery has changed

---

## 13. Exploration Features (your favorite)

### "Surprise me" mode ⭐
- One button: "Send me somewhere I've never been, within X hours' drive, where I might catch [species]"
- Returns a candidate with full briefing — directions, predicted species, access info, conditions, recommended gear
- Encourages getting out and exploring

### Adjacency suggestions
- "You've fished Sixteen Mile Creek. You haven't fished Bronte Creek 8km east. Same habitat, similar predicted species, low report density."
- 🟢 once spot discovery is built

### Exploration coverage map
- Visualize where you've fished vs where you haven't
- Gamify exploration: heat map of your personal fishing footprint
- ⭐ Surprisingly addictive

### Watershed completion
- "You've fished 4 of 12 named tributaries in the Credit River system"
- Encourages systematic exploration

### Species bingo / life list
- Bucket list species in your range
- Where most likely to catch each
- Best season for each

### Random spot generator within constraints
- Set filters: drive time, predicted species, access difficulty
- Click button, get a randomized recommendation that satisfies criteria
- Forces you out of routine

### Hidden gems mode
- Filter to spots that score high on prediction but have <2 reports anywhere
- The "no one fishes here but they should" list

### Historic exploration
- Old fishing reports from the 1950s-80s often mention spots forgotten today
- Some waterbodies were renamed, dammed, or lost; some still exist but unfished
- Sources: 🟡 scan historical fishing books/magazines (public domain ones), old MNRF reports

### Community bounty / unfished list
- Share with trusted fishing buddies: "We collectively haven't fished these 8 spots"
- Coordinate exploration trips

### Off-season exploration
- Winter is for scouting, not just ice fishing
- Plan summer trips by checking access points in winter
- Bot suggests scouting trips when active fishing is poor

---

## 14. System & UX Capabilities

### Voice interface ⭐
- Hands-free operation while on the water
- "What's the barometric pressure trend?" "Recommend a lure for this depth in stained water."
- Whisper for speech-to-text; speak responses via TTS

### Offline mode ⭐
- Cell service in fishing spots is unreliable
- Pre-download relevant maps, predictions, regulations for planned trip
- Sync when back in coverage

### Photo journaling
- Take a photo, bot logs it with auto-detected species, GPS, conditions
- Builds the trip log automatically

### Companion app for the boat / shore
- Optimized for one-handed use, wet hands, bright sun (high contrast mode)
- Big buttons, voice-first

### Trip recap reports
- After each trip, AI-generated summary: "You caught 4 smallmouth bass, biggest 1.8lb, on a Ned Rig in 14ft of water. Conditions were 68°F, falling pressure, light SW wind. This is your best trip on this lake in 3 months."

### Annual reports
- "2026 in fishing": species, sizes, distances traveled, money spent, top spots, biggest fish, lessons learned
- 🟢 reporting from trip log

### Calendar/seasonal view
- Year-long fishing planner with optimal windows for each species/water body
- Reminders for opening days, hatch timing, spawn periods

### Friends / trusted-buddy sharing
- Selectively share spots with whitelisted people
- Group trip planning
- Shared trip logs and friendly competition

### Multi-modal input
- Photo of a lure → bot identifies it and suggests how to use it
- Photo of water → bot reads it (clarity, structure visible, fishing lies)
- Voice memos → transcribed and parsed for trip log

### Time-aware notifications
- "Conditions tomorrow are ideal for [species] at [spot] — major solunar period 6:14am"
- Just push the few alerts that matter; avoid spam

### Export / data ownership
- All your data exportable as JSON/CSV/GPX
- Your trip log is yours forever

### Multi-language support
- Some Ontario fishing communities are French-speaking
- Indigenous language support for relevant communities

---

## 15. Genuinely Weird / Future Ideas

### Acoustic detection of jumping fish
- Smartphone mic + ML to detect splashes during dawn/dusk activity
- Tells you what's happening when you arrive

### Drone-assisted scouting
- For users with drones: overhead survey of a candidate water body
- Spot fish, structure, vegetation, access from the air

### Climate change projections
- 30-year species range shifts: where will smallmouth bass be common in 2050?
- Where will native brook trout still hang on?
- Sources: 🟡 published climate-fish models

### Underwater acoustic data
- Hydrophone recordings reveal fish sound communication
- More science than tool, but interesting

### Tagged fish tracking
- If MNRF acoustic telemetry data ever becomes public
- Track salmon, sturgeon movements

### Trail camera integration
- Some anglers leave cameras at remote spots
- Bot integrates with their data

### Stream temperature sensor network
- Cheap loggers ($30-50) deployed by users at key creeks
- Builds a real-time temperature map across the region
- Community-science project potential

### Augmented reality stream reading
- Point phone camera at creek; AR overlay shows likely holding lies
- Far-future but tractable

### Trip "regret minimizer"
- After each trip, bot computes: was there a better option I should have known about?
- Brutal but useful feedback for learning trip-selection skill

---

## How to Approach This

You'll never build all of this — and that's the point. The list is a buffet. A few principles for prioritizing:

1. **Build for your actual fishing first.** What do you fish for, where, how often? Optimize the bot for those specific patterns before generalizing.

2. **Trip log is the highest-leverage feature.** Almost everything else gets better when you have months of structured trip data. Build it well, fill it consistently, and the bot's recommendations compound.

3. **Exploration features differentiate you from every other fishing app.** Anyone can show you catch reports for your local lake. Surfacing the *unfished* tributary nobody talks about is the unique value.

4. **Tactical "help buddy" features are the daily-use loop.** Even when not exploring, you'll open the bot to ask "what should I throw?" That's the habit-forming feature.

5. **Safety and ethics features cost little to add and matter when they matter.** Don't skip them just because they're not exciting.

6. **Bathymetry deserves its own sprint.** Once you have it, every other feature gets better — species predictions ground better, lure suggestions can specify depths, structure overlays show on the map.

7. **The voice + offline + photo journal trio is what makes this an app you use on the water rather than at the kitchen table.** Worth investing in once the brains are working.

---

## Suggested Build Order (Holistic, Across All Addenda)

Now that you've seen the universe:

1. Base CLI bot with trip log (Roadmap 1, Phase 1)
2. iNaturalist + MNRF data ingestion (Roadmap 1, Phase 2-3)
3. Weather + conditions integration (this doc, Section 2)
4. **Tactical help-buddy: lure/bait/depth recommender** (this doc, Section 5) — high daily-use value
5. Hydrological network analysis (Addendum 2, Section 1)
6. Spot discovery from satellite (Addendum 3) + bathymetry overlay (this doc, Section 4)
7. **Exploration features built on top: surprise me, hidden gems, watershed completion** (this doc, Section 13)
8. Habitat-based species prediction (Addendum 2, Section 5)
9. Map UI + voice + offline (Roadmap 1, Phase 5 + this doc, Section 14)
10. Community/RAG content layer (Roadmap 1, Phase 4)
11. Continuous improvement architecture (Addendum 2, Section 4)
12. Whatever new ideas have shown up by then

You'll add and reshuffle as you go. That's correct. The point isn't to follow the order — it's to know what's possible so you can recognize the right next thing when you see it.
