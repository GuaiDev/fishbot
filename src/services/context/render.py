"""One renderer, for every surface.

The context layer's guarantee is that provenance is a data field rather than a
paragraph of prompt prose. That guarantee survives only as far as the last
place the data is turned into text — so it is turned into text exactly once,
here, and every caller uses this module.

The alternative is each call site formatting its own block, which reproduces
the drift this layer exists to remove: seven copies of the rendering rules,
each free to quietly drop a source or flatten an empty reason into "no data".

Rendering rules, applied uniformly:

  * A value never appears without its provenance.
  * An empty field never renders as absence alone — it renders as *why*.
  * A number never appears without its "so what"; if the translation layer
    has no meaning for it, the number is withheld and the fact that we hold a
    reading is not.
  * Record dates are surfaced, never a confidence score. A 2001 museum
    specimen and a 2022 sighting are not peers and must not read as peers.
"""

from src.models.context import (
    AccessSlice,
    ConditionsSlice,
    ContextField,
    ExploreResponse,
    HistorySlice,
    Place,
    PlaceContext,
    RecordsSlice,
    SpeciesContext,
    SpeciesHistory,
    StructureSlice,
    UserLayer,
    WaterSlice,
)

# A record older than this is called out in the rendering. Not a cutoff and not
# a confidence penalty — the angler weighs it. We only make sure the date is
# impossible to miss, because for a species that may no longer be present the
# date is the only honest signal we have.
_STALE_YEARS = 10


def _line(label: str, field: ContextField) -> str | None:
    """One `label: value [source]` line, or the reason there isn't one.

    Returns None only for fields that were never touched at all — a default
    ContextField with neither value nor reason. Those are slices the bundle
    didn't populate, and printing "unknown" for them would misreport a
    deliberate omission as a gap in the data.
    """
    if field.is_empty and field.empty_reason is None:
        return None
    return f"- {label}: {field.explain()}"


def _block(title: str, lines: list[str | None]) -> str:
    body = [ln for ln in lines if ln]
    if not body:
        return ""
    return "\n".join([f"### {title}", *body])


# -- place ---------------------------------------------------------------------


def render_place(place: Place) -> str:
    bits = [f"**{place.name or place.query}** ({place.lat:.4f}, {place.lng:.4f})"]
    bits.append(f"searched within {place.radius_km:g} km")
    if place.jurisdiction:
        bits.append(place.jurisdiction)
    head = " — ".join(bits)
    if place.resolution_note:
        head += f"\n_{place.resolution_note}_"
    return head


# -- records -------------------------------------------------------------------


def render_records(records: RecordsSlice, today_year: int | None = None) -> str:
    if not records.species:
        reason = records.empty_reason.value if records.empty_reason else "unknown"
        head = [
            "### Species recorded",
            f"Nothing within {records.radius_km:g} km ({reason}). This is a "
            f"statement about the corpus, not about the water.",
        ]
        # The bird proxy still matters here — arguably more than anywhere else.
        # No fish records plus active ospreys is a different situation from no
        # fish records and nothing else either.
        proxy = _line("fish-eating birds", records.piscivore_activity)
        if proxy:
            head.append(proxy)
        return "\n".join(head)

    lines = [f"### Species recorded ({records.total_count} records)"]
    for rec in records.species:
        parts = [rec.species]
        if rec.common_name and rec.common_name.lower() != rec.species.lower():
            parts.append(f"({rec.common_name})")
        detail = " ".join(parts)
        suffix = [f"{rec.count}x"]
        if rec.most_recent:
            suffix.append(f"most recent {rec.most_recent}")
            if _is_stale(rec.most_recent, today_year):
                suffix.append("old record, the fish may no longer be there")
        if rec.is_obscured:
            suffix.append("location fuzzed to ~22 km by the observer's geoprivacy")
        lines.append(f"- {detail}: {', '.join(suffix)} [{rec.provenance.describe()}]")

    if records.escalated_to_web:
        lines.append(
            "- _Some of the above came from a live web search and is unverified._"
        )
    proxy = _line("fish-eating birds", records.piscivore_activity)
    if proxy:
        lines.append(proxy)
    return "\n".join(lines)


def _is_stale(date_text: str, today_year: int | None) -> bool:
    if today_year is None:
        from datetime import UTC, datetime

        today_year = datetime.now(UTC).year
    year = date_text[:4]
    if not year.isdigit():
        return False
    return today_year - int(year) >= _STALE_YEARS


# -- the physical slices -------------------------------------------------------


def render_water(water: WaterSlice) -> str:
    return _block(
        "Water",
        [
            _line("thermal regime", water.thermal_class),
            _line("substrate", water.substrate),
            _line("dissolved oxygen", water.dissolved_oxygen),
            _line("pH", water.ph),
            _line("insect life", water.benthic_health),
        ],
    )


