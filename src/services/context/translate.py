"""Static raw-value → plain-language lookup.

A number without a "so what" is noise dressed as rigour. Every translator here
returns None when it cannot say something an angler could act on, and callers
drop the value entirely in that case.

This is a lookup, not an LLM call, and it lives in one place so that seven
callers do not each reinvent what "EPT 0.42" means.
"""


def substrate(category: str | None) -> str | None:
    """Surficial geology → what it does to the water."""
    if not category:
        return None
    match category.strip().lower():
        case "bedrock":
            return "runs clearer and holds temperature better than soft-bottom reaches"
        case "coarse":
            return "gravel and cobble — spawning substrate, and it holds insect life"
        case "mixed":
            return "varied bottom, so holding water changes character reach to reach"
        case "fine":
            return "silt and sand — turbid after rain, fewer clean spawning beds"
        case "organic":
            return "mucky bottom typical of wetland reaches — warmer, lower oxygen"
    return None


def barriers(upstream: int | None, downstream: int | None) -> str | None:
    """Barrier counts → how fish actually move through the reach."""
    if upstream is None and downstream is None:
        return None
    up = upstream or 0
    down = downstream or 0
    if up == 0 and down == 0:
        return "no mapped barriers either way — fish can move through freely"
    if up > 0 and down == 0:
        return "fish move up from the river below, then stack under the dam"
    if down > 0 and up == 0:
        return "cut off from downstream water — whatever is here is resident"
    return "barriers both ways — this reach is largely its own population"


def ept_proportion(value: float | None) -> str | None:
    """EPT share of the benthic community → year-round carrying capacity."""
    if value is None:
        return None
    if value >= 0.40:
        return "healthy insect life, holds fish year-round"
    if value >= 0.20:
        return "moderate insect life — supports fish but not densely"
    return "sparse mayfly/stonefly/caddis presence, a sign of degraded water"


def dissolved_oxygen(mgl: float | None) -> str | None:
    """DO → a hard constraint, never a presence indicator."""
    if mgl is None:
        return None
    if mgl < 4.0:
        return "below the floor for a persistent fish community"
    if mgl < 6.0:
        return "low — tolerant species only (bullhead, carp, sucker)"
    if mgl >= 9.0:
        return "well oxygenated, cold enough for trout if temperature agrees"
    return "adequate for most warmwater and coolwater species"


def thermal_regime(regime: str | None) -> str | None:
    if not regime or regime.strip().lower() == "unknown":
        return None
    match regime.strip().lower():
        case "coldwater":
            return "trout and salmon water"
        case "coolwater":
            return "pike, walleye and smallmouth water"
        case "warmwater":
            return "bass, panfish and catfish water"
    return None


def ph(value: float | None) -> str | None:
    """Only worth surfacing at the extremes."""
    if value is None:
        return None
    if value < 5.5:
        return "acidic enough to limit which species persist"
    if value > 9.0:
        return "unusually alkaline — stressful for most freshwater species"
    return None  # 5.5-9.0 is unremarkable; saying so wastes the reader's time


def flow_vs_median(ratio: float | None) -> str | None:
    """Current flow as a multiple of seasonal median."""
    if ratio is None:
        return None
    if ratio >= 2.0:
        return "well above normal — likely blown out and unfishable"
    if ratio >= 1.3:
        return "up on normal, so fish will hold tighter to the edges"
    if ratio <= 0.5:
        return "very low and clear — fish will be spooky, go lighter"
    if ratio <= 0.8:
        return "below normal, concentrating fish into the deeper holds"
    return "around seasonal normal"


def pressure_trend(trend: str | None) -> str | None:
    if not trend:
        return None
    match trend.strip().lower():
        case "falling":
            return "falling pressure ahead of weather often triggers a feeding window"
        case "rising":
            return "rising pressure after a front usually means a slower bite"
        case "steady":
            return None  # steady pressure implies nothing actionable
    return None


def stream_order(order: int | None) -> str | None:
    if order is None:
        return None
    if order <= 2:
        return "a small headwater reach — in urban areas these are often culverted"
    if order <= 4:
        return "a mid-size stream, wadeable in most conditions"
    return "a substantial river reach"


# Values we deliberately never surface: no honest "so what" exists for an
# angler, so showing the number would be rigour theatre.
def conductivity(_value: float | None) -> None:
    """Always None. Kept as a named function so the omission is explicit."""
    return None


def turbidity_fnu(_value: float | None) -> None:
    """Always None — the clarity proxy anglers use is visual, not FNU."""
    return None
