"""Slice builders for describe().

Each builder returns a populated slice or a slice whose fields carry a
specific empty_reason. None of them ever returns a bare "no data" — the four
empty cases render differently on every surface, so they stay distinct all
the way through.
"""

import json
import logging

from sqlite_utils import Database

from src.models.context import (
    AccessSlice,
    ConditionsSlice,
    ContextField,
    EmptyReason,
    HistorySlice,
    Place,
    Provenance,
    ProvenanceKind,
    RecordsSlice,
    SpeciesRecord,
    StructureSlice,
    WaterSlice,
)
from src.services.context import translate

logger = logging.getLogger(__name__)

_KM_PER_DEGREE = 111.0


# ── records (the only escalating slice) ───────────────────────────────────────


def build_records(
    db: Database,
    place: Place,
    species_filter: str | None = None,
    days_back: int = 3650,
    user_id: int = 1,
) -> RecordsSlice:
    """Species recorded at this place, from every grounded source we hold."""
    found: dict[str, SpeciesRecord] = {}

    for rec in _inat_records(db, place, species_filter, days_back):
        _merge(found, rec)
    for rec in _gbif_records(db, place, species_filter):
        _merge(found, rec)
    for rec in _user_catch_records(db, place, species_filter, user_id):
        _merge(found, rec)

    if not found:
        return RecordsSlice(
            radius_km=place.radius_km,
            empty_reason=_no_records_reason(db),
        )

    ordered = sorted(found.values(), key=lambda r: (-r.count, r.species))
    return RecordsSlice(
        species=ordered,
        total_count=sum(r.count for r in ordered),
        radius_km=place.radius_km,
    )


def _no_records_reason(db: Database) -> EmptyReason:
    """Distinguish 'nothing here' from 'we hold nothing for this area at all'."""
    for table in ("observations", "gbif_observations"):
        if table in db.table_names() and db[table].count > 0:
            return EmptyReason.NO_RECORDS_IN_RADIUS
    return EmptyReason.SOURCE_DOES_NOT_COVER_AREA


def _merge(found: dict[str, SpeciesRecord], rec: SpeciesRecord) -> None:
    key = rec.species.strip().lower()
    existing = found.get(key)
    if existing is None:
        found[key] = rec
        return
    existing.count += rec.count
    if rec.most_recent and (
        existing.most_recent is None or rec.most_recent > existing.most_recent
    ):
        existing.most_recent = rec.most_recent
    # A precise record beats an obscured one for the same species.
    if existing.is_obscured and not rec.is_obscured:
        existing.is_obscured = False
        existing.provenance = rec.provenance


def _inat_records(
    db: Database, place: Place, species_filter: str | None, days_back: int
) -> list[SpeciesRecord]:
    if "observations" not in db.table_names():
        return []
    try:
        from src.storage.observations import query_observations

        obs, _ = query_observations(
            db,
            lat=place.lat,
            lng=place.lng,
            radius_km=place.radius_km,
            days_back=days_back,
            species_filter=species_filter,
            limit=200,
        )
    except Exception:  # noqa: BLE001 - a slice failure must not kill describe()
        logger.warning("iNaturalist slice failed", exc_info=True)
        return []

    out = []
    for o in obs:
        source = getattr(o, "source", None) or "iNaturalist"
        out.append(
            SpeciesRecord(
                species=o.species,
                common_name=getattr(o, "common_name", None),
                most_recent=str(getattr(o, "observed_on", "") or "") or None,
                is_obscured=bool(getattr(o, "is_obscured", False)),
                provenance=Provenance(
                    kind=ProvenanceKind.RECORD,
                    source=source,
                    date=str(getattr(o, "observed_on", "") or "") or None,
                ),
            )
        )
    return out


def _gbif_records(
    db: Database, place: Place, species_filter: str | None
) -> list[SpeciesRecord]:
    if "gbif_observations" not in db.table_names():
        return []
    try:
        from src.storage.gbif_observations import query_gbif_observations

        obs = query_gbif_observations(
            db,
            lat=place.lat,
            lng=place.lng,
            radius_km=place.radius_km,
            species_filter=species_filter,
        )
    except Exception:  # noqa: BLE001
        logger.warning("GBIF slice failed", exc_info=True)
        return []

    return [
        SpeciesRecord(
            species=o.species,
            common_name=getattr(o, "common_name", None),
            most_recent=str(getattr(o, "observed_on", "") or "") or None,
            provenance=Provenance(
                kind=ProvenanceKind.RECORD,
                source=f"GBIF/{getattr(o, 'dataset_name', '') or 'occurrence'}",
                date=str(getattr(o, "observed_on", "") or "") or None,
            ),
        )
        for o in obs
    ]


