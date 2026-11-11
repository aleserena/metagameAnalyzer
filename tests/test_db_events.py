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


def test_date_is_a_view_of_event_date(db_session_rollback):
    from datetime import date

    session = db_session_rollback
    row = create_event(session, "Dates", "05/03/2025", "EDH", event_id="test_dates_1", player_count=1)
    assert row.event_date == date(2025, 3, 5)
    assert row.date == "05/03/25"
    row.date = "not a date"
    assert row.event_date is None
    assert row.date == ""


def test_date_property_round_trips_without_a_text_column(db_session_rollback):
    from api.db import EventRow, event_row_to_dict

    session = db_session_rollback
    create_event(session, "Dates", "05/03/2025", "EDH", event_id="test_dates_2", player_count=1)
    session.flush()
    session.expire_all()
    assert event_row_to_dict(session.get(EventRow, "test_dates_2"))["date"] == "05/03/25"
    assert "date" not in EventRow.__table__.columns and "date" not in DeckRow.__table__.columns


def test_date_in_a_query_renders_the_text(db_session_rollback):
    from api.db import EventRow

    session = db_session_rollback
    for eid, d in (("test_dates_q1", "05/03/25"), ("test_dates_q2", "")):
        create_event(session, "Dates", d, "EDH", event_id=eid, player_count=1)
    session.flush()
    rows = session.query(EventRow.event_id, EventRow.date).filter(EventRow.event_id.like("test_dates_q%")).all()
    assert {r.event_id: r.date for r in rows} == {"test_dates_q1": "05/03/25", "test_dates_q2": ""}


def test_events_are_listed_newest_first_with_undated_last(db_session_rollback):
    from api.db import get_all_events

    session = db_session_rollback
    for eid, d in (("test_dates_a", "31/01/25"), ("test_dates_b", "01/02/25"), ("test_dates_c", "")):
        create_event(session, "Dates", d, "EDH", event_id=eid, player_count=1)
    session.flush()
    ids = [e["event_id"] for e in get_all_events(session) if str(e["event_id"]).startswith("test_dates_")]
    assert ids == ["test_dates_b", "test_dates_a", "test_dates_c"]


def test_deck_constructor_date_sets_event_date(db_session_rollback):
    from datetime import date

    deck = DeckRow(date="01/01/24")
    assert deck.event_date == date(2024, 1, 1)


def test_sync_decks_with_event_updates_deck_event_date(db_session_rollback):
    from datetime import date

    session = db_session_rollback
    _seed(session)
    ev = create_event(session, "Old Name", "02/02/25", "EDH", event_id="test_dates_sync2", player_count=8)
    session.flush()
    deck = session.query(DeckRow).filter(DeckRow.event_id == EID).first()
    deck.event_id = ev.event_id
    session.flush()
    sync_decks_with_event(session, ev.event_id)
    session.flush()
    assert deck.date == "02/02/25"
    assert deck.event_date == date(2025, 2, 2)


def _load_migration(filename):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename[:3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_parsers_match_the_runtime_parser():
    from api.dates import parse_ddmmyy

    for filename in ("017_event_date_columns.py", "018_drop_text_dates.py"):
        mod = _load_migration(filename)
        for s in ("05/03/25", "05/03/2025", "31/02/25", "", "garbage", " 01/01/24 "):
            assert mod._parse(s) == parse_ddmmyy(s)


def _with_text_date_columns(session, values):
    """Re-create the pre-018 text columns inside the rolled-back transaction and seed one event+deck per value."""
    from sqlalchemy import text

    from api.db import PlayerRow

    player = PlayerRow(display_name="Zzm018 Player")
    session.add(player)
    session.flush()
    for i in range(len(values)):
        create_event(session, "M018", "", "EDH", event_id=f"test_m018_{i}", player_count=1)
        session.add(
            DeckRow(
                deck_id=990000 + i,
                event_id=f"test_m018_{i}",
                player_id=player.id,
                commanders=[],
                mainboard=[],
                sideboard=[],
            )
        )
    session.flush()
    for table in ("events", "decks"):
        session.execute(text(f"ALTER TABLE {table} ADD COLUMN date VARCHAR(32) NOT NULL DEFAULT ''"))
    for i, (txt, stored) in enumerate(values):
        params = {"t": txt, "d": stored, "e": f"test_m018_{i}", "k": 990000 + i}
        session.execute(text("UPDATE events SET date = :t, event_date = :d WHERE event_id = :e"), params)
        session.execute(text("UPDATE decks SET date = :t, event_date = :d WHERE deck_id = :k"), params)


def test_migration_018_syncs_null_and_stale_dates_before_dropping(db_session_rollback):
    from datetime import date

    from sqlalchemy import text

    session = db_session_rollback
    mod = _load_migration("018_drop_text_dates.py")
    # (text date, stored event_date): written by the old release (NULL), edited by it (stale), cleared, in sync
    values = [("05/03/25", None), ("06/03/25", date(2020, 1, 1)), ("", date(2020, 1, 1)), ("07/03/2025", date(2025, 3, 7))]
    _with_text_date_columns(session, values)
    mod._sync(session.connection())
    mod._check(session.connection())
    want = [date(2025, 3, 5), date(2025, 3, 6), None, date(2025, 3, 7)]
    got_events = [
        r[0] for r in session.execute(text("SELECT event_date FROM events WHERE event_id LIKE 'test_m018_%' ORDER BY event_id"))
    ]
    got_decks = [
        r[0]
        for r in session.execute(
            text("SELECT event_date FROM decks WHERE deck_id >= 990000 AND deck_id < 990010 ORDER BY deck_id")
        )
    ]
    assert got_events == want and got_decks == want


def test_migration_018_refuses_to_drop_an_unparseable_or_out_of_range_date(db_session_rollback):
    from datetime import date

    import pytest

    session = db_session_rollback
    mod = _load_migration("018_drop_text_dates.py")
    _with_text_date_columns(session, [("junk", None), ("05/03/1999", None)])
    mod._sync(session.connection())
    with pytest.raises(RuntimeError) as err:
        mod._check(session.connection())
    message = str(err.value)
    assert "cannot be parsed" in message and "'junk'" in message
    assert "outside 2000-2099" in message
    assert date(1999, 3, 5) == mod._parse("05/03/1999")
