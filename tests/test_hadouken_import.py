"""Tests for api.services.hadouken (completing an event with Hadouken standings + matchups)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mtgtop8.hadouken import HadoukenEvent, HadoukenPairing, HadoukenStanding

from api import db as _db
from api.services.hadouken import (
    MATCH_NONE,
    MATCH_PARTIAL,
    MATCH_PLAYER,
    MATCH_REORDERED,
    apply_import,
    assign_places_by_points,
    build_preview,
    suggest_deck_matches,
)

# --- Unit tests (no DB) ---


def _deck(deck_id, player, player_id):
    return {"deck_id": deck_id, "player": player, "player_id": player_id}


def test_suggest_matches_by_resolved_player_id():
    decks = [_deck(1, "Leonardo Basualdo", 10)]
    out = suggest_deck_matches(["Leonardo Basualdo"], decks, {"Leonardo Basualdo": 10})
    assert out == {"Leonardo Basualdo": (1, MATCH_PLAYER)}


def test_suggest_matches_reordered_and_accent_insensitive():
    decks = [_deck(1, "Julián Masino", 10)]
    out = suggest_deck_matches(["Masino Julian"], decks, {"Masino Julian": None})
    assert out == {"Masino Julian": (1, MATCH_REORDERED)}


def test_suggest_matches_partial_needs_two_words_and_single_candidate():
    decks = [_deck(1, "Juan Perea", 10), _deck(2, "Juan Gomez", 11)]
    out = suggest_deck_matches(["Juan Manuel Perea", "Juan"], decks, {"Juan Manuel Perea": None, "Juan": None})
    assert out["Juan Manuel Perea"] == (1, MATCH_PARTIAL)
    assert out["Juan"] == (None, MATCH_NONE)  # one word is too weak to suggest


def test_suggest_matches_uses_each_deck_once_and_prefers_stronger_match():
    decks = [_deck(1, "Ana Lopez", 10)]
    out = suggest_deck_matches(["Lopez Ana", "Ana Lopez"], decks, {"Lopez Ana": None, "Ana Lopez": 10})
    assert out["Ana Lopez"] == (1, MATCH_PLAYER)
    assert out["Lopez Ana"] == (None, MATCH_NONE)


# --- Integration tests (require DATABASE_URL; rolled back) ---


@pytest.fixture
def db_session_rollback():
    """Session that rolls back so no data is committed. Skips when DATABASE_URL is unset or DB unreachable."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    if not _db.is_database_available():
        pytest.skip("DATABASE_URL not set")
    factory = _db.get_session_factory_cached()
    if factory is None:
        pytest.skip("DATABASE_URL not set")
    try:
        session = factory()
        session.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("Database unreachable (e.g. no network)")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


_EID = "test_hado_1"
# Unlikely to exist in any real database
_A, _B, _C, _D = "Zqxa Hadotest", "Zqxb Hadotest", "Zqxc Hadotest", "Zqxd Hadotest"


def _hadouken_event() -> HadoukenEvent:
    return HadoukenEvent(
        url="https://hadoleague.vercel.app/torneos/test",
        name="Fecha Test",
        date="09/10/26",
        format_id="EDH",
        store="Hadouken",
        player_count=4,
        standings=[
            HadoukenStanding(1, _A, 6, 2, 0, 0),
            HadoukenStanding(2, "Hadotest Zqxb", 3, 1, 1, 0),  # same player as _B, words reordered
            HadoukenStanding(3, _C, 1, 0, 1, 1),
            HadoukenStanding(4, _D, 1, 0, 1, 1),
        ],
        pairings=[
            HadoukenPairing(1, _A, "Hadotest Zqxb", 2, 1),
            HadoukenPairing(1, _C, _D, 1, 1),
            HadoukenPairing(2, _A, _C, 2, 0),
            HadoukenPairing(2, "Hadotest Zqxb", _D, 2, 0),
        ],
    )


