"""Tests for CABIN benthic macroinvertebrate ingest. No live downloads."""

from pathlib import Path

import pytest

from src.ingest.jurisdictions.ca_on.benthic import (
    _habitat_quality,
    _is_ept_taxon,
    _normalize_col,
    build_samples,
    load_study,
    parse_benthic,
)
from src.models.benthic_sample import BenthicSample

STUDY_FIXTURE = Path(__file__).parent / "fixtures" / "cabin_study_sample.csv"
BENTHIC_FIXTURE = Path(__file__).parent / "fixtures" / "cabin_benthic_sample.csv"


# --- Unit: column normalization ---


def test_normalize_col_bilingual():
    assert _normalize_col("SiteVisitID/IdentifiantdeVisite") == "SiteVisitID"


def test_normalize_col_bilingual_order():
    assert _normalize_col("Order/Ordre") == "Order"


def test_normalize_col_bilingual_count():
    assert _normalize_col("Count/Décompte") == "Count"


def test_normalize_col_no_slash():
    assert _normalize_col("  Latitude  ") == "Latitude"


# --- Unit: EPT classification ---


def test_is_ept_taxon_by_family():
    assert _is_ept_taxon("Ephemeroptera", "Baetidae")
    assert _is_ept_taxon("Plecoptera", "Perlidae")
    assert _is_ept_taxon("Trichoptera", "Hydropsychidae")


def test_is_ept_taxon_order_only_when_no_family():
    assert _is_ept_taxon("Ephemeroptera", "")
    assert _is_ept_taxon("Plecoptera", "")
    assert _is_ept_taxon("Trichoptera", "")


def test_is_ept_taxon_order_with_family_uses_family():
    # Leptoceridae is in _EPT_FAMILIES → EPT regardless of order name
    assert _is_ept_taxon("Trichoptera", "Leptoceridae")


def test_is_ept_taxon_non_ept():
    assert not _is_ept_taxon("Diptera", "Chironomidae")
    assert not _is_ept_taxon("Oligochaeta", "Oligochaeta")
    assert not _is_ept_taxon("", "")


# --- Unit: habitat quality thresholds ---


def test_habitat_quality_high():
    assert _habitat_quality(0.5) == "high"
    assert _habitat_quality(1.0) == "high"


def test_habitat_quality_moderate():
    assert _habitat_quality(0.25) == "moderate"
    assert _habitat_quality(0.499) == "moderate"


def test_habitat_quality_impaired():
    assert _habitat_quality(0.0) == "impaired"
    assert _habitat_quality(0.249) == "impaired"


# --- Integration: load_study ---


def test_load_study_on_visits():
    _, on_visits = load_study(STUDY_FIXTURE)
    assert "SV001" in on_visits
    assert "SV002" in on_visits
    assert "SV003" in on_visits
    assert "SV004" in on_visits
    assert "SV006" in on_visits


def test_load_study_excludes_qc():
    _, on_visits = load_study(STUDY_FIXTURE)
    assert "SV005" not in on_visits


def test_load_study_on_count():
    _, on_visits = load_study(STUDY_FIXTURE)
    assert len(on_visits) == 5


def test_load_study_metadata():
    study_meta, _ = load_study(STUDY_FIXTURE)
    m = study_meta["SV001"]
    assert m["site_name"] == "Bronte Creek"
    assert m["site_code"] == "ON-001"
    assert m["lat"] == pytest.approx(43.42)
    assert m["lng"] == pytest.approx(-79.72)
    assert m["year"] == 2022
    assert m["julian_day"] == 152
    assert m["stream_order"] == 4
    assert m["local_basin"] == "Lake Ontario Tributaries"


def test_load_study_lake_erie_basin():
    study_meta, _ = load_study(STUDY_FIXTURE)
    assert study_meta["SV006"]["local_basin"] == "Lake Erie Tributaries"


# --- Integration: parse_benthic ---


def test_parse_benthic_excludes_qc_rows():
    _, on_visits = load_study(STUDY_FIXTURE)
    agg = parse_benthic(BENTHIC_FIXTURE, on_visits)
    assert "SV005" not in agg


def test_parse_benthic_ontario_visit_count():
    _, on_visits = load_study(STUDY_FIXTURE)
    agg = parse_benthic(BENTHIC_FIXTURE, on_visits)
    assert len(agg) == 5


def test_parse_benthic_sv001_ept_count():
    """SV001: EPT raw = 30+20+25+15+10+40+20 = 160."""
    _, on_visits = load_study(STUDY_FIXTURE)
    agg = parse_benthic(BENTHIC_FIXTURE, on_visits)
    assert agg["SV001"]["ept_count"] == pytest.approx(160.0)