def _user_catch_records(
    db: Database, place: Place, species_filter: str | None, user_id: int
) -> list[SpeciesRecord]:
    """The user's own confirmed catches — the most trustworthy source there is."""
    if "stops" not in db.table_names():
        return []
    deg = place.radius_km / _KM_PER_DEGREE
    rows = list(
        db.execute(
            "SELECT st.species_caught, s.date "
            "FROM stops st JOIN sessions s ON st.session_id = s.id "
            "WHERE st.user_id = ? AND st.lat BETWEEN ? AND ? AND st.lng BETWEEN ? AND ?",
            [
                user_id,
                place.lat - deg,
                place.lat + deg,
                place.lng - deg,
                place.lng + deg,
            ],
        ).fetchall()
    )

    out: list[SpeciesRecord] = []
    for species_json, date in rows:
        for sp in _load_species_list(species_json):
            if species_filter and species_filter.lower() not in sp.lower():
                continue
            out.append(
                SpeciesRecord(
                    species=sp,
                    most_recent=str(date) if date else None,
                    provenance=Provenance(
                        kind=ProvenanceKind.RECORD,
                        source="your logged catch",
                        date=str(date) if date else None,
                    ),
                )
            )
    return out


def _load_species_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(s) for s in parsed] if isinstance(parsed, list) else []


# ── water ─────────────────────────────────────────────────────────────────────


def build_water(db: Database, place: Place) -> WaterSlice:
    slice_ = WaterSlice()
    _fill_thermal(db, place, slice_)
    _fill_substrate(db, place, slice_)
    _fill_chemistry(db, place, slice_)
    _fill_benthic(db, place, slice_)
    return slice_


def _fill_thermal(db: Database, place: Place, out: WaterSlice) -> None:
    if "stream_temperature_summaries" not in db.table_names():
        out.thermal_class = ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
        return
    try:
        from src.storage.stream_temperature import query_temperature_summaries

        rows = query_temperature_summaries(
            db, lat=place.lat, lng=place.lng, radius_km=max(place.radius_km, 25.0)
        )
    except Exception:  # noqa: BLE001
        logger.warning("thermal slice failed", exc_info=True)
        rows = []

    for r in rows:
        regime = getattr(r, "thermal_regime", None)
        meaning = translate.thermal_regime(regime)
        if meaning:
            out.thermal_class = ContextField.recorded(
                regime, source=f"DFO station {getattr(r, 'station_id', '?')}", meaning=meaning
            )
            return
    out.thermal_class = ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)


def _fill_substrate(db: Database, place: Place, out: WaterSlice) -> None:
    if "geology_units" not in db.table_names():
        out.substrate = ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
        return
    try:
        from src.storage.geology import query_substrate_at_point

        unit = query_substrate_at_point(db, place.lat, place.lng)
    except Exception:  # noqa: BLE001
        logger.warning("substrate slice failed", exc_info=True)
        unit = None

    if unit is None:
        out.substrate = ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)
        return

    category = getattr(unit, "substrate_category", None) or getattr(unit, "unit_type", None)
    meaning = translate.substrate(category)
    out.substrate = (
        ContextField.recorded(category, source="Ontario surficial geology", meaning=meaning)
        if meaning
        else ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)
    )


def _fill_chemistry(db: Database, place: Place, out: WaterSlice) -> None:
    if "water_quality_readings" not in db.table_names():
        out.dissolved_oxygen = ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
        out.ph = ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
        return
    try:
        from src.storage.water_quality import query_water_quality

        rows = query_water_quality(
            db, lat=place.lat, lng=place.lng, radius_km=max(place.radius_km, 25.0)
        )
    except Exception:  # noqa: BLE001
        logger.warning("chemistry slice failed", exc_info=True)
        rows = []

    do_vals = [r.do_mgl for r in rows if getattr(r, "do_mgl", None) is not None]
    ph_vals = [r.ph for r in rows if getattr(r, "ph", None) is not None]

    if do_vals:
        median = sorted(do_vals)[len(do_vals) // 2]
        out.dissolved_oxygen = ContextField.recorded(
            round(float(median), 1),
            source=f"PWQMN ({len(do_vals)} readings)",
            meaning=translate.dissolved_oxygen(float(median)),
        )
    else:
        out.dissolved_oxygen = ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)

    if ph_vals:
        median = sorted(ph_vals)[len(ph_vals) // 2]
        meaning = translate.ph(float(median))
        # pH between 5.5 and 9.0 has no actionable meaning; don't surface it.
        out.ph = (
            ContextField.recorded(
                round(float(median), 1), source="PWQMN", meaning=meaning
            )
            if meaning
            else ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)
        )
    else:
        out.ph = ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)


