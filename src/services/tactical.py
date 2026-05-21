"""Tactical recommender: synthesizes conditions into lure/technique recommendations."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from src.models.recommendation import LureRecommendation
from src.storage.database import get_db
from src.storage.recommendations import insert_recommendation

# ── Species classification ────────────────────────────────────────────────────

_MICROFISHING_KEYWORDS = {
    "darter",
    "dace",
    "madtom",
    "shiner",
    "chub",
    "lamprey",
    "stonecat",
    "sculpin",
    "logperch",
    "bitterling",
    "minnow",
}

# First match wins — longer/more-specific patterns first
_SPECIES_PATTERNS: list[tuple[str, str]] = [
    ("brook trout", "trout"),
    ("rainbow trout", "trout"),
    ("brown trout", "trout"),
    ("lake trout", "trout"),
    ("splake", "trout"),
    ("trout", "trout"),
    ("smallmouth", "bass"),
    ("largemouth", "bass"),
    ("rock bass", "bass"),
    ("bass", "bass"),
    ("muskellunge", "pike"),
    ("muskie", "pike"),
    ("northern pike", "pike"),
    ("pike", "pike"),
    ("walleye", "walleye"),
    ("sauger", "walleye"),
    ("pickerel", "walleye"),  # Ontario common name for walleye
    ("channel cat", "catfish"),
    ("catfish", "catfish"),
    ("bullhead", "catfish"),
    ("bluegill", "panfish"),
    ("pumpkinseed", "panfish"),
    ("crappie", "panfish"),
    ("yellow perch", "panfish"),
    ("perch", "panfish"),
    ("sunfish", "panfish"),
    ("carp", "carp"),
    ("redhorse", "carp"),
    ("sucker", "carp"),
    ("gar", "unknown"),
]


def _classify(species: str) -> tuple[str, bool]:
    """Returns (species_group, is_microfishing)."""
    low = species.lower()
    for kw in _MICROFISHING_KEYWORDS:
        if kw in low:
            return ("microfishing", True)
    for pattern, group in _SPECIES_PATTERNS:
        if pattern in low:
            return (group, False)
    return ("unknown", False)


# ── Season ────────────────────────────────────────────────────────────────────


def _season(month: int) -> str:
    if month <= 2:
        return "winter"
    if month <= 4:
        return "pre_spawn"
    if month <= 6:
        return "spawn"
    if month <= 8:
        return "summer"
    if month <= 10:
        return "fall"
    return "early_winter"


# ── Temperature activity ──────────────────────────────────────────────────────

# (cold_limit, opt_low, opt_high, warm_limit)
_THRESHOLDS: dict[str, tuple[float, float, float, float]] = {
    "trout": (2.0, 8.0, 16.0, 20.0),
    "bass": (10.0, 18.0, 26.0, 30.0),
    "pike": (4.0, 15.0, 22.0, 26.0),
    "walleye": (4.0, 15.0, 21.0, 27.0),
    "catfish": (15.0, 22.0, 28.0, 32.0),
    "panfish": (5.0, 18.0, 24.0, 28.0),
    "carp": (8.0, 16.0, 24.0, 30.0),
    "unknown": (10.0, 18.0, 26.0, 30.0),
    "microfishing": (2.0, 8.0, 22.0, 28.0),
}


def _temp_activity(temp_c: float, group: str) -> str:
    cold, opt_low, opt_high, warm = _THRESHOLDS.get(group, _THRESHOLDS["unknown"])
    if temp_c < cold:
        return "lethargic"
    if temp_c < opt_low:
        return "sub_optimal"
    if temp_c <= opt_high:
        return "active"
    if temp_c <= warm:
        return "warm_stress"
    return "over_warm"


# ── Rule tables ───────────────────────────────────────────────────────────────

_SPEED_INT = {"slow": 0, "medium": 1, "fast": 2}
_INT_SPEED = ["slow", "medium", "fast"]

_BASE_SPEED: dict[str, str] = {
    "lethargic": "slow",
    "sub_optimal": "slow",
    "active": "medium",
    "warm_stress": "slow",
    "over_warm": "slow",
}

# (primary_lure_type, secondary_lure_type) by group → season
_LURE_TABLE: dict[str, dict[str, tuple[str, str]]] = {
    "trout": {
        "winter": ("jigging spoon (1/16-1/8 oz)", "live bait on finesse rig"),
        "pre_spawn": ("inline spinner (Mepps #1-2)", "small spoon (1/8-1/4 oz)"),
        "spawn": ("egg bead / egg fly pattern", "small nymph or wet fly"),
        "summer": ("dry fly / emerger", "small streamer (olive/black, 2-3 in)"),
        "fall": ("streamer (olive/black, 2-3 in)", "inline spinner"),
        "early_winter": ("slow-rolled spoon", "live bait under float"),
    },
    "bass": {
        "winter": ("blade bait / jigging spoon", "finesse jig (1/8-1/4 oz)"),
        "pre_spawn": ("jerkbait", "medium-diving crankbait"),
        "spawn": ("drop-shot rig", "finesse worm (5-6 in)"),
        "summer": ("football jig (1/2 oz)", "deep-diving crankbait"),
        "fall": ("spinnerbait (3/8-1/2 oz)", "lipless crankbait"),
        "early_winter": ("blade bait", "jigging spoon"),
    },
    "pike": {
        "winter": ("large jigging spoon (1-2 oz)", "large jig with soft trailer"),
        "pre_spawn": ("large spinnerbait (1 oz)", "jerkbait (5-7 in)"),
        "spawn": ("bucktail jig", "large minnow bait"),
        "summer": ("surface frog (weedbed edges)", "large soft swimbait"),
        "fall": ("large spoon (1-2 oz)", "large jerkbait"),
        "early_winter": ("large jigging spoon", "large jig + soft trailer"),
    },
    "walleye": {
        "winter": ("jigging spoon (1/4-1/2 oz)", "live bait rig (leech or nightcrawler)"),
        "pre_spawn": ("jig (1/4-3/8 oz)", "slow-death rig"),
        "spawn": ("jig + live bait (slow death)", "bottom bouncer + nightcrawler harness"),
        "summer": ("deep-diving crankbait", "bottom bouncer + spinner harness"),
        "fall": ("jig + paddle tail (3-4 in)", "medium-diving crankbait"),
        "early_winter": ("jigging spoon", "blade bait"),
    },
    "catfish": {
        "winter": ("cut bait on bottom (dead stick)", "punch bait + treble hook"),
        "pre_spawn": ("nightcrawler / chicken liver (slip rig)", "cut shad"),
        "spawn": ("punch bait / stink bait (bottom)", "cut bait"),
        "summer": ("cut shad / skipjack (Santee rig)", "circle hook + live bait"),
        "fall": ("cut bait (Santee rig)", "nightcrawler + slip float"),
        "early_winter": ("cut bait on bottom", "punch bait"),
    },
    "panfish": {
        "winter": ("tiny jig (1/64-1/32 oz)", "live bait (waxworm) under float"),
        "pre_spawn": ("small jig (1/32 oz)", "small tube (1.5-2 in)"),
        "spawn": ("small tube / inline spinner (#0)", "live bait under float"),
        "summer": ("small surface popper", "small jig (1/32 oz) under float"),
        "fall": ("small crankbait (1-1.5 in)", "small jig (1/16 oz)"),
        "early_winter": ("tiny jig (1/64 oz)", "live bait (waxworm or maggot)"),
    },
    "carp": {
        "winter": ("boilie on hair rig (dead stick)", "corn on small hook"),
        "pre_spawn": ("boilie (spring blend, 14-18 mm)", "tiger nuts on hair rig"),
        "spawn": ("small bait (corn / bread punch)", "boilie (10-14 mm)"),
        "summer": ("surface bait (floating dog biscuit)", "boilie + PVA stick"),
        "fall": ("boilie (fishmeal blend)", "tiger nuts / cell boilie"),
        "early_winter": ("boilie (winter blend, 10 mm)", "corn"),
    },
    "unknown": {
        "winter": ("jig (1/8-1/4 oz)", "live bait rig"),
        "pre_spawn": ("jerkbait / medium crankbait", "spinnerbait"),
        "spawn": ("finesse worm / drop-shot", "small jig"),
        "summer": ("deep-diving crankbait", "football jig"),
        "fall": ("spinnerbait", "lipless crankbait"),
        "early_winter": ("blade bait", "jig (1/4 oz)"),
    },
}

_SIZE_RANGES: dict[str, str] = {
    "trout": "size 10-16 hook (flies), 1/16-1/4 oz (hardware)",
    "bass": "3/8-1/2 oz (reaction), 5-7 in (soft plastics)",
    "pike": "1/2-2 oz, 5-9 in lures",
    "walleye": "1/4-1/2 oz, 3-5 in lures",
    "catfish": "2/0-5/0 hook, 1-3 oz sinker",
    "panfish": "1/32-1/16 oz jig, size 6-10 hook",
    "carp": "size 4-8 hook, 2-4 oz lead",
    "unknown": "1/4-3/8 oz, 3-5 in",
    "microfishing": "size 20-26 hook, 2-4 lb fluorocarbon, 1/64 oz split shot",
}

_DEFAULT_COLORS: dict[str, str] = {
    "trout": "natural (olive, white, silver)",
    "bass": "green pumpkin / white",
    "pike": "white / chartreuse (large profile)",
    "walleye": "chartreuse / white",
    "catfish": "scent over color — cut bait or stink bait",
    "panfish": "white / chartreuse",
    "carp": "boilie color — fishmeal or fruit blend",
    "unknown": "chartreuse / white (versatile)",
    "microfishing": "natural (waxworm or maggot color)",
}

_CLARITY_PRIMARY: dict[str, str] = {
    "clear": "natural/translucent (white, silver, green pumpkin, smoke)",
    "stained": "chartreuse/white",
    "murky": "black/dark brown (maximum contrast)",
}
_CLARITY_SECONDARY: dict[str, str] = {
    "clear": "subtle (watermelon red flake, natural olive)",
    "stained": "orange/chartreuse or hot pink",
    "murky": "dark blue/purple",
}

_DEPTH_BY_TIME: dict[str, str] = {
    "dawn": "0-3 ft",
    "morning": "2-10 ft",
    "midday": "10-20 ft",
    "afternoon": "8-18 ft",
    "evening": "2-10 ft",
    "dusk": "0-4 ft",
    "night": "0-8 ft",
}
_DEPTH_BY_SEASON: dict[str, str] = {
    "winter": "10-25 ft",
    "pre_spawn": "2-10 ft",
    "spawn": "1-6 ft",
    "summer": "8-20 ft",
    "fall": "3-15 ft",
    "early_winter": "10-25 ft",
}

# Lookup a base technique description by keyword in lure_type
_LURE_TECHNIQUES: dict[str, str] = {
    "topwater": "walk or pop on the surface, vary cadence to trigger reaction strikes",
    "popper": "pop and pause, letting ripples dissipate before the next pop",
    "frog": "work over vegetation, pause in holes and pockets",
    "buzzbait": "steady retrieve just fast enough to keep the blade churning the surface",
    "spinnerbait": "slow-roll near bottom or burn through cover, vary depth",
    "lipless crankbait": "rip-and-pause through vegetation edges or open water",
    "jerkbait": "jerk-pause-jerk with an irregular rhythm, longer pauses in cold water",
    "crankbait": "run along bottom or structure breaks, match depth to bill size",
    "drop-shot": "hover in place with subtle shakes; let the bait breathe",
    "finesse jig": "slow crawl along bottom, occasional hop; feel for changes in texture",
    "football jig": "drag and crawl along rocky bottom, pause frequently",
    "blade bait": "vertical jigging with short snaps, let it flutter on the fall",
    "jigging spoon": "vertical jigging in deep water; let it freefall on a slack line",
    "streamer": "swing across current or strip-retrieve with irregular pauses",
    "inline spinner": "cast upstream or across, retrieve with or against current",
    "dry fly": "dead drift on the surface; mend to avoid drag",
    "nymph": "dead drift near bottom with occasional lifts",
    "egg bead": "drift naturally through pools and runs below spawning areas",
    "spoon": "cast and retrieve with varied speed, or flutter vertically",
    "hair rig": "cast to feature, leave stationary; check every 30-60 minutes",
    "boilie": "cast to likely feature, leave stationary; check every 30-60 minutes",
    "cut bait": "bottom rig, stationary or very slow drag",
    "live bait": "slow drift or stationary under float; let the bait do the work",
    "punch bait": "bottom rig, stationary; scent does the work",
    "ultralight rig": "drift natural bait through current seams, eddies, and undercut banks",
    "jig": "hop along bottom with steady retrieve, vary the cadence",
    "tube": "drag and crawl along bottom, occasional twitch",
}


def _technique_for_lure(lure_type: str, extra_notes: list[str]) -> str:
    low = lure_type.lower()
    base = "present at depth, vary cadence until a pattern emerges"
    for keyword, desc in _LURE_TECHNIQUES.items():
        if keyword in low:
            base = desc
            break
    if extra_notes:
        base += " — " + ", ".join(extra_notes)
    return base


# ── Reasoning builder ─────────────────────────────────────────────────────────


def _build_reasoning(
    species: str,
    season: str,
    temp_c: float | None,
    temp_act: str | None,
    clarity: str | None,
    pressure: str | None,
    time_of_day: str | None,
    lure_type: str,
) -> str:
    parts: list[str] = []

    season_phrases = {
        "winter": (
            f"Mid-winter {species} are in their deepest, most lethargic phase — "
            "metabolism slows dramatically, so you need to work the bait right in front of them."
        ),
        "pre_spawn": (
            f"Pre-spawn {species} are staging and growing increasingly aggressive as water warms — "
            "one of the best times of year to be on the water."
        ),
        "spawn": (
            f"Spawn period for {species}: fish are focused on reproduction. "
            "Finesse near structure; avoid pressuring beds. "
            "Catch-and-release is the ethical call here."
        ),
        "summer": (
            f"Summer {species} are stressed by midday heat. "
            "Fish early morning or evening when water is coolest, "
            "or target the deepest water available."
        ),
        "fall": (
            f"Fall is prime for {species} — they're aggressively bulking up before winter. "
            "This is one of the best feeding windows of the year."
        ),
        "early_winter": (
            f"Early winter {species} are slowing down and transitioning to deep structure. "
            "Slow, bottom-contact presentations are the move."
        ),
    }
    parts.append(season_phrases.get(season, f"Fishing for {species}."))

    if temp_c is not None and temp_act is not None:
        temp_phrases = {
            "lethargic": (
                f"At {temp_c:.0f}°C the water is frigid — fish metabolism is near-zero. "
                "Tiny, slow, dead-bottom presentations are the only play."
            ),
            "sub_optimal": (
                f"At {temp_c:.0f}°C the water is cool; fish are sluggish but catchable "
                "with finesse presentations."
            ),
            "active": (
                f"At {temp_c:.0f}°C this is the optimal feeding temperature range — "
                f"{species} should be actively hunting."
            ),
            "warm_stress": (
                f"At {temp_c:.0f}°C the water is on the warm side; fish are beginning to stress. "
                "Early morning or late evening are your windows."
            ),
            "over_warm": (
                f"At {temp_c:.0f}°C the water is too warm for comfortable feeding — "
                "target the deepest, coolest water; fish before 8 AM or after 8 PM."
            ),
        }
        parts.append(temp_phrases.get(temp_act, ""))

    if pressure is not None:
        pressure_phrases = {
            "falling": (
                "Falling barometric pressure is opening an aggressive feeding window — "
                "fish often go on the bite ahead of a front. Don't miss this."
            ),
            "rising": (
                "Rising post-front pressure often suppresses feeding. "
                "Slower, more natural presentations will out-fish reaction baits right now."
            ),
            "steady": (
                "Steady pressure means baseline conditions — "
                "no strong barometric edge in either direction."
            ),
        }
        parts.append(pressure_phrases.get(pressure, ""))

    if clarity is not None:
        clarity_phrases = {
            "clear": (
                "Clear water means fish can inspect your bait closely — "
                "natural colors and finesse presentations out-fish loud stuff here."
            ),
            "stained": (
                "Stained water cuts visibility, so high-contrast colors (chartreuse, orange) "
                "and added vibration help fish locate the bait."
            ),
            "murky": (
                "Murky water means fish are using their lateral line more than sight — "
                "dark, high-contrast colors and maximum vibration or scent are essential."
            ),
        }
        parts.append(clarity_phrases.get(clarity, ""))

    if time_of_day is not None:
        tod_phrases = {
            "dawn": (
                "Dawn is a prime window: low light, cool surface water, "
                "predators pushing shallow."
            ),
            "morning": (
                "Morning: fish are still active from the dawn feed. "
                "Mid-column and shallow structure are productive."
            ),
            "midday": (
                "Midday sun pushes fish deep or into shade — "
                "work structure deep or wait for the evening bite."
            ),
            "afternoon": (
                "Afternoon: fish staged deep but starting to move shallower "
                "as sun angle drops."
            ),
            "evening": (
                "Evening bite is ramping up — "
                "fish moving from deep structure toward the shallows."
            ),
            "dusk": (
                "Dusk is another prime window: low light, surface activity picking back up."
            ),
            "night": (
                "Night fishing: go dark, add noise or vibration, slow down — "
                "fish are hunting by lateral line."
            ),
        }
        parts.append(tod_phrases.get(time_of_day, ""))

    parts.append(f"The {lure_type} matches these combined conditions well.")

    return " ".join(p for p in parts if p)


# ── Confidence ────────────────────────────────────────────────────────────────

_CONF_TIERS = ["low", "medium", "high"]


def _confidence(condition_count: int, group_known: bool) -> Literal["high", "medium", "low"]:
    if condition_count >= 3 and group_known:
        return "high"
    if condition_count >= 2 or group_known:
        return "medium"
    return "low"


# ── Microfishing shortcut ─────────────────────────────────────────────────────


def _microfishing_recs(
    species: str,
    season: str,
    temp_c: float | None,
    pressure: str | None,
    time_of_day: str | None,
    condition_count: int,
) -> list[LureRecommendation]:
    matched = ["microfishing target — ultralight terminal tackle required"]
    if season in ("winter", "early_winter"):
        matched.append("cold season — fish are present but lethargic; stealth and patience matter")
    if pressure == "falling":
        matched.append("falling pressure — micro-species may be slightly more active")
    if time_of_day in ("dawn", "dusk"):
        matched.append("low-light period — darters and sculpin more active in current seams")

    reasoning = (
        f"Microfishing targets like {species} require ultralight terminal tackle. "
        "Use size 20-26 hooks — anything larger will miss most bites and risks gut-hooking. "
        "Drift natural bait (waxworm, maggot, tiny piece of nightcrawler) through current seams, "
        "eddies behind rocks, and along undercut banks — that's where darters, dace, "
        "and madtoms hold. "
        "2-4 lb fluorocarbon is effectively invisible in most stream conditions. "
        "Stealth and patience matter far more than lure color or action."
    )
    if season in ("winter", "early_winter"):
        reasoning += " In cold water, fish even slower — they won't chase."
    if pressure == "rising":
        reasoning += (
            " Rising pressure tends to suppress activity even in micro-species; be patient."
        )

    return [
        LureRecommendation(
            lure_type="ultralight rig",
            color="natural (waxworm, maggot, or tiny nightcrawler piece)",
            size_range="size 20-26 hook, 2-4 lb fluorocarbon, 1/64 oz split shot",
            technique="drift natural bait through current seams, eddies, and undercut banks",
            retrieve_speed="slow",
            target_depth_range="0-2 ft",
            conditions_matched=matched,
            confidence=_confidence(condition_count, True),
            reasoning=reasoning,
        )
    ]


# ── Standard recommendations ──────────────────────────────────────────────────


def _standard_recs(
    species: str,
    group: str,
    season: str,
    temp_c: float | None,
    clarity: str | None,
    pressure: str | None,
    time_of_day: str | None,
    condition_count: int,
) -> list[LureRecommendation]:
    temp_act: str | None = None
    if temp_c is not None:
        temp_act = _temp_activity(temp_c, group)

    # Base retrieve speed from temperature, adjusted by pressure
    base_spd = _SPEED_INT[_BASE_SPEED.get(temp_act, "medium") if temp_act else "medium"]
    if pressure == "falling":
        base_spd = min(base_spd + 1, 2)
    elif pressure == "rising":
        base_spd = max(base_spd - 1, 0)
    retrieve_speed: Literal["slow", "medium", "fast"] = _INT_SPEED[base_spd]  # type: ignore[assignment]

    # Lure types from table
    primary_lure, secondary_lure = _LURE_TABLE.get(group, _LURE_TABLE["unknown"]).get(
        season, ("jig (1/4 oz)", "live bait rig")
    )

    # Dawn/dusk topwater override for active predators in warmer months
    if (
        time_of_day in ("dawn", "dusk")
        and temp_act in ("active", "warm_stress")
        and group in ("bass", "pike")
        and season in ("summer", "fall", "pre_spawn")
    ):
        primary_lure = "topwater popper / walking bait"
        secondary_lure = "buzzbait or wake bait"

    # Colors
    if clarity:
        primary_color = _CLARITY_PRIMARY[clarity]
        secondary_color = _CLARITY_SECONDARY[clarity]
    else:
        primary_color = _DEFAULT_COLORS.get(group, "chartreuse / white")
        secondary_color = primary_color

    # Depth range
    if time_of_day and time_of_day in _DEPTH_BY_TIME:
        depth = _DEPTH_BY_TIME[time_of_day]
    else:
        depth = _DEPTH_BY_SEASON.get(season, "5-15 ft")

    # Conditions matched list (human-readable)
    matched: list[str] = [f"{season.replace('_', '-')} season"]
    if temp_c is not None and temp_act:
        matched.append(f"{temp_c:.0f}°C water ({temp_act.replace('_', ' ')})")
    if clarity:
        matched.append(f"{clarity} water")
    if pressure:
        matched.append(f"{pressure} barometric pressure")
    if time_of_day:
        matched.append(f"{time_of_day}")

    # Extra technique notes driven by conditions
    technique_notes: list[str] = []
    if clarity in ("stained", "murky"):
        technique_notes.append("add vibration or rattle")
    if clarity == "murky":
        technique_notes.append("add scent if available")
    if pressure == "falling":
        technique_notes.append("reaction-bait cadence")
    if temp_act in ("lethargic", "sub_optimal"):
        technique_notes.append("slow bottom-contact or deadstick")

    conf = _confidence(condition_count, group != "unknown")
    secondary_conf: Literal["high", "medium", "low"] = _CONF_TIERS[  # type: ignore[assignment]
        max(0, _CONF_TIERS.index(conf) - 1)
    ]
    size = _SIZE_RANGES.get(group, _SIZE_RANGES["unknown"])

    primary_rec = LureRecommendation(
        lure_type=primary_lure,
        color=primary_color,
        size_range=size,
        technique=_technique_for_lure(primary_lure, technique_notes),
        retrieve_speed=retrieve_speed,
        target_depth_range=depth,
        conditions_matched=matched,
        confidence=conf,
        reasoning=_build_reasoning(
            species, season, temp_c, temp_act, clarity, pressure, time_of_day, primary_lure
        ),
    )

    secondary_rec = LureRecommendation(
        lure_type=secondary_lure,
        color=secondary_color,
        size_range=size,
        technique=_technique_for_lure(secondary_lure, technique_notes) + " (alternative)",
        retrieve_speed=retrieve_speed,
        target_depth_range=depth,
        conditions_matched=matched,
        confidence=secondary_conf,
        reasoning=_build_reasoning(
            species, season, temp_c, temp_act, clarity, pressure, time_of_day, secondary_lure
        ),
    )

    return [primary_rec, secondary_rec]


# ── Public service function ───────────────────────────────────────────────────


def get_tactical_recommendation_for_agent(
    species: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    water_clarity: str | None = None,
    water_temp_c: float | None = None,
    time_of_day: str | None = None,
    notes: str | None = None,
    _month: int | None = None,  # injectable for tests
) -> str:
    # Resolve species from profile if not provided
    if not species:
        from src.storage.profile import load_profile

        profile = load_profile()
        targets = profile.target_species
        if not targets:
            return json.dumps(
                {
                    "error": "No species specified and no target species in your profile. "
                    "Add target species to your profile or specify one when asking."
                }
            )
        if len(targets) == 1:
            species = targets[0]
        else:
            return json.dumps(
                {
                    "clarification_needed": True,
                    "message": (
                        "Which species are you targeting today? Your profile lists: "
                        + ", ".join(targets)
                        + ". Specify one and I'll give you a tailored recommendation."
                    ),
                    "options": targets,
                }
            )

    # Auto-fetch conditions when lat/lng available
    temp_c: float | None = water_temp_c
    pressure_trend: str | None = None
    jurisdiction: str | None = None

    if lat is not None and lng is not None:
        try:
            from src.services.weather import get_conditions_for_agent, get_pressure_trend_for_agent

            cond = json.loads(get_conditions_for_agent(lat, lng, "now"))
            jurisdiction = cond.get("jurisdiction")
            if temp_c is None:
                temp_c = cond.get("temperature_c")
            pressure_json = json.loads(get_pressure_trend_for_agent(lat, lng))
            pressure_trend = pressure_json.get("trend")
        except Exception:
            pass  # graceful degradation — rules still run without conditions

    month = _month if _month is not None else datetime.now().month
    season = _season(month)
    group, is_microfishing = _classify(species)

    condition_count = sum(
        [
            temp_c is not None,
            water_clarity is not None,
            pressure_trend is not None,
            time_of_day is not None,
        ]
    )

    if is_microfishing:
        recs = _microfishing_recs(
            species, season, temp_c, pressure_trend, time_of_day, condition_count
        )
    else:
        recs = _standard_recs(
            species,
            group,
            season,
            temp_c,
            water_clarity,
            pressure_trend,
            time_of_day,
            condition_count,
        )

    conditions_dict = {
        "lat": lat,
        "lng": lng,
        "water_temp_c": temp_c,
        "water_clarity": water_clarity,
        "pressure_trend": pressure_trend,
        "time_of_day": time_of_day,
        "season": season,
        "notes": notes,
    }

    try:
        db = get_db()
        rec_id = insert_recommendation(db, species, lat, lng, jurisdiction, conditions_dict, recs)
    except Exception:
        rec_id = None

    return json.dumps(
        {
            "recommendation_id": rec_id,
            "species": species,
            "conditions_used": conditions_dict,
            "recommendations": [r.model_dump() for r in recs],
            "note": (
                "Saved to recommendations log. "
                "When you log a trip that used this recommendation, the feedback loop will update."
                if rec_id is not None
                else "Note: could not save to recommendations log."
            ),
        }
    )