def _setup_mtgtop8_event(session) -> dict[str, int]:
    """MTGTop8-like event with only the top 2 decks (players A and B)."""
    _db.create_event(
        session, event_name="Fecha Test", date="09/10/26", format_id="EDH", origin=_db.ORIGIN_MTGTOP8,
        event_id=_EID, player_count=2, store="Hadouken",
    )
    ids = {}
    for i, (player, rank) in enumerate(((_A, "1"), (_B, "2"))):
        deck_id = 988100 + i
        _db.upsert_deck(
            session,
            {"deck_id": deck_id, "event_id": _EID, "format_id": "EDH", "name": "X", "player": player,
             "event_name": "Fecha Test", "date": "09/10/26", "rank": rank, "player_count": 2,
             "mainboard": [{"qty": 1, "card": "Card"}], "sideboard": [], "commanders": ["Card"], "archetype": None},
            origin=_db.ORIGIN_MTGTOP8,
        )
        ids[player] = deck_id
    session.flush()
    return ids


def test_preview_suggests_matches_and_new_decks(db_session_rollback):
    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    preview = build_preview(session, _EID, _hadouken_event())
    by_name = {p["name"]: p for p in preview["players"]}
    assert (by_name[_A]["deck_id"], by_name[_A]["match"]) == (ids[_A], MATCH_PLAYER)
    assert (by_name["Hadotest Zqxb"]["deck_id"], by_name["Hadotest Zqxb"]["match"]) == (ids[_B], MATCH_REORDERED)
    assert by_name[_C]["deck_id"] is None and by_name[_D]["deck_id"] is None
    assert preview["warnings"] == []
    assert preview["conflicts"] == []
    assert len(preview["pairings"]) == 4


def test_preview_and_apply_reject_different_date(db_session_rollback):
    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    hev = _hadouken_event()
    hev.date = "10/10/26"
    with pytest.raises(ValueError, match="Dates do not match"):
        build_preview(session, _EID, hev)
    with pytest.raises(ValueError, match="Dates do not match"):
        apply_import(session, _EID, hev, {_A: ids[_A]})
    hev.date = ""  # unreadable date on the Hadouken page
    with pytest.raises(ValueError, match="Could not read the date"):
        build_preview(session, _EID, hev)


def test_apply_uses_edited_standings_for_new_deck_ranks(db_session_rollback):
    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    player_map = {_A: ids[_A], "Hadotest Zqxb": ids[_B], _C: None, _D: None}
    apply_import(
        session, _EID, _hadouken_event(), player_map,
        {_C: {"rank": 4, "points": 1}, _D: {"rank": 3, "points": 2}},  # swap 3rd and 4th
    )
    session.flush()
    decks = {d["player"]: d for d in _db.get_decks_by_event(session, _EID)}
    assert decks[_D]["rank"] == "3"
    assert decks[_C]["rank"] == "4"
    assert decks[_A]["rank"] == "1"  # MTGTop8 rank still untouched


def test_apply_rejects_invalid_standings_edits(db_session_rollback):
    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    player_map = {_A: ids[_A], "Hadotest Zqxb": ids[_B]}
    with pytest.raises(ValueError, match="only be used once"):
        apply_import(session, _EID, _hadouken_event(), player_map, {_C: {"rank": 1, "points": 1}})
    with pytest.raises(ValueError, match="1 or higher"):
        apply_import(session, _EID, _hadouken_event(), player_map, {_C: {"rank": 0, "points": 1}})
    with pytest.raises(ValueError, match="not on the Hadouken page"):
        apply_import(session, _EID, _hadouken_event(), player_map, {"Nobody": {"rank": 9, "points": 0}})


def test_assign_places_by_points_ties_follow_page_order():
    hev = _hadouken_event()
    # page order: A (6 pts), B (3), C (1), D (1) -> give D more points than B, and tie C with B
    hev.standings[3].points = 5
    hev.standings[2].points = 3
    original = assign_places_by_points(hev)
    places = {s.player: s.rank for s in hev.standings}
    assert places == {_A: 1, _D: 2, "Hadotest Zqxb": 3, _C: 4}  # B before C: same points, B is higher on the page
    assert original == {_A: 1, "Hadotest Zqxb": 2, _C: 3, _D: 4}


