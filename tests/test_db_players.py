"""Tests for player resolution: get_or_create_player, resolve_name_to_player_id, and response shape."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.db import (
    get_or_create_player,
    get_player_by_id,
    resolve_name_to_player_id,
    set_player_alias,
)


@pytest.fixture
def db_session_rollback():
    """Session that rolls back so no data is committed. Skips when DATABASE_URL is unset or DB unreachable."""
    from sqlalchemy.exc import OperationalError

    from api.db import get_session_factory_cached, is_database_available

    if not is_database_available():
        pytest.skip("DATABASE_URL not set")
    factory = get_session_factory_cached()
    if factory is None:
        pytest.skip("DATABASE_URL not set")
    try:
        from sqlalchemy import text

        session = factory()
        session.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Database unreachable (e.g. no network)")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_get_or_create_player_creates_and_returns_stable_id(db_session_rollback):
    """get_or_create_player creates a player and returns the same id on second call."""
    session = db_session_rollback
    pid1, display1 = get_or_create_player(session, "Alice")
    assert isinstance(pid1, int)
    assert display1 == "Alice"
    row = get_player_by_id(session, pid1)
    assert row is not None
    assert row.display_name == "Alice"

    pid2, display2 = get_or_create_player(session, "Alice")
    assert pid2 == pid1
    assert display2 == "Alice"


def test_resolve_name_to_player_id_with_alias(db_session_rollback):
    """resolve_name_to_player_id returns (player_id, display_name) for an alias mapping to a player."""
    session = db_session_rollback
    pid, _ = get_or_create_player(session, "Bob")
    set_player_alias(session, "Bobby", "Bob")
    session.flush()

    resolved_id, resolved_name = resolve_name_to_player_id(session, "Bobby")
    assert resolved_id == pid
    assert resolved_name == "Bob"

    # Display name also resolves
    direct_id, direct_name = resolve_name_to_player_id(session, "Bob")
    assert direct_id == pid
    assert direct_name == "Bob"
