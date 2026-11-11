from api import state as state_module
from api.db import (
    MANUAL_DECK_ID_START,
    DeckRow,
    create_event,
    create_upload_link,
    get_upload_link,
    next_manual_deck_id,
    next_manual_event_id,
    upsert_deck,
)


def _deck(deck_id, event_id, player):
    return {
        "deck_id": deck_id,
        "event_id": event_id,
        "format_id": "EDH",
        "name": "D",
        "player": player,
        "event_name": "Ids",
        "date": "01/01/25",
        "rank": "",
        "player_count": 1,
        "mainboard": [],
        "sideboard": [],
        "commanders": [],
    }


def test_id_allocation_takes_the_lock_before_the_insert(db_session_rollback, sql_log):
    session = db_session_rollback
    create_event(session, "Ids", "01/01/25", "EDH", event_id="test_ids_1", player_count=1)
    session.flush()
    sql_log.clear()
    did = next_manual_deck_id(session)
    upsert_deck(session, _deck(did, "test_ids_1", "Ids Player"))
    session.flush()
    lock = next(i for i, s in enumerate(sql_log) if "pg_advisory_xact_lock" in s)
    insert = next(i for i, s in enumerate(sql_log) if s.lstrip().upper().startswith("INSERT INTO DECKS"))
    assert lock < insert


def test_event_id_allocation_takes_the_lock(db_session_rollback, sql_log):
    next_manual_event_id(db_session_rollback)
    assert any("pg_advisory_xact_lock" in s for s in sql_log)


def test_link_can_be_read_for_update(db_session_rollback, sql_log):
    session = db_session_rollback
    create_event(session, "Ids", "01/01/25", "EDH", event_id="test_ids_2", player_count=1)
    create_upload_link(session, "tok-lock", "test_ids_2")
    session.flush()
    sql_log.clear()
    assert get_upload_link(session, "tok-lock", for_update=True).token == "tok-lock"
    assert any("FOR UPDATE" in s for s in sql_log)


def test_persist_assigns_distinct_consecutive_manual_ids(db_session_rollback, monkeypatch):
    session = db_session_rollback
    create_event(session, "Ids", "01/01/25", "EDH", event_id="test_ids_3", player_count=3)
    session.flush()

    class _Scope:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            session.flush()
            return False

    monkeypatch.setattr(state_module._db, "session_scope", lambda: _Scope())
    monkeypatch.setattr(state_module, "_database_available", lambda: True)
    monkeypatch.setattr(state_module, "_load_decks_from_db", lambda: None)
    decks = [
        _deck(None, "test_ids_3", "Ids A"),
        _deck(5, "test_ids_3", "Ids B"),
        _deck(MANUAL_DECK_ID_START + 50_000_000, "test_ids_3", "Ids C"),
    ]
    decks[0].pop("deck_id")
    state_module._persist_decks_to_db(decks, origin="manual", assign_manual_ids=True)
    assert decks[0]["deck_id"] >= MANUAL_DECK_ID_START
    assert decks[1]["deck_id"] == decks[0]["deck_id"] + 1
    assert decks[2]["deck_id"] == MANUAL_DECK_ID_START + 50_000_000
    ids = {r.deck_id for r in session.query(DeckRow).filter(DeckRow.event_id == "test_ids_3")}
    assert len(ids) == 3