def test_preview_places_from_points_and_apply_uses_them(db_session_rollback):
    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    hev = _hadouken_event()
    hev.standings[3].points = 2  # D now above C by points (page has C 3rd, D 4th)
    preview = build_preview(session, _EID, hev)
    by_name = {p["name"]: p for p in preview["players"]}
    assert (by_name[_D]["rank"], by_name[_D]["hadouken_rank"]) == (3, 4)
    assert (by_name[_C]["rank"], by_name[_C]["hadouken_rank"]) == (4, 3)

    hev = _hadouken_event()  # apply re-downloads the page: places must be recomputed the same way
    hev.standings[3].points = 2
    apply_import(session, _EID, hev, {_A: ids[_A], "Hadotest Zqxb": ids[_B], _C: None, _D: None})
    session.flush()
    decks = {d["player"]: d for d in _db.get_decks_by_event(session, _EID)}
    assert (decks[_D]["rank"], decks[_C]["rank"]) == ("3", "4")


def test_preview_sorted_by_place(db_session_rollback):
    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    hev = _hadouken_event()
    hev.standings.reverse()
    preview = build_preview(session, _EID, hev)
    assert [p["rank"] for p in preview["players"]] == [1, 2, 3, 4]
    assert [d["deck_id"] for d in preview["decks"]] == [ids[_A], ids[_B]]  # ranks "1", "2"


def test_apply_creates_decks_and_both_sides_of_every_match(db_session_rollback):
    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    player_map = {_A: ids[_A], "Hadotest Zqxb": ids[_B], _C: None, _D: None}

    result = apply_import(session, _EID, _hadouken_event(), player_map)
    session.flush()

    assert result["decks_created"] == 2
    assert result["player_count"] == 4
    decks = {d["player"]: d for d in _db.get_decks_by_event(session, _EID)}
    assert set(decks) == {_A, _B, _C, _D}
    assert decks[_C]["rank"] == "3"
    assert decks[_A]["rank"] == "1"  # MTGTop8 rank untouched
    assert _db.get_event(session, _EID).player_count == 4

    rows = session.query(_db.MatchupRow).filter(
        _db.MatchupRow.deck_id.in_([d["deck_id"] for d in decks.values()])
    ).all()
    got = {(r.deck_id, r.opponent_deck_id, r.round): (r.result, r.result_note) for r in rows}
    a, b, c, d = (decks[p]["deck_id"] for p in (_A, _B, _C, _D))
    assert len(rows) == 8
    assert got[(a, b, 1)] == ("win", "2-1")
    assert got[(b, a, 1)] == ("loss", "1-2")
    assert got[(c, d, 1)] == ("draw", "1-1")
    assert got[(d, c, 1)] == ("draw", "1-1")
    assert got[(b, d, 2)] == ("win", "2-0")

    # The reordered spelling is remembered for the next import
    assert _db.resolve_name_to_player_id(session, "Hadotest Zqxb")[0] == decks[_B]["player_id"]


def test_apply_twice_does_not_duplicate(db_session_rollback):
    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    hev = _hadouken_event()
    apply_import(session, _EID, hev, {_A: ids[_A], "Hadotest Zqxb": ids[_B]})
    session.flush()
    # Second run: every player now resolves to a deck of the event
    preview = build_preview(session, _EID, hev)
    player_map = {p["name"]: p["deck_id"] for p in preview["players"]}
    assert None not in player_map.values()
    result = apply_import(session, _EID, hev, player_map)
    session.flush()
    assert result["decks_created"] == 0
    deck_ids = [d["deck_id"] for d in _db.get_decks_by_event(session, _EID)]
    assert len(deck_ids) == 4
    assert session.query(_db.MatchupRow).filter(_db.MatchupRow.deck_id.in_(deck_ids)).count() == 8


def test_apply_rejects_deck_used_twice(db_session_rollback):
    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    with pytest.raises(ValueError):
        apply_import(session, _EID, _hadouken_event(), {_A: ids[_A], _C: ids[_A]})


def test_apply_rejects_new_deck_for_player_already_in_event(db_session_rollback):
    session = db_session_rollback
    _setup_mtgtop8_event(session)
    with pytest.raises(ValueError):
        apply_import(session, _EID, _hadouken_event(), {_A: None})
