"""Tables and columns added by migration 019: event snapshots, change log, manual_fields."""

from api import db


def _deck(session, event_id="snapdb_ev_1", deck_id=991001, player="Snap Player"):
    db.create_event(session, "Snapshot test", "01/01/25", "EDH", event_id=event_id, player_count=2)
    row = db.upsert_deck(
        session,
        {
            "deck_id": deck_id,
            "event_id": event_id,
            "format_id": "EDH",
            "name": "Deck",
            "player": player,
            "event_name": "Snapshot test",
            "date": "01/01/25",
            "rank": "1",
            "player_count": 2,
            "commanders": [],
            "mainboard": [{"qty": 1, "card": "Sol Ring"}],
            "sideboard": [],
        },
    )
    session.flush()
    return row


def test_event_snapshot_row_round_trips(db_session_rollback):
    session = db_session_rollback
    row = db.EventSnapshotRow(
        event_id="snapdb_ev_1",
        event_name="Snapshot test",
        created_at=db.utcnow_naive(),
        reason="delete",
        payload_hash="a" * 64,
        payload={"decks": [{"deck_id": 1}], "matchups": []},
    )
    session.add(row)
    session.flush()
    session.expire(row)
    assert row.id is not None
    assert row.payload["decks"] == [{"deck_id": 1}]
    assert row.reason == "delete"


def test_snapshot_outlives_its_event(db_session_rollback):
    """No foreign key to events: a snapshot must survive the delete it protects against."""
    session = db_session_rollback
    session.add(
        db.EventSnapshotRow(
            event_id="event_that_never_existed",
            event_name="Gone",
            created_at=db.utcnow_naive(),
            reason="delete",
            payload_hash="b" * 64,
            payload={},
        )
    )
    session.flush()


def test_change_log_row_round_trips(db_session_rollback):
    session = db_session_rollback
    row = db.ChangeLogRow(
        at=db.utcnow_naive(), actor="admin", action="deck.update", event_id="snapdb_ev_1", deck_id=5, summary="x"
    )
    session.add(row)
    session.flush()
    session.expire(row)
    assert (row.actor, row.action, row.event_id, row.deck_id, row.summary) == (
        "admin",
        "deck.update",
        "snapdb_ev_1",
        5,
        "x",
    )


def test_manual_fields_default_to_null_and_store_a_list(db_session_rollback):
    session = db_session_rollback
    deck = _deck(session)
    event = db.get_event(session, "snapdb_ev_1")
    assert deck.manual_fields is None and event.manual_fields is None
    deck.manual_fields = ["player"]
    event.manual_fields = ["name"]
    session.flush()
    session.expire_all()
    assert deck.manual_fields == ["player"]
    assert event.manual_fields == ["name"]
