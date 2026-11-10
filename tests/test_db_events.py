from api.db import DeckRow, create_event, sync_decks_with_event, update_event, upsert_deck

EID = "test_ev_sync_1"


def _deck(deck_id, player):
    return {
        "deck_id": deck_id,
        "event_id": EID,
        "format_id": "EDH",
        "name": "D",
        "player": player,
        "event_name": "Old Name",
        "date": "01/01/25",
        "rank": "",
        "player_count": 8,
        "mainboard": [],
        "sideboard": [],
        "commanders": [],
        "archetype": None,
    }


def _seed(session):
    create_event(session, "Old Name", "01/01/25", "EDH", event_id=EID, player_count=8)
    upsert_deck(session, _deck(987001, "Sync A"))
    upsert_deck(session, _deck(987002, "Sync B"))
    session.flush()


def test_update_event_propagates_to_decks(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    update_event(
        session,
        EID,
        event_name="New",
        date="02/02/25",
        format_id="cEDH",
        player_count=40,
        store="Shop",
        location="City",
    )
    session.flush()
    rows = session.query(DeckRow).filter(DeckRow.event_id == EID).all()
    assert len(rows) == 2
    for row in rows:
        assert (row.event_name, row.date, row.format_id, row.player_count) == (
            "New @ Shop (City)",
            "02/02/25",
            "cEDH",
            40,
        )


def test_single_field_edit_leaves_other_copies_alone(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    update_event(session, EID, player_count=0)
    session.flush()
    row = session.query(DeckRow).filter(DeckRow.deck_id == 987001).one()
    assert (row.event_name, row.date, row.format_id, row.player_count) == (
        "Old Name",
        "01/01/25",
        "EDH",
        8,
    )


def test_sync_reports_number_of_changed_decks(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    session.query(DeckRow).filter(DeckRow.deck_id == 987002).one().date = "09/09/24"
    session.flush()
    assert sync_decks_with_event(session, EID) == 1
