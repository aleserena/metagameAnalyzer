from api.db import DeckRow, MatchupRow
from api.schemas.events import EventExportData
from api.services.event_import import import_event_payload


def _deck(did, player):
    return {
        "deck_id": did,
        "event_id": "old",
        "format_id": "EDH",
        "name": "D",
        "player": player,
        "event_name": "Imp",
        "date": "03/03/25",
        "rank": "",
        "player_count": 2,
        "mainboard": [],
        "sideboard": [],
        "commanders": [],
        "archetype": "Arch " + player,
    }


def _payload(matchups):
    return EventExportData(
        schema_version=1,
        event={
            "event_id": "old",
            "event_name": "Imp",
            "date": "03/03/25",
            "format_id": "EDH",
            "player_count": 2,
        },
        decks=[_deck(1, "Imp A"), _deck(2, "Imp B")],
        matchups=matchups,
        player_emails={},
        players=[],
    )


def _m(deck_id, opp_player, opp_deck_id, result, rnd):
    return {
        "deck_id": deck_id,
        "opponent_player": opp_player,
        "opponent_deck_id": opp_deck_id,
        "opponent_archetype": None,
        "result": result,
        "result_note": "",
        "round": rnd,
    }


def test_both_sides_are_imported_once(db_session_rollback):
    session = db_session_rollback
    out = import_event_payload(
        session,
        _payload(
            [
                _m(1, "Imp B", 2, "win", 1),
                _m(2, "Imp A", 1, "loss", 1),
                _m(1, "Bye", None, "bye", 2),
            ]
        ),
    )
    session.flush()
    ids = {
        r.player: r.deck_id
        for r in session.query(DeckRow).filter(DeckRow.event_id == out["event_id"])
    }
    rows = session.query(MatchupRow).filter(MatchupRow.deck_id.in_(ids.values())).all()
    assert out["matchup_count"] == 3
    assert len(rows) == 3
    a_vs_b = [r for r in rows if r.deck_id == ids["Imp A"] and r.round == 1]
    assert len(a_vs_b) == 1
    assert (a_vs_b[0].result, a_vs_b[0].opponent_deck_id) == ("win", ids["Imp B"])
    assert a_vs_b[0].opponent_player_id is not None


def test_one_sided_report_stays_one_sided(db_session_rollback):
    session = db_session_rollback
    out = import_event_payload(session, _payload([_m(1, "Imp B", 2, "win", 1)]))
    assert out["matchup_count"] == 1


def test_rows_pointing_outside_the_file(db_session_rollback):
    session = db_session_rollback
    out = import_event_payload(
        session,
        _payload(
            [
                _m(1, "Stranger", 999, "win", 1),  # opponent deck not in file: kept, no opponent deck
                _m(999, "Imp A", 1, "loss", 1),  # own deck not in file: skipped
            ]
        ),
    )
    session.flush()
    assert out["matchup_count"] == 1
    row = session.query(MatchupRow).filter(MatchupRow.opponent_player == "Stranger").one()
    assert row.opponent_deck_id is None


def test_imported_decks_carry_the_event_display_name(db_session_rollback):
    from api.db import EventRow
    from src.mtgtop8.scraper import event_display_name

    session = db_session_rollback
    payload = _payload([])
    payload.event.store = "Card Shop"
    payload.event.location = "Town"
    out = import_event_payload(session, payload)
    session.flush()
    ev = session.query(EventRow).filter(EventRow.event_id == out["event_id"]).one()
    expected = event_display_name(ev.name, ev.store, ev.location)
    assert "@" in expected
    names = {d.event_name for d in session.query(DeckRow).filter(DeckRow.event_id == out["event_id"])}
    assert names == {expected}