def test_parse_benthic_sv001_total_count():
    """SV001: total raw = 160 + 15 + 10 = 185."""
    _, on_visits = load_study(STUDY_FIXTURE)
    agg = parse_benthic(BENTHIC_FIXTURE, on_visits)
    assert agg["SV001"]["total_count"] == pytest.approx(185.0)


def test_parse_benthic_sv001_ept_richness():
    """SV001: 7 distinct EPT families."""
    _, on_visits = load_study(STUDY_FIXTURE)
    agg = parse_benthic(BENTHIC_FIXTURE, on_visits)
    assert len(agg["SV001"]["ept_taxa_seen"]) == 7


def test_parse_benthic_sv001_all_taxa():
    """SV001: 9 total distinct taxa."""
    _, on_visits = load_study(STUDY_FIXTURE)
    agg = parse_benthic(BENTHIC_FIXTURE, on_visits)
    assert len(agg["SV001"]["all_taxa_seen"]) == 9


def test_parse_benthic_sv003_subsample_zero():
    """SV003 SubSample=0: raw counts used directly — ept_count=20, total_count=130."""
    _, on_visits = load_study(STUDY_FIXTURE)
    agg = parse_benthic(BENTHIC_FIXTURE, on_visits)
    assert agg["SV003"]["ept_count"] == pytest.approx(20.0)
    assert agg["SV003"]["total_count"] == pytest.approx(130.0)


def test_parse_benthic_sv003_ept_richness():
    """SV003: Baetidae, Ephemerellidae, Heptageniidae, Hydropsychidae = 4 EPT taxa."""
    _, on_visits = load_study(STUDY_FIXTURE)
    agg = parse_benthic(BENTHIC_FIXTURE, on_visits)
    assert len(agg["SV003"]["ept_taxa_seen"]) == 4


# --- Integration: build_samples ---


def _full_parse() -> list[BenthicSample]:
    study_meta, on_visits = load_study(STUDY_FIXTURE)
    benthic_agg = parse_benthic(BENTHIC_FIXTURE, on_visits)
    return build_samples(study_meta, benthic_agg)


def test_build_samples_count():
    records = _full_parse()
    assert len(records) == 5


def test_build_samples_jurisdiction():
    records = _full_parse()
    assert all(r.jurisdiction == "CA-ON" for r in records)


def test_build_samples_no_qc():
    records = _full_parse()
    visit_ids = {r.site_visit_id for r in records}
    assert "SV005" not in visit_ids


def test_build_samples_sv001_high_quality():
    records = _full_parse()
    r = next(r for r in records if r.site_visit_id == "SV001")
    assert r.habitat_quality == "high"
    assert r.ept_proportion == pytest.approx(160.0 / 185.0, rel=1e-3)
    assert r.ept_richness == 7
    assert r.total_taxa_richness == 9


def test_build_samples_sv001_metadata():
    records = _full_parse()
    r = next(r for r in records if r.site_visit_id == "SV001")
    assert r.site_name == "Bronte Creek"
    assert r.site_code == "ON-001"
    assert r.lat == pytest.approx(43.42)
    assert r.lng == pytest.approx(-79.72)
    assert r.sampled_year == 2022
    assert r.sampled_julian_day == 152
    assert r.stream_order == 4
    assert r.local_basin == "Lake Ontario Tributaries"


def test_build_samples_sv003_impaired():
    records = _full_parse()
    r = next(r for r in records if r.site_visit_id == "SV003")
    assert r.habitat_quality == "impaired"
    assert r.ept_count == pytest.approx(20.0)
    assert r.total_count == pytest.approx(130.0)


def test_build_samples_sv006_lake_erie():
    records = _full_parse()
    r = next(r for r in records if r.site_visit_id == "SV006")
    assert r.local_basin == "Lake Erie Tributaries"
    assert r.sampled_year == 2022


# --- Edge cases ---


def test_parse_benthic_empty_on_visits():
    """Empty on_visit_ids → no aggregation."""
    agg = parse_benthic(BENTHIC_FIXTURE, set())
    assert len(agg) == 0


def test_parse_benthic_zero_count_skipped(tmp_path):
    """Rows with Count=0 are skipped."""
    csv_path = tmp_path / "benthic_zero.csv"
    csv_path.write_text(
        '"SiteVisitID/IdentifiantdeVisite","SubSample/Sous-échantillon",'
        '"TotalSample/Échantillontotal","Order/Ordre","Family/Famille","Count/Décompte"\n'
        '"SV001","300","500","Ephemeroptera","Baetidae","0"\n'
    )
    agg = parse_benthic(csv_path, {"SV001"})
    assert len(agg) == 0


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
