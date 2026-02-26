"""Tests for metagame analyzer."""

from src.mtgtop8.analyzer import (
    analyze,
    archetype_aggregate_analysis,
    archetype_distribution,
    commander_distribution,
    deck_analysis,
    deck_diversity,
    effective_commanders,
    effective_mainboard,
    is_top8,
    normalize_rank,
    player_leaderboard,
    top_cards_main,
)
from src.mtgtop8.models import Deck


def test_normalize_rank_bands():
    """normalize_rank maps bands and individual ranks 1-128 to canonical bands."""
    assert normalize_rank("1") == "1"
    assert normalize_rank("2") == "2"
    assert normalize_rank("3") == "3-4"
    assert normalize_rank("4") == "3-4"
    assert normalize_rank("3-4") == "3-4"
    assert normalize_rank("5") == "5-8"
    assert normalize_rank("8") == "5-8"
    assert normalize_rank("9") == "9-16"
    assert normalize_rank("16") == "9-16"
    assert normalize_rank("17") == "17-32"
    assert normalize_rank("32") == "17-32"
    assert normalize_rank("33") == "33-64"
    assert normalize_rank("64") == "33-64"
    assert normalize_rank("33-64") == "33-64"
    assert normalize_rank("65") == "65-128"
    assert normalize_rank("128") == "65-128"
    assert normalize_rank("65-128") == "65-128"
    assert normalize_rank("129") == ""
    assert normalize_rank("") == ""


def test_effective_mainboard_empty_edh_with_archetype():
    """Empty EDH deck with archetype (non-partner) gets commander on effective mainboard."""
    empty_edh = Deck.from_dict({
        "deck_id": 1,
        "event_id": 1,
        "format_id": "EDH",
        "name": "Azusa",
        "player": "P",
        "event_name": "E",
        "date": "01/01/26",
        "rank": "5-8",
        "player_count": 32,
        "mainboard": [],
        "sideboard": [],
        "commanders": [],
        "archetype": "Azusa, Lost but Seeking",
    })
    assert effective_mainboard(empty_edh) == [(1, "Azusa, Lost but Seeking")]
    assert effective_commanders(empty_edh) == ["Azusa, Lost but Seeking"]

    # Partner deck (2 commanders): no auto-include on mainboard
    partner = Deck.from_dict({
        "deck_id": 2,
        "event_id": 1,
        "format_id": "EDH",
        "name": "Partner",
        "player": "P",
        "event_name": "E",
        "date": "01/01/26",
        "rank": "5-8",
        "player_count": 32,
        "mainboard": [],
        "sideboard": [],
        "commanders": ["Thrasios", "Tymna"],
        "archetype": "Partner",
    })
    assert effective_mainboard(partner) == []
    assert effective_commanders(partner) == ["Thrasios", "Tymna"]


def test_is_top8_excludes_33_to_128():
    """is_top8 is False for ranks 33-128."""
    assert is_top8("33") is False
    assert is_top8("64") is False
    assert is_top8("65") is False
    assert is_top8("128") is False
    assert is_top8("33-64") is False
    assert is_top8("65-128") is False
    assert is_top8("1") is True
    assert is_top8("8") is True


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
    """deck_diversity returns unique players and archetypes."""
    decks = [Deck.from_dict(d) for d in sample_decks]
    result = deck_diversity(decks)
    assert result["total_decks"] == 2
    assert result["unique_players"] == 2
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
