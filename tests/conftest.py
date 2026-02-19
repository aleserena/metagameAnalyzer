"""Shared fixtures for MTGTop8 tests."""

import pytest


@pytest.fixture
def sample_deck_dict():
    """Single deck as dict (sample_decks.json structure)."""
    return {
        "deck_id": 811597,
        "event_id": 80455,
        "format_id": "EDH",
        "name": "Spider-man 2099",
        "player": "Jeremy Lb",
        "event_name": "CR PdLL MTGAnjou @ Angers (France)",
        "date": "15/02/26",
        "rank": "1",
        "player_count": 128,
        "mainboard": [
            {"qty": 1, "card": "Spider-Man 2099"},
            {"qty": 2, "card": "Lightning Bolt"},
            {"qty": 38, "card": "Lands"},
        ],
        "sideboard": [{"qty": 1, "card": "Soul-Guide Lantern"}],
        "commanders": ["Spider-Man 2099"],
        "archetype": "UR Aggro",
    }


@pytest.fixture
def sample_decks(sample_deck_dict):
    """List of deck dicts for multi-deck analysis."""
    deck2 = {
        "deck_id": 811598,
        "event_id": 80455,
        "format_id": "EDH",
        "name": "Terra, Magical Adept",
        "player": "Thomas Le Goff",
        "event_name": "CR PdLL MTGAnjou @ Angers (France)",
        "date": "15/02/26",
        "rank": "2",
        "player_count": 128,
        "mainboard": [
            {"qty": 1, "card": "Terra, Magical Adept"},
            {"qty": 2, "card": "Lightning Bolt"},
            {"qty": 39, "card": "Lands"},
        ],
        "sideboard": [],
        "commanders": ["Terra, Magical Adept"],
        "archetype": "UR Control",
    }
    return [sample_deck_dict, deck2]


@pytest.fixture
def deck_with_split_card():
    """Deck containing Fire / Ice (single slash) for normalization tests."""
    return {
        "deck_id": 999,
        "event_id": 1,
        "format_id": "EDH",
        "name": "Test",
        "player": "Test Player",
        "event_name": "Test Event",
        "date": "01/01/25",
        "rank": "1",
        "player_count": 8,
        "mainboard": [
            {"qty": 1, "card": "Fire / Ice"},
            {"qty": 1, "card": "Lightning Bolt"},
        ],
        "sideboard": [{"qty": 1, "card": "Life / Death"}],
        "commanders": [],
        "archetype": "Test",
    }
