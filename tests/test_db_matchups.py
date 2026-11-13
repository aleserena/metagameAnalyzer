"""Tests for matchup-related DB helpers: _swiss_rounds_for_players, list_event_ids_with_complete_matchups, list_missing_matchups_for_event."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.schemas.matchups import MatchupItem

from api.db import (
    DeckRow,
    _swiss_rounds_for_players,
    create_event,
    list_event_ids_with_complete_matchups,
    list_matchups_by_deck,
    list_matchups_reported_against_player_id,
    list_missing_matchups_for_event,
    upsert_deck,
    upsert_matchups_for_deck,
)


# --- Unit tests (no DB) ---


def test_matchup_item_rejects_empty_result():
    """MatchupItem validation rejects empty result (would be NULL/invalid in DB)."""
    with pytest.raises(ValidationError) as exc_info:
        MatchupItem(opponent_player="Alice", result="")
    assert "result" in str(exc_info.value).lower()


def test_matchup_item_rejects_missing_opponent_when_not_bye_drop():
    """MatchupItem requires opponent_player when result is not bye or drop."""
    with pytest.raises(ValidationError) as exc_info:
        MatchupItem(opponent_player="", result="win")
    assert "opponent" in str(exc_info.value).lower()
    with pytest.raises(ValidationError):
        MatchupItem(opponent_player="   ", result="loss")


def test_matchup_item_accepts_valid_and_bye_drop():
    """MatchupItem accepts valid items and bye/drop without opponent."""
    MatchupItem(opponent_player="Alice", result="win")
    MatchupItem(opponent_player="Bye", result="bye")
    MatchupItem(opponent_player="(drop)", result="drop")


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


def test_upsert_matchups_for_deck_skips_invalid_items(db_session_rollback):
    """upsert_matchups_for_deck does not insert rows with empty opponent_player or empty result."""
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "skip_invalid"
    base = _TEST_DECK_ID_BASE + 800
    create_event(
        session, event_name="SkipInvalid", date="01/01/25", format_id="EDH", origin="manual", event_id=eid
    )
    upsert_deck(session, _make_deck(base, eid, "P1"))
    upsert_deck(session, _make_deck(base + 1, eid, "P2"))
    session.flush()

    upsert_matchups_for_deck(
        session,
        base,
        [
            {"opponent_player": "P2", "opponent_deck_id": base + 1, "result": "win"},
            {"opponent_player": "", "opponent_deck_id": None, "result": "loss"},
            {"opponent_player": "P2", "opponent_deck_id": base + 1, "result": ""},
            {"opponent_player": "   ", "result": "draw"},
        ],
    )
    session.flush()
    rows = list_matchups_by_deck(session, base)
    assert len(rows) == 1
    assert rows[0]["opponent_player"] == "P2" and rows[0]["result"] == "win"
    assert "opponent_player_id" in rows[0]
    assert rows[0]["opponent_player_id"] is not None


def test_list_matchups_by_deck_includes_opponent_player_id(db_session_rollback):
    """list_matchups_by_deck returns rows with opponent_player_id (resolved from opponent_player)."""
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "opp_id"
    base = _TEST_DECK_ID_BASE + 900
    create_event(
        session, event_name="OppId", date="01/01/25", format_id="ST", origin="manual", event_id=eid, player_count=2
    )
    upsert_deck(session, _make_deck(base, eid, "Alpha"))
    upsert_deck(session, _make_deck(base + 1, eid, "Beta"))
    session.flush()
    upsert_matchups_for_deck(
        session,
        base,
        [{"opponent_player": "Beta", "opponent_deck_id": base + 1, "result": "win"}],
    )
    session.flush()
    rows = list_matchups_by_deck(session, base)
    assert len(rows) == 1
    assert "opponent_player_id" in rows[0]
    assert rows[0]["opponent_player_id"] is not None
    assert rows[0]["opponent_player"] == "Beta"
    assert rows[0]["result"] == "win"
    # Inverse row is stored for the opponent so both sides appear in the matrix
    opp_rows = list_matchups_by_deck(session, base + 1)
    assert len(opp_rows) == 1
    assert opp_rows[0]["opponent_player"] == "Alpha"
    assert opp_rows[0]["result"] == "loss"
    assert opp_rows[0]["opponent_deck_id"] == base


def test_upsert_matchups_removes_orphan_reports_against_player(db_session_rollback):
    """Saving deck A without a matchup removes B's report vs A even when opponent_deck_id was NULL."""
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "orphan_del"
    base = _TEST_DECK_ID_BASE + 960
    create_event(
        session, event_name="OrphanDel", date="01/01/25", format_id="ST", origin="manual", event_id=eid, player_count=2
    )
    upsert_deck(session, _make_deck(base, eid, "Alice"))
    upsert_deck(session, _make_deck(base + 1, eid, "Bob"))
    session.flush()
    alice_row = session.query(DeckRow).filter_by(deck_id=base).first()
    alice_pid = alice_row.player_id

    upsert_matchups_for_deck(
        session,
        base + 1,
        [{"opponent_player": "Alice", "opponent_deck_id": None, "result": "loss", "round": 1}],
    )
    session.flush()
    assert len(list_matchups_reported_against_player_id(session, eid, alice_pid)) == 1

    upsert_matchups_for_deck(session, base, [])
    session.flush()
    assert list_matchups_reported_against_player_id(session, eid, alice_pid) == []
    assert list_matchups_by_deck(session, base) == []