def render_structure(structure: StructureSlice) -> str:
    return _block(
        "Structure",
        [
            _line("barriers upstream", structure.barriers_upstream),
            _line("barriers downstream", structure.barriers_downstream),
            _line("confluence", structure.is_confluence),
            _line("connects to", structure.waterbody_connection),
            _line("stream order", structure.stream_order),
        ],
    )


def render_access(access: AccessSlice) -> str:
    return _block(
        "Access",
        [
            _line("parking", access.parking),
            _line("trails", access.trails),
            _line("crown land", access.crown_land),
            _line("note", access.access_note),
        ],
    )


def render_conditions(conditions: ConditionsSlice) -> str:
    return _block(
        "Conditions now",
        [
            _line("flow vs median", conditions.flow_vs_median),
            _line("water temp", conditions.water_temp_c),
            _line("air temp", conditions.air_temp_c),
            _line("pressure", conditions.pressure_trend),
        ],
    )


def render_history(history: HistorySlice) -> str:
    """The user's own record here — including the blanks.

    Blanks are printed as a first-class number rather than implied by
    subtraction. They are half the analytical signal and the product does not
    treat them as a failure state to be tidied away.
    """
    if history.visits == 0:
        reason = (
            history.empty_reason.value if history.empty_reason else "no visits logged"
        )
        return f"### Your history here\nNone ({reason})."

    lines = [
        "### Your history here",
        f"- {history.visits} visit(s): {history.productive_visits} productive, "
        f"{history.blanks} blank",
    ]
    if history.last_visit:
        lines.append(f"- last visit: {history.last_visit}")
    if history.species_caught:
        lines.append(f"- caught here: {', '.join(history.species_caught)}")
    if history.techniques_used:
        lines.append(f"- techniques tried: {', '.join(history.techniques_used)}")
    return "\n".join(lines)


# -- whole contexts ------------------------------------------------------------


def render_place_context(ctx: PlaceContext) -> str:
    """The full block for one place, in the order an angler reads it."""
    sections = [render_place(ctx.place)]
    if ctx.records is not None:
        sections.append(render_records(ctx.records))
    if ctx.water is not None:
        sections.append(render_water(ctx.water))
    if ctx.structure is not None:
        sections.append(render_structure(ctx.structure))
    if ctx.access is not None:
        sections.append(render_access(ctx.access))
    if ctx.conditions is not None:
        sections.append(render_conditions(ctx.conditions))
    if ctx.history is not None:
        sections.append(render_history(ctx.history))
    return "\n\n".join(s for s in sections if s)


def render_species_context(ctx: SpeciesContext) -> str:
    if not ctx.found:
        return f"### {ctx.species}\nNot in the local species file. {ctx.sar_reason}"

    head = ctx.species
    if ctx.scientific_name and ctx.scientific_name.lower() != ctx.species.lower():
        head += f" (*{ctx.scientific_name}*)"

    lines = [f"### {head}"]
    if ctx.sar_alert:
        # Rendered before anything else and never as a footnote: SAR law
        # prohibits capture, not just possession, so catch-and-release is not
        # an exemption and the reader has to see this before the habitat note.
        lines.append(f"- **Conservation flag: {ctx.sar_reason}**")
        if ctx.status_known_listed:
            lines.append(
                "- Do not suggest how to target this species. Handling guidance only."
            )
        else:
            # No affirmative listing signal, only an unverified status. The
            # corpus's own angling text stays withheld — it was generated, not
            # sourced — but the caution is a caution, not a refusal.
            lines.append(
                "- No listing is asserted for this species, but the status is "
                "unverified. Our stored angling notes are withheld as unsourced; "
                "tell the angler to confirm the current listing before targeting."
            )
    for label, field in (
        ("conservation status", ctx.conservation_status),
        ("habitat", ctx.habitat_note),
        ("angling note", ctx.angling_note),
        ("native to Ontario", ctx.native_to_ontario),
    ):
        line = _line(label, field)
        if line:
            lines.append(line)
    return "\n".join(lines)


