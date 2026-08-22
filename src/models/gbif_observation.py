"""Pydantic model for a single GBIF species occurrence record."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class GBIFObservation(BaseModel):
    gbif_key: int
    species: str
    common_name: str | None = None
    taxon_key: int
    lat: float
    lng: float
    observed_on: date | None = None
    country_code: str | None = None
    dataset_name: str | None = None
    basis_of_record: str
    coordinate_uncertainty_m: float | None = None
    jurisdiction: str
    ingested_at: datetime = Field(default_factory=datetime.now)

    # ── licensing and attribution ─────────────────────────────────────────────
    # GBIF licences are set per DATASET, not per record, and are restricted to
    # three: CC0, CC BY and CC BY-NC. They arrive as legalcode URIs rather than
    # short codes, so both forms are kept: `license_code` normalised into the
    # same vocabulary the iNaturalist model uses, so one filter can span both
    # corpora, and `license_uri` verbatim so the exact grant is auditable.
    license_code: str | None = None
    """Normalised: 'cc0', 'cc-by', 'cc-by-nc'. None = not stated by the publisher."""

    license_uri: str | None = None
    """The raw legalcode URI exactly as GBIF returned it."""

    dataset_key: str | None = None
    """GBIF dataset UUID. The licence attaches here, so this is the audit key."""

    rights_holder: str | None = None
    recorded_by: str | None = None
