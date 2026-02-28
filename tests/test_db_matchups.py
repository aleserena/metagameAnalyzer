"""Tests for matchup-related DB helpers: _swiss_rounds_for_players, list_event_ids_with_complete_matchups, list_missing_matchups_for_event."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.db import (
    _swiss_rounds_for_players,
    create_event,
    list_event_ids_with_complete_matchups,
    list_missing_matchups_for_event,
    upsert_deck,
    upsert_matchups_for_deck,
)


# --- Unit tests (no DB) ---


def test_swiss_rounds_for_players():
    """Expected Swiss rounds: 1-2 -> 1, 3-4 -> 2, 5-8 -> 3, 9-16 -> 4, etc."""
    assert _swiss_rounds_for_players(0) == 0
    assert _swiss_rounds_for_players(1) == 1
    assert _swiss_rounds_for_players(2) == 1
    assert _swiss_rounds_for_players(3) == 2
    assert _swiss_rounds_for_players(4) == 2
    assert _swiss_rounds_for_players(5) == 3
    assert _swiss_rounds_for_players(8) == 3
    assert _swiss_rounds_for_players(9) == 4
    assert _swiss_rounds_for_players(16) == 4
    assert _swiss_rounds_for_players(17) == 5
    assert _swiss_rounds_for_players(32) == 5
    assert _swiss_rounds_for_players(33) == 6
    assert _swiss_rounds_for_players(64) == 6


# --- Integration tests (require DATABASE_URL; skip otherwise) ---


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
        # Touch the DB to ensure we can connect (e.g. skip in CI when DB is unreachable)
        session.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Database unreachable (e.g. no network)")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# Deck IDs and event IDs used only in tests to avoid clashes
_TEST_EVENT_PREFIX = "test_cm_"
_TEST_DECK_ID_BASE = 989000


def _make_deck(deck_id: int, event_id: str, player: str, event_name: str = "Test Event", date: str = "01/01/25"):
    return {
        "deck_id": deck_id,
        "event_id": event_id,
        "format_id": "ST",
        "name": f"Deck {deck_id}",
        "player": player,
        "event_name": event_name,
        "date": date,
        "rank": "",
        "player_count": 4,
        "mainboard": [{"qty": 1, "card": "Card"}],
        "sideboard": [],
        "commanders": [],
        "archetype": None,
    }


def test_list_event_ids_with_complete_matchups_empty_event_included(db_session_rollback):
    """Event with zero decks is considered 'complete' (included in the list)."""
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "empty"
    create_event(
        session, event_name="Empty", date="01/01/25", format_id="ST", origin="manual", event_id=eid, player_count=0
    )
    session.flush()  # session has autoflush=False; flush so the query inside sees test data
    result = list_event_ids_with_complete_matchups(session)
    assert eid in result


def test_list_event_ids_with_complete_matchups_complete_event_included(db_session_rollback):
    """Event where every deck has expected matchups (2 rounds for 4 players) is included."""
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "ok"
    create_event(
        session, event_name="Complete", date="01/01/25", format_id="ST", origin="manual", event_id=eid, player_count=4
    )
    # 4 decks -> expected 2 rounds (each deck must have 2 distinct opponents)
    decks = [
        _make_deck(_TEST_DECK_ID_BASE + 1, eid, "Alice"),
        _make_deck(_TEST_DECK_ID_BASE + 2, eid, "Bob"),
        _make_deck(_TEST_DECK_ID_BASE + 3, eid, "Carol"),
        _make_deck(_TEST_DECK_ID_BASE + 4, eid, "Dave"),
    ]
    for d in decks:
        upsert_deck(session, d, origin="manual")
    # Matchups: each deck reports 2 opponents (round 1 and round 2)
    # d1 vs d2, d1 vs d3; d2 vs d1, d2 vs d4; d3 vs d1, d3 vs d4; d4 vs d2, d4 vs d3
    upsert_matchups_for_deck(
        session,
        _TEST_DECK_ID_BASE + 1,
        [
            {"opponent_player": "Bob", "opponent_deck_id": _TEST_DECK_ID_BASE + 2, "result": "win"},
            {"opponent_player": "Carol", "opponent_deck_id": _TEST_DECK_ID_BASE + 3, "result": "loss"},
        ],
    )
    upsert_matchups_for_deck(
        session,
        _TEST_DECK_ID_BASE + 2,
        [
            {"opponent_player": "Alice", "opponent_deck_id": _TEST_DECK_ID_BASE + 1, "result": "loss"},
            {"opponent_player": "Dave", "opponent_deck_id": _TEST_DECK_ID_BASE + 4, "result": "win"},
        ],
    )
    upsert_matchups_for_deck(
        session,
        _TEST_DECK_ID_BASE + 3,
        [
            {"opponent_player": "Alice", "opponent_deck_id": _TEST_DECK_ID_BASE + 1, "result": "win"},
            {"opponent_player": "Dave", "opponent_deck_id": _TEST_DECK_ID_BASE + 4, "result": "loss"},
        ],
    )
    upsert_matchups_for_deck(
        session,
        _TEST_DECK_ID_BASE + 4,
        [
            {"opponent_player": "Bob", "opponent_deck_id": _TEST_DECK_ID_BASE + 2, "result": "loss"},
            {"opponent_player": "Carol", "opponent_deck_id": _TEST_DECK_ID_BASE + 3, "result": "win"},
        ],
    )
    session.flush()  # session has autoflush=False; flush so the query inside sees test data
    result = list_event_ids_with_complete_matchups(session)
    assert eid in result


def test_list_event_ids_with_complete_matchups_missing_matchups_excluded(db_session_rollback):
    """Event where at least one deck has fewer than expected matchups is excluded.
    'Complete' counts effective opponents = (reported by this deck) | (reported against this deck).
    So we need a deck with only 1 effective opponent: base+1 reports only vs base+2, and only base+2 reports vs base+1.
    base+3 must not report vs base+1 (else base+1 would have 2 effective)."""
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "missing"
    create_event(
        session, event_name="Missing", date="01/01/25", format_id="ST", origin="manual", event_id=eid, player_count=4
    )
    for i, name in enumerate(["Alice", "Bob", "Carol", "Dave"], start=1):
        upsert_deck(session, _make_deck(_TEST_DECK_ID_BASE + 10 + i, eid, name), origin="manual")
    base = _TEST_DECK_ID_BASE + 10
    # base+1 (Alice): only vs base+2; only base+2 reports vs base+1 -> effective 1, expected 2 -> missing
    upsert_matchups_for_deck(
        session, base + 1, [{"opponent_player": "Bob", "opponent_deck_id": base + 2, "result": "win"}]
    )
    upsert_matchups_for_deck(
        session,
        base + 2,
        [
            {"opponent_player": "Alice", "opponent_deck_id": base + 1, "result": "loss"},
            {"opponent_player": "Dave", "opponent_deck_id": base + 4, "result": "win"},
            {"opponent_player": "Carol", "opponent_deck_id": base + 3, "result": "win"},
        ],
    )
    # base+3 reports vs base+2 and base+4 only (not vs base+1)
    upsert_matchups_for_deck(
        session,
        base + 3,
        [
            {"opponent_player": "Bob", "opponent_deck_id": base + 2, "result": "loss"},
            {"opponent_player": "Dave", "opponent_deck_id": base + 4, "result": "loss"},
        ],
    )
    upsert_matchups_for_deck(
        session,
        base + 4,
        [
            {"opponent_player": "Bob", "opponent_deck_id": base + 2, "result": "loss"},
            {"opponent_player": "Carol", "opponent_deck_id": base + 3, "result": "win"},
        ],
    )
    session.flush()  # session has autoflush=False; flush so the query inside sees test data
    result = list_event_ids_with_complete_matchups(session)
    assert eid not in result


def test_list_missing_matchups_for_event_complete_returns_empty(db_session_rollback):
    """list_missing_matchups_for_event returns [] when all decks have expected matchups."""
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "single_ok"
    create_event(
        session, event_name="OK", date="01/01/25", format_id="ST", origin="manual", event_id=eid, player_count=2
    )
    base = _TEST_DECK_ID_BASE + 20
    upsert_deck(session, _make_deck(base + 1, eid, "A"), origin="manual")
    upsert_deck(session, _make_deck(base + 2, eid, "B"), origin="manual")
    # 2 players -> 1 round; each reports the other
    upsert_matchups_for_deck(session, base + 1, [{"opponent_player": "B", "opponent_deck_id": base + 2, "result": "win"}])
    upsert_matchups_for_deck(session, base + 2, [{"opponent_player": "A", "opponent_deck_id": base + 1, "result": "loss"}])
    session.flush()  # session has autoflush=False; flush so the query inside sees test data
    missing = list_missing_matchups_for_event(session, eid)
    assert missing == []


def test_list_missing_matchups_for_event_missing_returns_deck(db_session_rollback):
    """list_missing_matchups_for_event returns deck(s) with fewer than expected matchups."""
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "single_miss"
    create_event(
        session, event_name="Miss", date="01/01/25", format_id="ST", origin="manual", event_id=eid, player_count=4
    )
    base = _TEST_DECK_ID_BASE + 30
    for i, name in enumerate(["P1", "P2", "P3", "P4"], start=1):
        upsert_deck(session, _make_deck(base + i, eid, name), origin="manual")
    # Only P1 has 2 matchups; P2 has 0
    upsert_matchups_for_deck(
        session,
        base + 1,
        [
            {"opponent_player": "P2", "opponent_deck_id": base + 2, "result": "win"},
            {"opponent_player": "P3", "opponent_deck_id": base + 3, "result": "loss"},
        ],
    )
    session.flush()  # session has autoflush=False; flush so the query inside sees test data
    missing = list_missing_matchups_for_event(session, eid)
    assert len(missing) >= 1
    deck_ids_missing = {m["deck_id"] for m in missing}
    # P1 has 2 opponents; P2 and P3 each have 1 (reported by P1); P4 has 0. So P2, P3, P4 are missing.
    assert (base + 2) in deck_ids_missing
    assert (base + 3) in deck_ids_missing
    assert (base + 4) in deck_ids_missing
    assert (base + 1) not in deck_ids_missing
