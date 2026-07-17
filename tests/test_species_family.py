"""Tests for the family taxonomy classification behind My FishDex grouping."""

from src.services.species_family import get_family


def test_known_family_returns_display_name():
    assert get_family("Micropterus dolomieu") == ("Centrarchidae", "Bass & Sunfish")


def test_carp_exception_gets_its_own_folder():
    family, display = get_family("Cyprinus carpio")
    assert display == "Carp"
    assert family == "Cyprinus carpio"


def test_other_cyprinidae_not_affected_by_carp_exception():
    family, display = get_family("Semotilus atromaculatus")
    assert family == "Cyprinidae"
    assert display == "Minnows & Chubs"


def test_unknown_species_falls_back_gracefully():
    assert get_family("Nonexistent fishium") == ("Unclassified", "Other")


def test_darters_are_percidae_not_a_separate_family():
    family, display = get_family("Etheostoma caeruleum")
    assert family == "Percidae"
    assert display == "Perch, Walleye & Darters"