def _fill_benthic(db: Database, place: Place, out: WaterSlice) -> None:
    if "benthic_samples" not in db.table_names():
        out.benthic_health = ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
        return
    try:
        from src.storage.benthic import query_benthic

        rows = query_benthic(
            db, lat=place.lat, lng=place.lng, radius_km=max(place.radius_km, 25.0)
        )
    except Exception:  # noqa: BLE001
        logger.warning("benthic slice failed", exc_info=True)
        rows = []

    vals = [
        r.ept_proportion for r in rows if getattr(r, "ept_proportion", None) is not None
    ]
    if not vals:
        out.benthic_health = ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)
        return
    mean = sum(float(v) for v in vals) / len(vals)
    out.benthic_health = ContextField.recorded(
        round(mean, 2),
        source=f"CABIN ({len(vals)} samples)",
        meaning=translate.ept_proportion(mean),
    )


# ── structure ─────────────────────────────────────────────────────────────────


def build_structure(db: Database, place: Place) -> StructureSlice:
    out = StructureSlice()

    order = _stream_order(db, place)
    out.stream_order = (
        ContextField.recorded(order, source="OHN", meaning=translate.stream_order(order))
        if order is not None
        else ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
    )

    if "barriers" not in db.table_names():
        empty = ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
        out.barriers_upstream = empty
        out.barriers_downstream = empty
        return out

    up, down = _barrier_counts(db, place)
    meaning = translate.barriers(up, down)
    out.barriers_upstream = ContextField.recorded(up, source="OHN barriers", meaning=meaning)
    out.barriers_downstream = ContextField.recorded(down, source="OHN barriers")
    return out


def _stream_order(db: Database, place: Place) -> int | None:
    if "stream_segments" not in db.table_names() or not place.segment_ids:
        return None
    rows = list(
        db["stream_segments"].rows_where(
            f"ogf_id IN ({','.join('?' * len(place.segment_ids))})",
            place.segment_ids,
        )
    )
    orders = [r["stream_order"] for r in rows if r.get("stream_order") is not None]
    return max(int(o) for o in orders) if orders else None


def _barrier_counts(db: Database, place: Place) -> tuple[int, int]:
    """Barriers near this place, split by whether they sit up- or downstream.

    Without a traversal of the connectivity graph this is a latitude proxy:
    upstream is inland/higher, downstream is toward the outlet. Good enough to
    say "fish stack below the dam"; not good enough to count fish passage.
    """
    deg = max(place.radius_km, 10.0) / _KM_PER_DEGREE
    rows = list(
        db["barriers"].rows_where(
            "nearest_segment_ogf_id IS NOT NULL", [], limit=5000
        )
    )
    up = down = 0
    for r in rows:
        blat, blng = _barrier_point(r)
        if blat is None or blng is None:
            continue
        if abs(blat - place.lat) > deg or abs(blng - place.lng) > deg:
            continue
        if blat > place.lat:
            up += 1
        else:
            down += 1
    return up, down


def _barrier_point(row: dict) -> tuple[float | None, float | None]:
    for lat_key, lng_key in (("lat", "lng"), ("centroid_lat", "centroid_lng")):
        if row.get(lat_key) is not None and row.get(lng_key) is not None:
            return float(row[lat_key]), float(row[lng_key])
    wkt = row.get("geom_wkt")
    if not wkt or "(" not in wkt:
        return None, None
    try:
        inner = wkt[wkt.index("(") + 1 : wkt.rindex(")")].strip("() ")
        parts = inner.split(",")[0].split()
        return float(parts[1]), float(parts[0])
    except (ValueError, IndexError):
        return None, None


# ── access ────────────────────────────────────────────────────────────────────


