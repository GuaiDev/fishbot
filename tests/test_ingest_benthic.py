"""Tests for CABIN benthic macroinvertebrate ingest. No live downloads."""

from pathlib import Path

import pytest

from src.ingest.jurisdictions.ca_on.benthic import (
    _habitat_quality,
    _is_ept,
    _normalize_col,
    parse_cabin_data,
)
from src.models.benthic_sample import BenthicSample

FIXTURE = Path(__file__).parent / "fixtures" / "cabin_benthic_sample.csv"


# --- Unit: column normalization ---


def test_normalize_col_bilingual():
    assert _normalize_col("SiteVisitID/IDVisite") == "SiteVisitID"


def test_normalize_col_bilingual_province():
    assert _normalize_col("Province/Province") == "Province"


def test_normalize_col_no_slash():
    assert _normalize_col("  Baetidae  ") == "Baetidae"


def test_normalize_col_taxon_with_slash():
    # Hypothetical bilingual taxon header should strip French suffix
    assert _normalize_col("Perlidae/Perlidae") == "Perlidae"


# --- Unit: EPT classification ---


def test_is_ept_family():
    assert _is_ept("Baetidae")
    assert _is_ept("Perlidae")
    assert _is_ept("Hydropsychidae")


def test_is_ept_order():
    assert _is_ept("Ephemeroptera")
    assert _is_ept("Plecoptera")
    assert _is_ept("Trichoptera")


def test_is_ept_non_ept():
    assert not _is_ept("Chironomidae")
    assert not _is_ept("Oligochaeta")
    assert not _is_ept("Province")


# --- Unit: habitat quality thresholds ---


def test_habitat_quality_high():
    assert _habitat_quality(0.5) == "high"
    assert _habitat_quality(0.9) == "high"


def test_habitat_quality_moderate():
    assert _habitat_quality(0.25) == "moderate"
    assert _habitat_quality(0.49) == "moderate"


def test_habitat_quality_impaired():
    assert _habitat_quality(0.0) == "impaired"
    assert _habitat_quality(0.24) == "impaired"


# --- Integration: parse fixture ---


def test_fixture_excludes_quebec():
    """QC row (SV005) must be filtered out — only ON rows returned."""
    records = parse_cabin_data(FIXTURE)
    visit_ids = {r.site_visit_id for r in records}
    assert "SV005" not in visit_ids


def test_fixture_record_count():
    """5 Ontario rows in fixture → 5 records returned."""
    records = parse_cabin_data(FIXTURE)
    assert len(records) == 5


def test_fixture_jurisdiction_always_ca_on():
    records = parse_cabin_data(FIXTURE)
    assert all(r.jurisdiction == "CA-ON" for r in records)


def test_fixture_site_sv001_high_quality():
    """SV001 has 7 EPT taxa with high counts → 'high' quality."""
    records = parse_cabin_data(FIXTURE)
    r = next(r for r in records if r.site_visit_id == "SV001")
    assert r.habitat_quality == "high"
    assert r.ept_richness == 7
    assert r.sampled_year == 2022
    assert r.site_name == "Bronte Creek"
    assert r.lat == pytest.approx(43.42)
    assert r.lng == pytest.approx(-79.72)


def test_fixture_site_sv003_subsample_zero():
    """SV003 has SubSample=0 — raw counts used directly, not divided."""
    records = parse_cabin_data(FIXTURE)
    r = next(r for r in records if r.site_visit_id == "SV003")
    # Raw EPT counts: Baetidae=5, Ephemerellidae=3, Heptageniidae=4, Hydropsychidae=8 → 20
    # Raw total: 5+3+4+0+0+8+0+60+50 = 130
    # When SubSample=0, no scaling: ept_count=20.0, total_count=130.0
    assert r.ept_count == pytest.approx(20.0)
    assert r.total_count == pytest.approx(130.0)
    assert r.ept_proportion == pytest.approx(20.0 / 130.0, rel=1e-3)
    assert r.habitat_quality == "impaired"


