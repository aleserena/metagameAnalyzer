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


def test_event_date_follows_the_text_date(db_session_rollback):
    from datetime import date

    session = db_session_rollback
    row = create_event(session, "Dates", "05/03/25", "EDH", event_id="test_dates_1", player_count=1)
    assert row.event_date == date(2025, 3, 5)
    row.date = "not a date"
    assert row.event_date is None
    assert row.date == "not a date"


def test_events_are_listed_newest_first_with_undated_last(db_session_rollback):
    from api.db import get_all_events

    session = db_session_rollback
    for eid, d in (("test_dates_a", "31/01/25"), ("test_dates_b", "01/02/25"), ("test_dates_c", "")):
        create_event(session, "Dates", d, "EDH", event_id=eid, player_count=1)
    session.flush()
    ids = [e["event_id"] for e in get_all_events(session) if str(e["event_id"]).startswith("test_dates_")]
    assert ids == ["test_dates_b", "test_dates_a", "test_dates_c"]


def test_deck_date_copied_from_event_sets_event_date(db_session_rollback):
    from datetime import date

    session = db_session_rollback
    create_event(session, "Dates", "05/03/25", "EDH", event_id="test_dates_sync", player_count=1)
    deck = DeckRow(date="01/01/24")
    assert deck.event_date == date(2024, 1, 1)


def test_migration_parser_matches_the_runtime_parser():
    import importlib.util
    from pathlib import Path

    from api.dates import parse_ddmmyy

    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "017_event_date_columns.py"
    spec = importlib.util.spec_from_file_location("m017", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for s in ("05/03/25", "05/03/2025", "31/02/25", "", "garbage", " 01/01/24 "):
        assert mod._parse(s) == parse_ddmmyy(s)