def test_upsert_same_opponent_different_rounds(db_session_rollback):
    """Same opponent in Swiss and Top 8 (different round) is stored as two rows."""
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "dup_round"
    base = _TEST_DECK_ID_BASE + 950
    create_event(
        session, event_name="DupRound", date="01/01/25", format_id="ST", origin="manual", event_id=eid, player_count=8
    )
    deck_a = _make_deck(base, eid, "Alice")
    deck_a["rank"] = "1"
    deck_b = _make_deck(base + 1, eid, "Bob")
    deck_b["rank"] = "2"
    upsert_deck(session, deck_a)
    upsert_deck(session, deck_b)
    session.flush()
    upsert_matchups_for_deck(
        session,
        base,
        [
            {"opponent_player": "Bob", "opponent_deck_id": base + 1, "result": "win", "round": 1},
            {"opponent_player": "Bob", "opponent_deck_id": base + 1, "result": "loss", "round": 4},
        ],
    )
    session.flush()
    rows = list_matchups_by_deck(session, base)
    bob_rows = [r for r in rows if r["opponent_player"] == "Bob"]
    assert len(bob_rows) == 2
    rounds = sorted(r["round"] for r in bob_rows)
    assert rounds == [1, 4]


def test_match_record_counts_intentional_draw_winners(db_session_rollback):
    from api.db import match_record_for_decks

    session = db_session_rollback
    eid = f"{_TEST_EVENT_PREFIX}record"
    create_event(session, "Rec", "01/01/25", "ST", event_id=eid, player_count=4)
    upsert_deck(session, _make_deck(_TEST_DECK_ID_BASE + 901, eid, "Rec Player"))
    session.flush()
    upsert_matchups_for_deck(
        session,
        _TEST_DECK_ID_BASE + 901,
        [
            {"opponent_player": "Rec Opp 1", "result": "win", "round": 1},
            {"opponent_player": "Rec Opp 2", "result": "intentional_draw_win", "round": 2},
            {"opponent_player": "Rec Opp 3", "result": "intentional_draw_loss", "round": 3},
            {"opponent_player": "Rec Opp 4", "result": "draw", "round": 4},
            {"opponent_player": "Bye", "result": "bye", "round": 5},
        ],
    )
    session.flush()
    assert match_record_for_decks(session, [_TEST_DECK_ID_BASE + 901]) == {
        "recorded_matches": 4,
        "match_wins": 2,
        "match_losses": 1,
        "match_draws": 1,
        "match_win_pct": 50.0,
    }


