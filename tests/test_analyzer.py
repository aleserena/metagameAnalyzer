"""Tests for metagame analyzer."""

import pytest
from src.mtgtop8.models import Deck
from src.mtgtop8.analyzer import (
    commander_distribution,
    archetype_distribution,
    archetype_aggregate_analysis,
    top_cards_main,
    player_leaderboard,
    deck_diversity,
    analyze,
    deck_analysis,
)


def test_commander_distribution(sample_decks):
    """Commander distribution counts decks per commander."""
    decks = [Deck.from_dict(d) for d in sample_decks]
    result = commander_distribution(decks)
    assert len(result) == 2
    commanders = [r["commander"] for r in result]
    assert "Spider-Man 2099" in commanders
    assert "Terra, Magical Adept" in commanders
    total_pct = sum(r["pct"] for r in result)
    assert abs(total_pct - 100) < 0.1


def test_archetype_distribution(sample_decks):
    """Archetype distribution counts decks per archetype."""
    decks = [Deck.from_dict(d) for d in sample_decks]
    result = archetype_distribution(decks)
    assert len(result) == 2
    archetypes = [r["archetype"] for r in result]
    assert "UR Aggro" in archetypes
    assert "UR Control" in archetypes


def test_top_cards_main_excludes_basic_lands(sample_decks):
    """top_cards_main excludes basic lands (Plains, Island, etc.)."""
    decks = [Deck.from_dict(d) for d in sample_decks]
    result = top_cards_main(decks)
    card_names = [r["card"] for r in result]
    assert "Plains" not in card_names
    assert "Island" not in card_names
    assert "Lands" in card_names  # "Lands" is not in BASIC_LANDS


def test_top_cards_main_ignore_lands(sample_decks):
    """top_cards_main with ignore_lands=True excludes land-like cards."""
    decks = [Deck.from_dict(d) for d in sample_decks]
    result = top_cards_main(decks, ignore_lands=True)
    card_names = [r["card"] for r in result]
    assert "Lands" not in card_names
    assert "Lightning Bolt" in card_names


def test_player_leaderboard(sample_decks):
    """Player leaderboard returns wins, top2, top4, points."""
    decks = [Deck.from_dict(d) for d in sample_decks]
    result = player_leaderboard(decks)
    assert len(result) == 2
    jeremy = next(r for r in result if r["player"] == "Jeremy Lb")
    assert jeremy["wins"] == 1
    assert jeremy["top2"] == 1
    assert jeremy["deck_count"] == 1
    thomas = next(r for r in result if r["player"] == "Thomas Le Goff")
    assert thomas["wins"] == 0
    assert thomas["top2"] == 1


def test_deck_diversity(sample_decks):
    """deck_diversity returns unique commanders and archetypes."""
    decks = [Deck.from_dict(d) for d in sample_decks]
    result = deck_diversity(decks)
    assert result["total_decks"] == 2
    assert result["unique_commanders"] == 2
    assert result["unique_archetypes"] == 2


def test_analyze(sample_decks):
    """analyze returns full metagame report."""
    decks = [Deck.from_dict(d) for d in sample_decks]
    result = analyze(decks)
    assert "summary" in result
    assert "commander_distribution" in result
    assert "archetype_distribution" in result
    assert "top_cards_main" in result
    assert result["summary"]["total_decks"] == 2


def test_deck_analysis_with_metadata(sample_deck_dict):
    """deck_analysis returns mana curve, colors, lands with card metadata."""
    deck = Deck.from_dict(sample_deck_dict)
    metadata = {
        "Lightning Bolt": {"cmc": 1, "mana_cost": "{R}", "type_line": "Instant", "colors": ["R"], "color_identity": ["R"]},
        "Spider-Man 2099": {"cmc": 3, "mana_cost": "{1}{U}{R}", "type_line": "Legendary Creature", "colors": ["U", "R"], "color_identity": ["U", "R"]},
        "Lands": {"cmc": 0, "mana_cost": "", "type_line": "Land", "colors": [], "color_identity": []},
    }
    result = deck_analysis(deck, metadata)
    assert "mana_curve" in result
    assert "color_distribution" in result
    assert "lands_distribution" in result
    assert "type_distribution" in result
    assert "grouped_by_type" in result
    assert result["lands_distribution"]["lands"] >= 38  # Lands card (38 copies)
    assert 1 in result["mana_curve"]  # Lightning Bolt CMC 1


def test_archetype_aggregate_analysis(sample_decks):
    """archetype_aggregate_analysis returns averaged mana curve, colors, lands, types."""
    decks = [Deck.from_dict(d) for d in sample_decks]
    metadata = {
        "Lightning Bolt": {"cmc": 1, "mana_cost": "{R}", "type_line": "Instant", "colors": ["R"], "color_identity": ["R"]},
        "Spider-Man 2099": {"cmc": 3, "mana_cost": "{1}{U}{R}", "type_line": "Legendary Creature", "colors": ["U", "R"], "color_identity": ["U", "R"]},
        "Terra, Magical Adept": {"cmc": 3, "mana_cost": "{1}{U}{R}", "type_line": "Legendary Creature", "colors": ["U", "R"], "color_identity": ["U", "R"]},
        "Lands": {"cmc": 0, "mana_cost": "", "type_line": "Land", "colors": [], "color_identity": []},
    }
    result = archetype_aggregate_analysis(decks, metadata)
    assert "mana_curve" in result
    assert "color_distribution" in result
    assert "lands_distribution" in result
    assert "type_distribution" in result
    # Averages: two decks => values should be numeric (averaged)
    assert isinstance(result["lands_distribution"]["lands"], (int, float))
    assert isinstance(result["lands_distribution"]["nonlands"], (int, float))
