"""Entry point for the fishbot CLI."""

from datetime import date as date_type

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.agent.chat import run_chat
from src.models.catch import Catch
from src.models.profile import Location, UserProfile
from src.models.trip import Trip
from src.storage.database import get_db
from src.storage.profile import load_profile, save_profile
from src.storage.trips import insert_trip, recent_trips

app = typer.Typer(name="fishbot", help="Personal fishing exploration bot.")
console = Console()


@app.command()
def run() -> None:
    """Start the fishing bot chat."""
    run_chat()


@app.command()
def log() -> None:
    """Interactively log a fishing trip."""
    profile = load_profile()
    today = date_type.today().isoformat()

    trip_date_str = typer.prompt("Date (YYYY-MM-DD)", default=today)
    location_name = typer.prompt("Location name (lake/river)")
    jurisdiction = typer.prompt(
        "Jurisdiction (ISO 3166-2, e.g. CA-ON)",
        default=profile.home_jurisdiction,
    )
    lat_raw = typer.prompt("Latitude (blank to skip)", default="", show_default=False)
    lng_raw = typer.prompt("Longitude (blank to skip)", default="", show_default=False)

    catches: list[Catch] = []
    if typer.confirm("Any catches?", default=False):
        while True:
            species = typer.prompt("  Species (blank to stop)", default="", show_default=False)
            if not species:
                break
            length_raw = typer.prompt("  Length cm (blank to skip)", default="", show_default=False)
            weight_raw = typer.prompt("  Weight kg (blank to skip)", default="", show_default=False)
            released = typer.confirm("  Released?", default=True)
            catches.append(
                Catch(
                    species=species,
                    length_cm=float(length_raw) if length_raw else None,
                    weight_kg=float(weight_raw) if weight_raw else None,
                    released=released,
                )
            )

    gear_used_raw = typer.prompt("Gear used (comma-separated)", default="", show_default=False)
    conditions_notes = typer.prompt("Conditions (free text)", default="", show_default=False)
    what_worked = typer.prompt("What worked", default="", show_default=False)
    what_didnt = typer.prompt("What didn't", default="", show_default=False)
    notes = typer.prompt("General notes", default="", show_default=False)

    trip = Trip(
        date=date_type.fromisoformat(trip_date_str),
        jurisdiction=jurisdiction,
        location_name=location_name,
        lat=float(lat_raw) if lat_raw else None,
        lng=float(lng_raw) if lng_raw else None,
        species_caught=catches,
        gear_used=[g.strip() for g in gear_used_raw.split(",") if g.strip()],
        conditions={"notes": conditions_notes} if conditions_notes else {},
        notes=notes,
        what_worked=what_worked,
        what_didnt=what_didnt,
    )

    db = get_db()
    trip_id = insert_trip(db, trip)
    console.print(f"[green]Saved trip #{trip_id}[/green] — {location_name} on {trip_date_str}")


@app.command()
def recent(
    limit: int = typer.Option(10, "--limit", "-n", help="How many trips to show"),
) -> None:
    """Show recent trips."""
    db = get_db()
    trips = recent_trips(db, limit=limit)
    if not trips:
        console.print("[dim]No trips logged yet. Run `fishbot log` to record one.[/dim]")
        return

    table = Table(title=f"Recent trips ({len(trips)})")
    table.add_column("Date")
    table.add_column("Location")
    table.add_column("Jurisdiction")
    table.add_column("Caught")
    table.add_column("Notes", overflow="fold")
    for t in trips:
        species = ", ".join(c.species for c in t.species_caught) if t.species_caught else "skunked"
        notes_bits = [t.what_worked, t.what_didnt, t.notes]
        notes_combined = " | ".join(s for s in notes_bits if s)
        table.add_row(
            t.date.isoformat(),
            t.location_name,
            t.jurisdiction,
            species,
            notes_combined,
        )
    console.print(table)


@app.command()
def profile() -> None:
    """View and optionally edit your fishing profile."""
    p = load_profile()
    _print_profile(p)

    if not typer.confirm("Edit profile?", default=False):
        return

    home_jurisdiction = typer.prompt("Home jurisdiction (ISO 3166-2)", default=p.home_jurisdiction)
    home_name = typer.prompt(
        "Home location name",
        default=p.home_location.name if p.home_location else "",
    )
    home_lat_raw = typer.prompt(
        "Home latitude",
        default=str(p.home_location.lat) if p.home_location else "",
    )
    home_lng_raw = typer.prompt(
        "Home longitude",
        default=str(p.home_location.lng) if p.home_location else "",
    )
    target_species_raw = typer.prompt(
        "Target species (comma-separated)",
        default=", ".join(p.target_species),
    )
    fishing_style = typer.prompt("Fishing style", default=p.fishing_style)
    skill_level = typer.prompt("Skill level", default=p.skill_level)
    preferences = typer.prompt("Preferences (free text)", default=p.preferences)

    home_location = None
    if home_name and home_lat_raw and home_lng_raw:
        home_location = Location(
            name=home_name,
            lat=float(home_lat_raw),
            lng=float(home_lng_raw),
        )

    updated = UserProfile(
        home_jurisdiction=home_jurisdiction,
        frequented_jurisdictions=p.frequented_jurisdictions,
        home_location=home_location,
        target_species=[s.strip() for s in target_species_raw.split(",") if s.strip()],
        gear=p.gear,
        budget=p.budget,
        skill_level=skill_level,
        fishing_style=fishing_style,
        preferences=preferences,
    )
    save_profile(updated)
    console.print("[green]Profile saved.[/green]")