def test_update_matchup_mirrors_result_and_round(db_session_rollback):
    from api.db import MatchupRow, update_matchup

    session = db_session_rollback
    eid = f"{_TEST_EVENT_PREFIX}patch"
    a, b = _TEST_DECK_ID_BASE + 911, _TEST_DECK_ID_BASE + 912
    create_event(session, "Patch", "01/01/25", "ST", event_id=eid, player_count=2)
    upsert_deck(session, _make_deck(a, eid, "Patch A"))
    upsert_deck(session, _make_deck(b, eid, "Patch B"))
    session.flush()
    upsert_matchups_for_deck(
        session, a, [{"opponent_player": "Patch B", "opponent_deck_id": b, "result": "win", "round": 1}]
    )
    session.flush()
    mine = session.query(MatchupRow).filter(MatchupRow.deck_id == a).one()
    assert update_matchup(session, mine.id, result="loss", round=2) is True
    session.flush()
    theirs = session.query(MatchupRow).filter(MatchupRow.deck_id == b).one()
    assert (theirs.result, theirs.round) == ("win", 2)


def test_matchup_listings_do_not_select_decklists(db_session_rollback, sql_log):
    from api.db import list_matchups_with_deck_and_players, list_matchups_with_deck_info

    session = db_session_rollback
    eid = f"{_TEST_EVENT_PREFIX}slim"
    a, b = _TEST_DECK_ID_BASE + 921, _TEST_DECK_ID_BASE + 922
    create_event(session, "Slim", "01/01/25", "ST", event_id=eid, player_count=2)
    upsert_deck(session, _make_deck(a, eid, "Slim A"))
    upsert_deck(session, _make_deck(b, eid, "Slim B"))
    session.flush()
    upsert_matchups_for_deck(
        session, a, [{"opponent_player": "Slim B", "opponent_deck_id": b, "result": "win", "round": 1}]
    )
    session.flush()
    sql_log.clear()
    info = [r for r in list_matchups_with_deck_info(session) if r["event_id"] == eid]
    players = [r for r in list_matchups_with_deck_and_players(session) if r["event_id"] == eid]
    against = list_matchups_reported_against_player_id(session, eid, players[0]["opponent_player_id"])
    assert against
    assert not any("mainboard" in s or "sideboard" in s for s in sql_log)
    assert set(info[0]) == {
        "deck_id",
        "opponent_deck_id",
        "archetype",
        "format_id",
        "event_id",
        "date",
        "opponent_archetype",
        "result",
        "result_note",
        "round",
    }
    assert set(players[0]) == set(info[0]) | {"player_id", "opponent_player_id", "player", "opponent_player"}
    assert sorted((r["player"], r["opponent_player"], r["result"]) for r in players) == [
        ("Slim A", "Slim B", "win"),
        ("Slim B", "Slim A", "loss"),
    ]


def test_byes_count_in_the_bulk_completeness_check(db_session_rollback):
    session = db_session_rollback
    eid = f"{_TEST_EVENT_PREFIX}byes"
    a, b, c = (_TEST_DECK_ID_BASE + n for n in (931, 932, 933))
    create_event(session, "Byes", "01/01/25", "ST", event_id=eid, player_count=3)
    for did, name in ((a, "Bye A"), (b, "Bye B"), (c, "Bye C")):
        upsert_deck(session, _make_deck(did, eid, name))
    session.flush()
    upsert_matchups_for_deck(session, b, [{"opponent_player": "Bye", "result": "bye", "round": 2}])
    upsert_matchups_for_deck(session, c, [{"opponent_player": "Bye", "result": "bye", "round": 1}])
    session.flush()
    upsert_matchups_for_deck(session, a, [
        {"opponent_player": "Bye B", "opponent_deck_id": b, "result": "win", "round": 1},
        {"opponent_player": "Bye C", "opponent_deck_id": c, "result": "win", "round": 2}])
    session.flush()
    assert list_missing_matchups_for_event(session, eid) == []
    assert eid in list_event_ids_with_complete_matchups(session)


