---
name: FishBot
description: Photography-led field journal — full-bleed catch photos carry the interface; thin instrument chrome sits on top.
colors:
  base-bark: "#17140F"
  surface-loam: "#211C15"
  border-twig: "#392F22"
  text-bone: "#EAE3D3"
  text-ash: "#9A9280"
  moss: "#7C8F69"
  moss-fill: "#3D4A32"
  moss-fill-dim: "#2A331F"
  sage-tint-bg: "#262A1C"
  wet-stone: "#6B7268"
  gold: "#B8923D"
  gold-tint-bg: "#2E260F"
  rust: "#C1673D"
  rust-bg: "#2A1810"
  rust-border: "#4A2C1A"
  heat-high: "#e74c3c"
  heat-med: "#e67e22"
  heat-mid: "#f1c40f"
  heat-low: "#2ecc71"
  heat-min: "#3498db"
typography:
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "normal"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "0.02em"
  mono:
    fontFamily: "monospace"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "2px"
rounded:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "12px"
  xxl: "14px"
  sheet: "16px"
  pill: "20px"
  full: "50%"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.moss-fill}"
    textColor: "{colors.text-bone}"
    rounded: "{rounded.lg}"
    padding: "14px"
  button-primary-disabled:
    backgroundColor: "{colors.border-twig}"
    textColor: "{colors.text-ash}"
    rounded: "{rounded.lg}"
    padding: "14px"
  button-primary-loading:
    backgroundColor: "{colors.moss-fill-dim}"
    textColor: "{colors.text-bone}"
    rounded: "{rounded.lg}"
    padding: "14px"
  chip-tag:
    backgroundColor: "{colors.sage-tint-bg}"
    textColor: "{colors.moss}"
    rounded: "{rounded.sm}"
    padding: "3px 8px"
  input-field:
    backgroundColor: "{colors.surface-loam}"
    textColor: "{colors.text-bone}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
  card-surface:
    backgroundColor: "{colors.surface-loam}"
    textColor: "{colors.text-bone}"
    rounded: "{rounded.lg}"
    padding: "12px 14px"
  catch-photo-card:
    backgroundColor: "{colors.surface-loam}"
    textColor: "{colors.text-bone}"
    rounded: "{rounded.xl}"
  personal-best-badge:
    backgroundColor: "{colors.gold-tint-bg}"
    textColor: "{colors.gold}"
    rounded: "{rounded.pill}"
    padding: "4px 12px"
---

# Design System: FishBot

## 1. Overview

**Creative North Star: "The Naturalist's Field Journal"**

The North Star holds, but this revision changes what it means structurally. The reference is MOSS, a nature-walk discovery app: full-bleed real photography IS the interface — the UI sits as a thin, confident layer on top of the photo, not the other way around. The previous description of this system as "dark cards with a small photo accent inside" is retired; that's a dashboard pattern, and this is a journal pattern. A journal doesn't put your photo in a little box with a caption underneath — the photo takes the page, and you write directly on it.

Concretely: species and catch photography goes near-full-bleed, with the species name, personal-best flag, and count sitting directly on the image over a gradient scrim — not beside it or below it in a separate text zone. Completion states (finishing a session) get a real moment: a checkmark, a stat row, a filmstrip of what was actually caught, and a clear "Added to your FishDex" flag when a session produced a new species. Collection progress ("3 of 5 discoveries") gets a trail — segmented and storied — instead of a flat thin bar. Instrument data (temperature, pressure, water clarity) gets a circular dial/gauge treatment instead of small text chips, borrowing the confident, scientific-instrument feel of a compass or hiking altimeter. Chrome — nav, headers, buttons — stays thin, minimal, and out of the photo's way in every case; the photo supplies the adventure, the chrome supplies the function.