@app.command()
def ingest(
    radius_km: float = typer.Option(50.0, "--radius", help="Search radius in km"),
    days_back: int = typer.Option(90, "--days", help="How many days of iNaturalist history to pull"),  # noqa: E501
) -> None:
    """Pull fish observations from iNaturalist and GBIF near your home location."""
    from src.services.gbif import fetch_and_store as gbif_fetch_and_store
    from src.services.observations import fetch_and_store as inat_fetch_and_store
    from src.services.osm import fetch_and_store as osm_fetch_and_store
    from src.services.stream_gauge import fetch_and_store as wsc_fetch_and_store

    profile = load_profile()
    if not profile.home_location:
        console.print(
            "[red]Home location not set. Run `fishbot profile` and enter your coordinates.[/red]"
        )
        raise typer.Exit(1)

    loc = profile.home_location

    console.print(
        f"[dim]Fetching iNaturalist observations within {radius_km}km of {loc.name}, "
        f"last {days_back} days…[/dim]"
    )
    inat_count = inat_fetch_and_store(loc.lat, loc.lng, radius_km=radius_km, days_back=days_back)

    console.print(
        f"[dim]Fetching GBIF institutional records (museum specimens, surveys) "
        f"within {radius_km}km of {loc.name}…[/dim]"
    )
    gbif_count = gbif_fetch_and_store(loc.lat, loc.lng, radius_km=radius_km)

    console.print(
        f"[dim]Fetching WSC stream gauge readings within {radius_km:.0f}km of {loc.name}…[/dim]"
    )
    wsc_count = wsc_fetch_and_store(loc.lat, loc.lng, radius_km=radius_km)

    console.print(
        f"[dim]Fetching OSM water features (50km) and access points (25km) "
        f"near {loc.name}…[/dim]"
    )
    osm_water_count, osm_access_count = osm_fetch_and_store(loc.lat, loc.lng)

    console.print("[dim]Downloading MNRF fish stocking records (30-day cache)…[/dim]")
    from src.services.stocking import ingest_stocking_data
    stocking_count = ingest_stocking_data()

    console.print("[dim]Loading Ontario species range database…[/dim]")
    from src.services.species_ranges import load_and_store as species_load_and_store
    species_count = species_load_and_store()

    console.print("[dim]Fetching Reddit fishing community posts (r/OntarioFishing + others)…[/dim]")
    from src.services.reddit import fetch_and_store as reddit_fetch_and_store
    reddit_count = reddit_fetch_and_store()

    console.print(
        f"[dim]Fetching Ontario Hydro Network stream segments and barriers "
        f"({radius_km:.0f}km bbox)…[/dim]"
    )
    from src.services.hydrology import ingest_hydro_network
    ohn_seg_count, ohn_barrier_count = ingest_hydro_network(loc.lat, loc.lng, radius_km)

    console.print("[dim]Downloading and parsing MNRF Fishing Regulations Summary (annual PDF)…[/dim]")  # noqa: E501
    from src.services.regulations import ingest_regulations
    reg_count = ingest_regulations()

    console.print(
        f"[green]iNaturalist: {inat_count} observations | GBIF: {gbif_count} records "
        f"| WSC gauges: {wsc_count} stations updated "
        f"| OSM: {osm_water_count} water features, {osm_access_count} access points "
        f"| MNRF stocking: {stocking_count} records "
        f"| Species: {species_count} ranges loaded "
        f"| Reddit: {reddit_count} posts indexed "
        f"| OHN: {ohn_seg_count} stream segments, {ohn_barrier_count} barriers "
        f"| Regulations: {reg_count} FMZ zones[/green]"
    )


def _print_profile(p: UserProfile) -> None:
    home = p.home_location
    home_str = f"{home.name} ({home.lat}, {home.lng})" if home else "(not set)"
    species = ", ".join(p.target_species) or "(none)"
    body_lines = [
        f"Home jurisdiction: {p.home_jurisdiction}",
        f"Home location: {home_str}",
        f"Target species: {species}",
        f"Fishing style: {p.fishing_style or '(not set)'}",
        f"Skill level: {p.skill_level}",
        f"Preferences: {p.preferences or '(none)'}",
    ]
    if p.frequented_jurisdictions:
        body_lines.append(f"Also fishes: {', '.join(p.frequented_jurisdictions)}")
    if p.gear:
        body_lines.append(f"Gear: {p.gear}")
    if p.budget is not None:
        body_lines.append(f"Annual budget: ${p.budget}")
    console.print(Panel("\n".join(body_lines), title="Profile", border_style="cyan"))


if __name__ == "__main__":
    app()