# --- Single-elimination events: expected matches come from each deck's rank ---

from tests._bracket_fixture import rank_for_seed, seed_bracket  # noqa: E402

_SE_BASE = _TEST_DECK_ID_BASE + 500


def test_bracket_fixture_ranks():
    assert [rank_for_seed(s, 16) for s in (0, 1, 2, 3, 4, 7, 8, 15)] == ["1", "2", "3-4", "3-4", "5-8", "5-8", "9-16", "9-16"]


def test_single_elim_complete_bracket_not_missing(db_session_rollback):
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "se_ok"
    seed_bracket(session, eid, 16, _SE_BASE, player_count=44)
    assert list_missing_matchups_for_event(session, eid) == []
    assert eid in list_event_ids_with_complete_matchups(session)


def test_single_elim_semifinalist_missing_one(db_session_rollback):
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "se_semi"
    ids = seed_bracket(session, eid, 16, _SE_BASE, player_count=44, skip=frozenset({(0, 2)}))
    missing = {m["deck_id"]: m for m in list_missing_matchups_for_event(session, eid)}
    assert (missing[ids[2]]["matchup_count"], missing[ids[2]]["expected_count"]) == (2, 3)
    assert (missing[ids[0]]["matchup_count"], missing[ids[0]]["expected_count"]) == (3, 4)
    assert set(missing) == {ids[0], ids[2]}
    assert eid not in list_event_ids_with_complete_matchups(session)


def test_single_elim_outside_bracket_not_missing(db_session_rollback):
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "se_out"
    seed_bracket(session, eid, 8, _SE_BASE, player_count=30)
    extra = _make_deck(_SE_BASE + 100, eid, "League only")
    extra["rank"] = "17-32"
    upsert_deck(session, extra, origin="manual")
    session.flush()
    assert list_missing_matchups_for_event(session, eid) == []
    assert eid in list_event_ids_with_complete_matchups(session)


def test_single_elim_bye_counts_as_match(db_session_rollback):
    from api.db import MatchupRow

    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "se_bye"
    ids = seed_bracket(session, eid, 8, _SE_BASE, skip=frozenset({(3, 7)}))
    # Seed 7 (5-8) never played: give it a first-round bye; seed 3 then lacks its first-round match too.
    session.add(MatchupRow(deck_id=ids[7], opponent_player="Bye", result="bye", round=1))
    session.add(MatchupRow(deck_id=ids[3], opponent_player="Bye", result="bye", round=1))
    session.flush()
    assert list_missing_matchups_for_event(session, eid) == []


def test_swiss_event_with_same_bracket_still_uses_swiss_rule(db_session_rollback):
    """Same data, Swiss structure: 16 decks -> 4 rounds expected from every deck, so early losers are missing."""
    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "se_swiss"
    ids = seed_bracket(session, eid, 16, _SE_BASE, structure=None)
    missing = {m["deck_id"]: m["expected_count"] for m in list_missing_matchups_for_event(session, eid)}
    assert missing[ids[15]] == 4
    assert ids[0] not in missing


def test_missing_decks_uses_bracket_size(db_session_rollback):
    from api.db import list_event_ids_with_missing_decks, update_event

    session = db_session_rollback
    eid = _TEST_EVENT_PREFIX + "se_decks"
    seed_bracket(session, eid, 16, _SE_BASE, player_count=44)
    assert eid not in list_event_ids_with_missing_decks(session)
    update_event(session, eid, structure="swiss", bracket_size=None)
    session.flush()
    assert eid in list_event_ids_with_missing_decks(session)