def build_access(db: Database, place: Place) -> AccessSlice:
    out = AccessSlice()
    deg = max(place.radius_km, 2.0) / _KM_PER_DEGREE

    if "access_points" not in db.table_names():
        empty = ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
        out.parking = empty
        out.trails = empty
    else:
        rows = list(
            db["access_points"].rows_where(
                "lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                [place.lat - deg, place.lat + deg, place.lng - deg, place.lng + deg],
                limit=200,
            )
        )
        parking = [r for r in rows if "park" in str(r.get("access_type", "")).lower()]
        trails = [
            r
            for r in rows
            if any(k in str(r.get("access_type", "")).lower() for k in ("path", "trail", "track"))
        ]
        out.parking = (
            ContextField.recorded(
                len(parking), source="OpenStreetMap", meaning="somewhere to leave the car"
            )
            if parking
            else ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)
        )
        out.trails = (
            ContextField.recorded(len(trails), source="OpenStreetMap")
            if trails
            else ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)
        )

    out.crown_land = _crown_land(db, place)
    return out


def _crown_land(db: Database, place: Place) -> ContextField:
    if "crown_land" not in db.table_names():
        return ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
    deg = place.radius_km / _KM_PER_DEGREE
    rows = list(
        db["crown_land"].rows_where(
            "centroid_lat BETWEEN ? AND ? AND centroid_lng BETWEEN ? AND ?",
            [place.lat - deg, place.lat + deg, place.lng - deg, place.lng + deg],
            limit=5,
        )
    )
    if rows:
        return ContextField.recorded(
            True,
            source="Ontario Crown Land",
            meaning="public access generally permitted — verify no local restriction",
        )
    return ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)


# ── conditions (live — never cached beyond an hour) ───────────────────────────


def build_conditions(db: Database, place: Place, fetch_live: bool = True) -> ConditionsSlice:
    out = ConditionsSlice()
    if not fetch_live:
        empty = ContextField.empty(EmptyReason.SOURCE_DOES_NOT_COVER_AREA)
        out.air_temp_c = empty
        out.pressure_trend = empty
        out.flow_vs_median = empty
        return out

    try:
        from src.services.weather import get_conditions_for_agent

        raw = json.loads(get_conditions_for_agent(lat=place.lat, lng=place.lng))
    except Exception:  # noqa: BLE001 - live fetch must never break describe()
        logger.warning("conditions slice failed", exc_info=True)
        raw = {}

    temp = raw.get("temperature_c") or raw.get("air_temp_c")
    if temp is not None:
        out.air_temp_c = ContextField.recorded(temp, source="Open-Meteo")

    trend = raw.get("pressure_trend")
    meaning = translate.pressure_trend(trend)
    if trend:
        out.pressure_trend = ContextField.recorded(
            trend, source="Open-Meteo", meaning=meaning
        )
    else:
        out.pressure_trend = ContextField.empty(EmptyReason.NO_RECORDS_IN_RADIUS)

    return out


# ── history ───────────────────────────────────────────────────────────────────


def build_history(db: Database, place: Place, user_id: int = 1) -> HistorySlice:
    """The user's own record at this place — including blanks.

    Blanks are half the analytical signal and the hardest behaviour to get,
    so they are counted explicitly rather than inferred from absence.
    """
    if "stops" not in db.table_names():
        return HistorySlice(empty_reason=EmptyReason.USER_NEVER_FISHED_HERE)

    deg = place.radius_km / _KM_PER_DEGREE
    rows = list(
        db.execute(
            "SELECT st.species_caught, st.was_productive, st.technique, s.date "
            "FROM stops st JOIN sessions s ON st.session_id = s.id "
            "WHERE st.user_id = ? AND st.lat BETWEEN ? AND ? AND st.lng BETWEEN ? AND ?",
            [
                user_id,
                place.lat - deg,
                place.lat + deg,
                place.lng - deg,
                place.lng + deg,
            ],
        ).fetchall()
    )
    if not rows:
        return HistorySlice(empty_reason=EmptyReason.USER_NEVER_FISHED_HERE)

    species: set[str] = set()
    techniques: set[str] = set()
    productive = blanks = 0
    last: str | None = None

    for species_json, was_productive, technique, date in rows:
        caught = _load_species_list(species_json)
        species.update(caught)
        if technique:
            techniques.add(str(technique))
        if was_productive:
            productive += 1
        else:
            blanks += 1
        if date and (last is None or str(date) > last):
            last = str(date)

    return HistorySlice(
        visits=len(rows),
        productive_visits=productive,
        blanks=blanks,
        species_caught=sorted(species),
        last_visit=last,
        techniques_used=sorted(techniques),
    )
