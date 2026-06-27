"""Jurisdiction config registry for the FishDex ingest pipeline.

Each jurisdiction registers a JurisdictionConfig that documents:
  - Which global sources work automatically (iNat, GBIF, WSC, OSM, eBird)
  - Which jurisdiction-specific adapters are implemented
  - Cron areas used by the weekly GitHub Actions ingest
  - API endpoints / dataset URLs for jurisdiction-specific sources

Usage
-----
    from src.ingest.jurisdictions.config import get, all_jurisdictions
    cfg = get("CA-BC")
    cfg.cron_areas      # list of CronArea
    cfg.data_sources    # dict[str, bool | None]

Adding a new jurisdiction
-------------------------
See src/ingest/jurisdictions/JURISDICTION_TEMPLATE.md.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CronArea:
    label: str
    lat: float
    lng: float
    radius_km: float


@dataclass
class JurisdictionConfig:
    jurisdiction_code: str   # ISO 3166-2: "CA-ON", "CA-BC", "US-MI"
    display_name: str
    cron_areas: list[CronArea]
    # Keys: "hydro_network", "fish_observations", "water_quality", "stocking",
    #       "regulations", "species_ranges", "benthic", "geology"
    # Values: True = implemented, False = planned but not yet built, None = not applicable
    data_sources: dict[str, bool | None] = field(default_factory=dict)
    # Named API endpoints / dataset URLs for jurisdiction-specific sources
    api_endpoints: dict[str, str] = field(default_factory=dict)
    notes: str = ""


# ── registry ──────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, JurisdictionConfig] = {}


def register(config: JurisdictionConfig) -> None:
    _REGISTRY[config.jurisdiction_code] = config


def get(jurisdiction_code: str) -> JurisdictionConfig | None:
    return _REGISTRY.get(jurisdiction_code)


def all_jurisdictions() -> list[JurisdictionConfig]:
    return list(_REGISTRY.values())


# ── built-in registrations ────────────────────────────────────────────────────

register(JurisdictionConfig(
    jurisdiction_code="CA-ON",
    display_name="Ontario",
    cron_areas=[
        CronArea("Grand River Dunnville",     42.917, -79.774, 50),
        CronArea("Credit River Mississauga",  43.55,  -79.65,  30),
        CronArea("Bronte Creek Oakville",     43.45,  -79.72,  25),
        CronArea("Thames River London",       42.984, -81.244, 30),
    ],
    data_sources={
        "hydro_network":     True,   # OHN via LIO ArcGIS MapServer
        "fish_observations": False,  # covered by global iNat + GBIF
        "water_quality":     True,   # PWQMN
        "stocking":          True,   # MNRF
        "regulations":       True,   # MNRF annual PDF
        "species_ranges":    True,   # hardcoded range maps
        "benthic":           True,   # CABIN (federal; filtered to ON)
        "geology":           True,   # MRD 128 surficial geology
    },
    api_endpoints={
        "hydro_network":  (
            "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/"
            "LIO_OPEN_DATA/LIO_Open01/MapServer"
        ),
        "water_quality":  (
            "https://data.ontario.ca/api/3/action/package_show"
            "?id=provincial-stream-water-quality-monitoring-network"
        ),
        "stocking": (
            "https://geohub.lio.gov.on.ca/datasets/"
            "c725d683af734e6da7850fe0f0b73eb3_0.csv"
        ),
    },
))

register(JurisdictionConfig(
    jurisdiction_code="CA-BC",
    display_name="British Columbia",
    cron_areas=[
        CronArea("Fraser River Lower Mainland", 49.12,  -122.05, 60),
        CronArea("Thompson River Kamloops",      50.67,  -120.33, 50),
        CronArea("Okanagan Vernon",              50.27,  -119.27, 40),
        CronArea("Skeena River Terrace",         54.51,  -128.60, 50),
    ],
    data_sources={
        "hydro_network":     True,   # FWA via DataBC WFS
        "fish_observations": True,   # FISS via DataBC WFS
        "water_quality":     True,   # BC EMS stations via DataBC WFS (results stubbed)
        "stocking":          False,  # FFSBC data not publicly available in bulk
        "regulations":       False,  # BC regs PDF adapter not yet built
        "species_ranges":    False,  # not yet built
        "benthic":           True,   # CABIN (federal; filtered to BC)
        "geology":           False,  # BC surficial geology adapter not yet built
    },
    api_endpoints={
        "hydro_network": (
            "https://openmaps.gov.bc.ca/geo/pub/"
            "WHSE_BASEMAPPING.FWA_STREAM_NETWORKS_SP/ows"
        ),
        "fish_observations": (
            "https://openmaps.gov.bc.ca/geo/pub/"
            "WHSE_FISH.FISS_FISH_OBSRVTN_PNT_SP/ows"
        ),
        "water_quality_stations": (
            "https://openmaps.gov.bc.ca/geo/pub/"
            "WHSE_ENVIRONMENTAL_MONITORING.ENV_MONITORING_LOCATIONS_SVW/ows"
        ),
    },
    notes=(
        "Global sources (iNat, GBIF, WSC, OSM, eBird) work automatically for any BC lat/lng. "
        "BENTHIC: use the existing CABIN federal adapter with province='BC' filter. "
        "STOCKING: BC FFSBC (Freshwater Fisheries Society of BC) does not publish bulk stocking "
        "records via a public API as of 2026. "
        "REGULATIONS: https://www2.gov.bc.ca/gov/content/sports-culture/recreation/fishing — "
        "HTML/PDF; adapter not yet built. "
        "WATER QUALITY: EMS results (measurements) require the DataBC Distribution API; "
        "see water_quality.py TODO for resource IDs and query approach."
    ),
))