def test_fixture_site_sv001_scaling():
    """SV001 SubSample=300: counts scaled to 500-specimen standard."""
    records = parse_cabin_data(FIXTURE)
    r = next(r for r in records if r.site_visit_id == "SV001")
    # Raw EPT: 30+20+25+15+10+40+20 = 160; total raw: 160+15+10 = 185
    expected_ept = 160 / 300 * 500
    expected_total = 185 / 300 * 500
    assert r.ept_count == pytest.approx(expected_ept, rel=1e-3)
    assert r.total_count == pytest.approx(expected_total, rel=1e-3)


def test_fixture_ept_richness_sv003():
    """SV003: Perlidae=0, Chloroperlidae=0, Rhyacophilidae=0 → EPT richness=4."""
    records = parse_cabin_data(FIXTURE)
    r = next(r for r in records if r.site_visit_id == "SV003")
    assert r.ept_richness == 4


def test_fixture_total_taxa_richness_sv003():
    """SV003: 4 EPT + Chironomidae + Oligochaeta → 6 non-zero taxa."""
    records = parse_cabin_data(FIXTURE)
    r = next(r for r in records if r.site_visit_id == "SV003")
    assert r.total_taxa_richness == 6


def test_fixture_stream_order_and_basin():
    records = parse_cabin_data(FIXTURE)
    r = next(r for r in records if r.site_visit_id == "SV001")
    assert r.stream_order == 4
    assert r.local_basin == "Lake Ontario"


def test_fixture_julian_day():
    records = parse_cabin_data(FIXTURE)
    r = next(r for r in records if r.site_visit_id == "SV001")
    assert r.sampled_julian_day == 152


def test_fixture_sv006_grand_river():
    """SV006 Grand River in Lake Erie basin."""
    records = parse_cabin_data(FIXTURE)
    r = next(r for r in records if r.site_visit_id == "SV006")
    assert r.local_basin == "Lake Erie"
    assert r.sampled_year == 2022


# --- Edge case: all-zero row is skipped ---


def test_skip_all_zero_row(tmp_path):
    header = (
        "SiteVisitID/IDVisite,Province/Province,VisitYear/AnnéeVisite,"
        "Latitude/Latitude,Longitude/Longitude,SubSample/Souséchantillon,"
        "Baetidae,Chironomidae"
    )
    row = "SV_ZERO,ON,2022,43.5,-79.5,300,0,0"
    csv_path = tmp_path / "cabin_zero.csv"
    csv_path.write_text(header + "\n" + row + "\n")
    records = parse_cabin_data(csv_path)
    assert len(records) == 0


# --- Edge case: missing SiteVisitID is skipped ---


def test_skip_missing_visit_id(tmp_path):
    header = (
        "SiteVisitID/IDVisite,Province/Province,VisitYear/AnnéeVisite,"
        "Latitude/Latitude,Longitude/Longitude,SubSample/Souséchantillon,"
        "Baetidae,Chironomidae"
    )
    row = ",ON,2022,43.5,-79.5,300,10,20"
    csv_path = tmp_path / "cabin_noid.csv"
    csv_path.write_text(header + "\n" + row + "\n")
    records = parse_cabin_data(csv_path)
    assert len(records) == 0


# --- Model tests ---


def test_benthic_sample_model_valid():
    s = BenthicSample(
        site_visit_id="TEST001",
        site_code="ON-TEST",
        jurisdiction="CA-ON",
        sampled_year=2023,
        ept_richness=5,
        ept_count=120.0,
        total_count=250.0,
        ept_proportion=0.48,
        total_taxa_richness=9,
        habitat_quality="moderate",
    )
    assert s.site_visit_id == "TEST001"
    assert s.habitat_quality == "moderate"


def test_benthic_sample_optional_fields_default_none():
    s = BenthicSample(
        site_visit_id="TEST002",
        site_code="ON-TEST2",
        jurisdiction="CA-ON",
        sampled_year=2022,
        ept_richness=0,
        ept_count=0.0,
        total_count=50.0,
        ept_proportion=0.0,
        total_taxa_richness=3,
        habitat_quality="impaired",
    )
    assert s.lat is None
    assert s.lng is None
    assert s.site_name is None
    assert s.stream_order is None
    assert s.local_basin is None
    assert s.sampled_julian_day is None
