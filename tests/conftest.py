"""Shared fixtures for MTGTop8 tests."""

import pytest
from fastapi.testclient import TestClient

from tests._dbguard import apply_test_database_env, ensure_test_schema

# DB-backed tests run only against TEST_DATABASE_URL (never staging/prod): pin DATABASE_URL
# to it (or to "" so tests skip) before api.config loads .env, then migrate it at import time
# because test modules import api.main (which queries the DB) during collection.
_TEST_DATABASE_URL = apply_test_database_env()
try:
    ensure_test_schema(_TEST_DATABASE_URL)
except Exception as exc:  # unreachable/misconfigured test DB: leave DB tests to skip
    print(f"[conftest] test database schema setup failed, DB tests may skip: {exc}")

# Load .env / .env.$DB_ENV up front. api.db does not import api.config, so without this
# the DB-backed tests only see DATABASE_URL when another module imported api.main first
# (alphabetical luck) and silently skip when run on their own.
import api.config  # noqa: F401,E402  isort:skip

# Import app and auth/DB dependencies for override fixture (done lazily to avoid import side effects in non-API tests)
_app_ref = None
_dep_refs = None


def _get_app_and_deps():
    global _app_ref, _dep_refs
    if _app_ref is None:
        from api.dependencies import (
            require_admin,
            require_admin_or_event_edit,
            require_admin_or_event_edit_deck,
            require_database,
        )
        from api.main import app
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
        "player_id": 1,
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
        "player_id": 2,
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


@pytest.fixture
def db_session_rollback():
    """Session that rolls back so no data is committed. Skips when DATABASE_URL is unset or DB unreachable."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from api.db import get_session_factory_cached, is_database_available

    if not is_database_available():
        pytest.skip("TEST_DATABASE_URL not set")
    factory = get_session_factory_cached()
    if factory is None:
        pytest.skip("TEST_DATABASE_URL not set")
    try:
        session = factory()
        session.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Test database unreachable")
    try:
        yield session
    finally:
        session.rollback()
        session.close()
