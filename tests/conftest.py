"""Shared fixtures for MTGTop8 tests."""

import pytest
from fastapi.testclient import TestClient

# Import app and auth/DB dependencies for override fixture (done lazily to avoid import side effects in non-API tests)
_app_ref = None
_dep_refs = None


def _get_app_and_deps():
    global _app_ref, _dep_refs
    if _app_ref is None:
        from api.main import (
            app,
            require_admin,
            require_database,
            require_admin_or_event_edit,
            require_admin_or_event_edit_deck,
        )
        _app_ref = app
        _dep_refs = {
            "require_admin": require_admin,
            "require_database": require_database,
            "require_admin_or_event_edit": require_admin_or_event_edit,
            "require_admin_or_event_edit_deck": require_admin_or_event_edit_deck,
        }
    return _app_ref, _dep_refs


@pytest.fixture
def client_with_overrides():
    """TestClient with require_admin, require_database, and event-edit deps overridden (no-op pass)."""
    app, deps = _get_app_and_deps()
    app.dependency_overrides[deps["require_admin"]] = lambda authorization=None: "admin"
    app.dependency_overrides[deps["require_database"]] = lambda: None
    app.dependency_overrides[deps["require_admin_or_event_edit"]] = (
        lambda event_id, authorization=None, x_event_edit_token=None: "admin"
    )
    app.dependency_overrides[deps["require_admin_or_event_edit_deck"]] = (
        lambda deck_id, authorization=None, x_event_edit_token=None: "admin"
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


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