Two things this explicitly is not: it is not the illustrated/flat-icon fish style (reviewed and rejected — real photography only, never illustration, for any species or catch); and it is not a literal hiking/outdoor-brand identity (no boot icons, no leaf icons, no expedition-brand typography or taglines like "go further"). FishBot stays precise and quiet, not expedition-branded — adventurous *and* scientific, never gamified or cutesy. Think "curious and a little reverent about nature," not "conquer the trail." The prior anti-references still hold too: no pure black background, no Inter, no purple/generic SaaS gradients, no cards nested in cards.

**Key Characteristics:**
- Full-bleed real photography IS the interface on species/catch/session screens — not a thumbnail inside a card
- Species name, PB flag, and count sit directly on the photo via a bottom gradient scrim, never in a separate text zone beside or below it
- Session completion is a real moment: checkmark, stat row, catch-photo filmstrip, "Added to your FishDex" flags
- Collection/discovery progress uses a segmented trail motif, not a flat thin bar (the map's continuous score meter is the one exception — see Components)
- Instrument data (temp, pressure, clarity) reads as a circular dial/gauge, not a text chip
- Chrome stays thin, minimal, and translucent when it floats over photography; solid only on non-photo screens (chat, forms, lists)
- Real photography only — never illustrated/flat-icon fish art, never literal hiking-brand tropes

## 2. Colors

Palette is unchanged from the prior revision — warm neutrals, a desaturated moss/sage/wet-stone accent family, gold held in reserve, one earthy alarm tone. What changes in this revision is where and how these colors get used: more of the screen is now photography, so flat color fields (card backgrounds, chip fills) cover proportionally less of any given view, and gradient scrims (Bark fading to transparent) do more of the work that solid Loam fills used to do.

### Primary
- **Moss** (`#7C8F69`): Text, icons, links, active indicators, and dial-arc fills for "favorable" instrument readings.
- **Moss Fill** (`#3D4A32`): Filled surfaces (primary button backgrounds) holding Bone text.
- **Moss Fill Dim** (`#2A331F`): The "processing" state of a filled button.
- **Sage Tint** (`#262A1C`): Background behind Moss text on chips/tags.

### Secondary
- **Wet Stone** (`#6B7268`): Secondary/inactive elements, and dial-arc fills for "neutral" instrument readings — present but not the point.

### Tertiary (rare)
- **Gold** (`#B8923D`): Personal-best moments and new species added to the FishDex — the one warm, precious color in the system. See The Earned Gold Rule.
- **Gold Tint** (`#2E260F`): Background behind a gold callout or badge.

### Neutral
- **Bark** (`#17140F`): App background — warm, not pure black.
- **Loam** (`#211C15`): Raised surfaces on non-photo screens (chat, forms, lists). Not used as a photo-card frame anymore in the near-full-bleed pattern — see Components.
- **Twig** (`#392F22`): Hairline borders, dividers, disabled fills, progress tracks.
- **Bone** (`#EAE3D3`): Primary text — on dark surfaces and directly on photo scrims alike.
- **Ash** (`#9A9280`): Secondary/meta text, and dial-arc fills for "unfavorable" instrument readings alongside Rust for genuinely poor conditions.

### Semantic (single alarm)
- **Rust** (`#C1673D` text / `#2A1810` background / `#4A2C1A` border): The one alarm color — errors, warnings, and poor-condition instrument readings alike.

### Data (map exploration score — unchanged, flagged)
- **Heat High → Heat Min**: The map's sequential score scale stays as-is (Section 5, Progress & Trail notes). Still the one saturated holdover; still not solved in this revision.

### Named Rules
**The Photograph IS the Interface Rule.** On any species, catch, or session screen, the photo is not an element on the page — it is the page. UI sits on top of it as a thin translucent layer (see The Overlay Chrome Rule), never as a frame around a smaller photo inside a card.

**The Earned Gold Rule.** Gold marks an actual event: a personal-best catch, a new species added to the FishDex, a milestone. Never a generic highlight or default active state.

**The One Alarm Rule.** Rust is the only alarm color, for UI errors and for a poor instrument reading alike. Severity is carried by copy and dial position, not a second hue.

## 3. Typography

**Body Font:** -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif — the system stack, deliberately not Inter, unchanged in this revision.
**Label/Mono Font:** monospace (system default), used once: the invite-code field.

**Character:** Unchanged — a single honest system sans at every size. On photo-first screens, type sits directly on the image (over a scrim), so it carries slightly more weight there by necessity: prefer 600 over 400 for anything overlaid on a photo, even where the equivalent element on a solid surface would be regular weight.

### Hierarchy
- **Title** (600, 18–24px, 1.3 line-height): Screen headings, the Login wordmark, and species names overlaid on a photo card.
- **Body** (400, 14px, 1.5 line-height): Chat messages, textarea content, form values.
- **Label** (500, 10–12px, 1.3 line-height, occasional uppercase + 0.02em tracking): Form labels, timestamps, nav labels, dial readouts, stat-row captions.
- **Mono** (400, 16px, 2px tracking): The invite-code input only.

### Named Rules
**The Quiet Type Rule.** Nothing exceeds 24px, and 24px appears exactly once. Hierarchy comes from weight and color, never a dramatic size jump — this includes text overlaid on photography, which gets weight, not size, to stay legible.

## 4. Elevation

Flat by default, unchanged: no `box-shadow` anywhere. What's new is a second chrome treatment specifically for photo-first screens. On non-photo screens (chat, forms, lists), raised surfaces are still solid Loam + a 1px Twig edge. On photo-first screens (a session-complete summary, a species detail hero, any screen where a nav bar or header floats directly over full-bleed photography), chrome instead uses a translucent dark scrim with `backdrop-filter: blur(...)` — solid Loam would fight the photo underneath it; a blurred scrim lets the image continue to read through.

Grain texture (from the prior revision) still applies only to non-photo background surfaces — it has no role on top of real photography, which already supplies all the material/texture the screen needs.

### Named Rules
**The Flat-by-Default Rule.** No shadows. Loam + Twig for solid chrome; a blurred scrim for chrome over photography.

**The Overlay Chrome Rule.** Any nav, header, or button that sits directly on top of full-bleed photography uses a translucent Bark scrim (`rgba(23,20,15,~0.5–0.7)`) with backdrop blur, never a solid fill — the photo must stay visible through it.

**The Sparing Grain Rule.** Grain is a non-photo background material only, on at most one or two large surfaces per screen.

## 5. Components

### Catch / Species Photo Card (primary browsing pattern — rewritten)
- **Structure:** One large, near-full-bleed photo per scroll unit — not a grid of small square thumbnails. Aspect ratio leans portrait (~4:5) so a single catch photo dominates the viewport; minimal outer padding so the card reads as edge-to-edge, not framed.
- **Text placement:** Species name (Title weight), personal-best flag, and count sit directly on the photo inside a bottom gradient scrim (Bark fading to transparent, covering roughly the bottom 35–40% of the image) — never in a text zone beside or below the photo.
- **Border:** A single 1px Twig edge at the card's outer radius (`{rounded.xl}`) — the only framing device; no inner card, no nested surface.
- **Personal-best / new-species variant:** A small Gold badge (`personal-best-badge` token) in the photo's top corner — the primary place The Earned Gold Rule surfaces in product.
- Species chips (`chip-tag`) still exist, but only for dense inline lists with no photo available (chat mentions, a compact fallback list) — never as the default browsing pattern.

### Session Complete Screen (new signature pattern)
Modeled directly on a "walk complete" summary: a clear, earned end-of-session moment, not just a form confirmation.
- **Checkmark:** A simple circular check, Moss by default; Gold instead if the session included a personal best or a new species.
- **Stat row:** Three stats side by side — location, duration, species caught — as large Title-weight numerals with a Label-weight caption beneath each, mirroring a distance/time/discoveries layout.
- **Photo filmstrip:** A horizontal scrollable strip of the actual catch photos from the session. This is the one place small thumbnails are correct — a recap filmstrip is a secondary, retrospective use, not the primary discovery/browsing pattern that the full-bleed Photo Card owns.
- **New species flag:** Any first-time species in the session gets an explicit "Added to your FishDex" tag (Gold text on Gold Tint), separate from and in addition to a personal-best flag on the same catch if both apply.

### Discovery Progress Trail (new component)
- **Structure:** A horizontal segmented trail of dots/marks — filled Moss for logged/discovered, outline Twig/Ash for not-yet-found — with a caption like "3 of 5 discoveries." Used for collection/dex-style progress (species found within a family, a challenge, a trip's discovery count).
- **Completion:** If a trail reaches full completion, the final segment and caption take Gold instead of Moss — a small, earned moment, consistent with The Earned Gold Rule.
- **Distinct from the map's exploration-score bar** (below), which is a continuous 0–100 measurement, not a discrete collection count — the trail and the bar are not interchangeable.

### Instrument Dial (new component)
- **Structure:** A circular gauge — a stroke-based progress ring with a centered numeric readout (value + unit, e.g. "18°C", "1013 hPa") and a Label-weight caption beneath or beside it. Used for temperature, barometric pressure, and water clarity wherever they currently render as small text chips.
- **Color:** The ring arc is colored by reading quality using the existing semantic set — Moss for favorable, Ash/Wet Stone for neutral, Rust for unfavorable — no new hexes introduced for this purpose.
- **Feel:** Confident and scientific-instrument-like (compass/altimeter register), not playful or rounded-cartoon.

### Buttons
- **Shape:** 10px radius for full-width CTAs.
- **Primary:** Moss Fill background, Bone text, 600 weight.
- **Disabled / Loading:** Twig+Ash / Moss Fill Dim, as before.
- **Focus:** Visible Moss ring on `:focus-visible` — required on every button.
- **On photography:** Icon-only buttons that float over a photo (e.g. a back button on a photo-first hero) use the Overlay Chrome treatment — translucent Bark circle with blur — never a solid fill.

### Chips / Pills
- **Species tag:** Sage Tint background, Moss text — inline/no-photo contexts only now (see Photo Card above).
- **Alarm pill:** Rust text/border on Rust Tint — the single style for any warning or error state.

### Cards / Containers (non-photo screens only)
- **Corner Style:** 10–12px radius.
- **Background:** Loam on Bark, 1px Twig border, no shadow.
- **Use:** Trip list rows, form containers, chat — anywhere there isn't a dominant photo. This is now explicitly the secondary pattern; photo-first screens use the Photo Card and Overlay Chrome treatments instead.

### Inputs / Fields
- Loam background, 1px Twig stroke, Bone text, Ash label. Required Moss `:focus-visible` ring/border — previously missing, still a hard requirement.

### Navigation
- **Solid variant** (non-photo screens: chat, list, forms): Loam background, 1px Twig top edge, Moss active state, Ash inactive.
- **Overlay variant** (photo-first screens): translucent Bark scrim + backdrop blur (The Overlay Chrome Rule) instead of solid Loam, same Moss/Ash color logic for active/inactive.

### Message Bubbles
- Bot: Loam background, 2px Moss left accent, asymmetric radius. User: Moss Fill background, Bone text, mirrored radius. Unchanged.

### Exploration Score Bar (map only — unchanged, distinct from the Discovery Trail above)
- 6px height, Twig track, fill uses the Heat data scale, 0.3s width transition. This is a continuous score meter for the map, not a collection-progress indicator — see Discovery Progress Trail for that use case.

## 6. Do's and Don'ts

### Do:
- **Do** let full-bleed real photography be the interface on species, catch, and session screens — chrome floats thin and minimal on top of it, never the reverse.
- **Do** put species name, PB flag, and count directly on the photo via a bottom gradient scrim — never beside or below it in a separate text zone.
- **Do** give session completion a real moment: checkmark, stat row, catch-photo filmstrip, explicit "Added to your FishDex" flags for new species.
- **Do** use a segmented, storied trail for collection/discovery progress ("3 of 5 discoveries") — reserve the plain thin bar for the map's continuous score meter only.
- **Do** give instrument data (temp, pressure, clarity) a circular dial/gauge treatment, colored with the existing Moss/Ash/Rust semantic set.
- **Do** use a translucent blurred scrim, not solid Loam, for any chrome floating over full-bleed photography (The Overlay Chrome Rule).
- **Do** keep chrome thin, precise, and out of the photo's way — the photo carries emotion, the chrome carries function.
- **Do** keep the tone adventurous *and* scientific — curious, precise, a little reverent about nature. Never gamified or cutesy.
- **Do** give every input and button a visible focus state (Moss ring) — still a hard requirement.

### Don't:
- **Don't** use small square photo thumbnails inside dark cards as the primary species/catch browsing pattern — that dashboard-of-cards look is retired. (Small thumbnails are correct only in the Session Complete filmstrip, a secondary recap context.)
- **Don't** use illustrated or flat-icon fish artwork anywhere — real photography only, for any species or catch.
- **Don't** borrow literal hiking/outdoor-brand tropes — boot icons, leaf icons, expedition-adventure typography or taglines ("go further," "conquer"). This stays precise and quiet, not expedition-branded.
- **Don't** use pure black backgrounds, Inter, or purple/generic SaaS gradients.
- **Don't** nest cards inside cards.
- **Don't** default collection/discovery progress to a plain thin bar when the trail motif fits — and don't use the trail motif for the map's continuous score meter, which is a different data shape.
- **Don't** add badges, leaderboards, streak counters, or social-feed gamification patterns — Gold-marked personal bests and FishDex additions are the one deliberate, earned exception.
- **Don't** let a dial, trail, or any instrument element read as playful or rounded-cartoon — the register is scientific-instrument, not gamified.
- **Don't** use `border-left` as a decorative colored stripe anywhere except the bot message bubble's tail accent.

### Migration note
The naturalist palette is fully implemented: `web/src/tokens.css` (`:root` custom properties) and `web/src/tokens.js` (the Leaflet-consumed mirror) are the single source of truth, and all 7 components reference them — no raw hex remains in the app outside those two files.

Of the four flagship photography-led patterns, two are live and backed by real data:
- **LogTrip's photo preview** uses the near-full-bleed Catch Photo Card treatment — GPS status sits directly on the image via a bottom scrim, not as separate pills below it.
- **Instrument Dial** is live for air temperature and barometric pressure in Trips and the Map bottom sheet (`web/src/components/InstrumentDial.jsx`). Deliberately not colored by reading quality (favorable/neutral/unfavorable) as originally specified — the app has no real thresholds for what counts as "favorable" fishing conditions, and inventing one would be exactly the kind of unsupported presence/quality claim CLAUDE.md's core principle warns against. The ring shows position-in-range only, in a single neutral Moss fill.

Two are intentionally **not yet implemented** — both need backend work first, not just frontend polish:
- **Full-bleed Catch Photo Cards in Trips/Map** — the backend never receives or stores the actual photo file today (`logTrip()` sends only `photo_lat`/`photo_lng`/`photo_taken_at`, extracted client-side from EXIF; the image itself is discarded after upload). There's no photo to show in trip history or the map without adding real photo storage.
- **Discovery Progress Trail** — there's no species-collection/"discoveries" concept in the API at all yet (no endpoint, no aggregate). This is a real product decision (what counts as a "discovery," per-family or global count) as much as a backend one.

This is now the reference `/impeccable audit` and `/impeccable critique` should check against, with the above two gaps understood as backend-blocked, not oversights.