def render_explore(response: ExploreResponse) -> str:
    if not response.results:
        reason = (
            response.empty_reason.value if response.empty_reason else "no candidates"
        )
        return f"### Exploration candidates\nNone ({reason})."

    lines = ["### Exploration candidates", f"_{response.scoring_note}_", ""]
    for i, r in enumerate(response.results, 1):
        name = r.name or f"unnamed segment {r.ogf_id}"
        bits = [f"score {r.score:.3f}"]
        if r.stream_order is not None:
            bits.append(f"order {r.stream_order}")
        bits.append(f"pressure {r.observation_pressure:.2f}")
        # Same call every other value in the layer gets. The three access
        # states are ordinary ContextField states, so their wording comes from
        # _EMPTY_PHRASING rather than from three branches invented here.
        bits.append(f"access {r.access.explain()}")
        if r.is_confluence:
            bits.append("confluence")
        lines.append(f"{i}. {name} ({r.lat:.4f}, {r.lng:.4f}) — {', '.join(bits)}")

    total = len(response.results)
    if response.results_on_placeholder_access:
        lines.append(
            f"\n_Access is unmapped for {response.results_on_placeholder_access} "
            f"of these {total}: nobody has surveyed roads or parking that far "
            f"out, so there is no figure to give. What ranked them — how little "
            f"has been reported there, the structure, the remoteness — is real._"
        )
    if response.results_with_unknown_access_coverage:
        # A gap in our pipeline, not in the world. Different remedy, so it gets
        # different words; the shell command that fixes it belongs in the log,
        # not in something an angler reads.
        lines.append(
            f"\n_For {response.results_with_unknown_access_coverage} of these "
            f"{total}, the stored access figures predate the record of where "
            f"access was actually surveyed, so it cannot be said whether they "
            f"mean anything. Recomputing access scores would settle it._"
        )

    if response.tied_at_top > len(response.results):
        # Without a habitat term the surviving signals are coarse, so ties are
        # large. Presenting ten of a thousand equally-ranked segments as "the
        # best" would be a precision claim the score cannot support.
        lines.append(
            f"\n_{response.tied_at_top} candidates share the top score — the "
            f"ordering within that group is arbitrary, not a ranking._"
        )
    if response.excluded_count:
        lines.append(
            f"\n_{response.excluded_count} candidate(s) excluded by the "
            f"physical-plausibility gate._"
        )
        for ex in response.excluded_examples:
            lines.append(f"  - {ex}")
    return "\n".join(lines)


def render_user_layer(layer: UserLayer) -> str:
    """The derived layer, with the epistemic rule visible in the output.

    Patterns that lack a comparison set are still printed, marked as not yet
    claimable. Hiding them would leave the caller unable to say "one session
    is a hypothesis, not a rule" — which is more useful than silence.
    """
    if layer.total_stops == 0:
        return "### This angler\nNo trips logged yet."

    lines = [
        "### This angler",
        f"- {layer.total_sessions} session(s), {layer.total_stops} stop(s)",
    ]
    if layer.blank_rate is not None:
        lines.append(f"- blank rate: {layer.blank_rate:.0%}")
    lines.append(f"- demonstrated expertise: {layer.expertise}")
    if layer.target_species:
        lines.append(
            f"- appears to target (from logs, not configured): "
            f"{', '.join(layer.target_species)}"
        )
    if layer.species_logged:
        lines.append(f"- species logged: {', '.join(layer.species_logged)}")

    if layer.patterns:
        lines.append("- personal patterns:")
        for p in layer.patterns:
            mark = "claimable" if p.is_claimable else "NOT yet claimable"
            lines.append(
                f"  - {p.statement} (n={p.sample_size} vs {p.comparison_size}, "
                f"{p.confidence} confidence, {mark})"
            )
    if layer.known_gaps:
        lines.append("- known gaps:")
        for g in layer.known_gaps:
            lines.append(f"  - {g}")
    return "\n".join(lines)


def render_species_history(history: SpeciesHistory) -> str:
    """The angler's own record with one species.

    Catches and blanks both, and the blank count arrives with its caveat
    attached rather than as a bare number the reader will over-interpret.
    """
    if history.caught_stops == 0 and history.blank_stops == 0 and not history.insights:
        reason = (
            history.empty_reason.value
            if history.empty_reason
            else "nothing logged"
        )
        return f"### Your record with {history.species}\nNothing logged ({reason})."

    lines = [f"### Your record with {history.species}"]
    if history.caught_stops:
        lines.append(f"- caught on {history.caught_stops} stop(s)")
        if history.last_caught:
            lines.append(f"- last caught: {history.last_caught}")
        if history.locations:
            lines.append(f"- where: {', '.join(history.locations)}")
        lines.append("- what worked:")
        for setup in history.productive_setups:
            lines.append(f"  - {setup}")
    else:
        lines.append("- never logged a catch of this species")

    lines.append(
        f"- {history.blank_stops} blank stop(s) in the log overall — targeting is "
        f"not always recorded, so this is an upper bound on 'tried and failed', "
        f"not a count of it"
    )

    if history.insights:
        lines.append("- stored insights:")
        for ins in history.insights:
            line = f"  - [{ins.confidence}] {ins.conclusion} [{ins.provenance.describe()}]"
            lines.append(line)
            if ins.recommendation:
                lines.append(f"    recommendation: {ins.recommendation}")
    return "\n".join(lines)
