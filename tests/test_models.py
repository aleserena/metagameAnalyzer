"""Tests for Deck model serialization."""

import pytest
from src.mtgtop8.models import Deck


def test_deck_from_dict_round_trip(sample_deck_dict):
    """Deck.from_dict then to_dict should match original structure."""
    deck = Deck.from_dict(sample_deck_dict)
    out = deck.to_dict()
    assert out["deck_id"] == sample_deck_dict["deck_id"]
    assert out["name"] == sample_deck_dict["name"]
    assert out["mainboard"] == sample_deck_dict["mainboard"]
    assert out["sideboard"] == sample_deck_dict["sideboard"]
    assert out["commanders"] == sample_deck_dict["commanders"]
    assert out["archetype"] == sample_deck_dict["archetype"]


def test_deck_from_dict_with_missing_commanders():
    """from_dict handles missing commanders (defaults to []) and archetype (None)."""
    data = {
        "deck_id": 1,
        "event_id": 1,
        "format_id": "ST",
        "name": "Standard Deck",
        "player": "Player",
        "event_name": "Event",
        "date": "01/01/25",
        "rank": "1",
        "player_count": 8,
        "mainboard": [{"qty": 1, "card": "Card"}],
        "sideboard": [],
    }
    deck = Deck.from_dict(data)
    assert deck.commanders == []
    assert deck.archetype is None


def test_deck_from_dict_mainboard_structure(sample_deck_dict):
    """from_dict converts mainboard dicts to (qty, card) tuples."""
    deck = Deck.from_dict(sample_deck_dict)
    assert deck.mainboard == [
        (1, "Spider-Man 2099"),
        (2, "Lightning Bolt"),
        (38, "Lands"),
    ]
    assert deck.sideboard == [(1, "Soul-Guide Lantern")]


def test_deck_to_dict_output_structure(sample_deck_dict):
    """to_dict produces {qty, card} format for mainboard/sideboard."""
    deck = Deck.from_dict(sample_deck_dict)
    out = deck.to_dict()
    assert all("qty" in c and "card" in c for c in out["mainboard"])
    assert out["mainboard"][0] == {"qty": 1, "card": "Spider-Man 2099"}
