"""Every destructive action snapshots the events it touches first, in the same transaction."""

from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from api import db
from api.db import EventSnapshotRow
from api.services import snapshots as snap
from tests.test_snapshots import DECK_A, DECK_B, EID, _deck, seed


@pytest.fixture
def in_session(db_session_rollback, monkeypatch):
    """Run handlers (which open their own session_scope) inside the rolled-back test session."""
    session = db_session_rollback

    @contextmanager
    def scope():
        yield session
        session.flush()

    monkeypatch.setattr(db, "session_scope", scope)
    from api import state as state_module
    from api.routers import events as events_router

    monkeypatch.setattr(events_router, "_load_decks_from_db", lambda: None)
    monkeypatch.setattr(events_router, "_invalidate_events_cache", lambda: None)
    monkeypatch.setattr(state_module.state, "set_decks", lambda decks: None)
    return session


def _snapshots(session, event_id, reason):
    return (
        session.query(EventSnapshotRow)
        .filter(EventSnapshotRow.event_id == event_id, EventSnapshotRow.reason == reason)
        .order_by(EventSnapshotRow.id)
        .all()
    )


def _deck_ids(session, event_id):
    return {d["deck_id"] for d in db.get_decks_by_event(session, event_id)}


# ---- delete --------------------------------------------------------------------------------------


def test_deleting_an_event_snapshots_it_first(in_session):
    from api.routers.events import delete_event_endpoint

    session = in_session
    seed(session)
    delete_event_endpoint(EID)
    assert db.get_event(session, EID) is None

    (row,) = _snapshots(session, EID, "delete")
    snap.restore_snapshot(session, row.id)
    assert _deck_ids(session, EID) == {DECK_A, DECK_B}


def test_failed_snapshot_blocks_the_delete(in_session, monkeypatch):
    from api.routers import events as events_router

    session = in_session
    seed(session)

    def boom(*args, **kwargs):
        raise RuntimeError("snapshot storage failed")

    monkeypatch.setattr(events_router, "take_snapshot", boom)
    with pytest.raises(HTTPException) as exc:
        events_router.delete_event_endpoint(EID)
    assert exc.value.status_code == 500
    assert db.get_event(session, EID) is not None
    assert _deck_ids(session, EID) == {DECK_A, DECK_B}


# ---- merge ---------------------------------------------------------------------------------------


def test_merging_events_snapshots_both_first(in_session):
    from api.routers.events import merge_events
    from api.schemas.events import MergeEventsBody

    session = in_session
    seed(session)  # mtgtop8 event, kept
    db.create_event(session, "Manual twin", "01/01/25", "EDH", event_id="snap_ev_manual", player_count=2)
    db.upsert_deck(session, _deck(987021, "snap_ev_manual", "Snap Zed"), origin=db.ORIGIN_MANUAL)
    session.flush()

    merge_events(MergeEventsBody(event_id_keep=EID, event_id_remove="snap_ev_manual"))
    assert db.get_event(session, "snap_ev_manual") is None
    assert 987021 in _deck_ids(session, EID)

    (kept,) = _snapshots(session, EID, "merge")
    (removed,) = _snapshots(session, "snap_ev_manual", "merge")
    snap.restore_snapshot(session, removed.id)
    snap.restore_snapshot(session, kept.id)
    session.expire_all()
    assert _deck_ids(session, "snap_ev_manual") == {987021}
    assert _deck_ids(session, EID) == {DECK_A, DECK_B}


# ---- Hadouken import -----------------------------------------------------------------------------


def test_hadouken_import_snapshots_the_event_first(db_session_rollback):
    from api.services import hadouken as hado
    from tests.test_hadouken_import import _A, _B, _EID, _hadouken_event, _setup_mtgtop8_event

    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    hado.apply_import(session, _EID, _hadouken_event(), {_A: ids[_A], "Hadotest Zqxb": ids[_B]})
    session.flush()
    assert len(_deck_ids(session, _EID)) == 4  # two blank decks were created

    (row,) = _snapshots(session, _EID, "hadouken")
    snap.restore_snapshot(session, row.id)
    session.expire_all()
    assert _deck_ids(session, _EID) == set(ids.values())
    assert db.list_matchups_by_decks(session, list(ids.values())) == []


def test_rejected_hadouken_import_leaves_no_snapshot(db_session_rollback):
    from api.services import hadouken as hado
    from tests.test_hadouken_import import _A, _EID, _hadouken_event, _setup_mtgtop8_event

    session = db_session_rollback
    ids = _setup_mtgtop8_event(session)
    with pytest.raises(ValueError):
        hado.apply_import(session, _EID, _hadouken_event(), {"Nobody On The Page": ids[_A]})
    assert _snapshots(session, _EID, "hadouken") == []


# ---- clear decks ---------------------------------------------------------------------------------


def test_clear_decks_snapshots_every_event_once(in_session):
    from api import state as state_module

    session = in_session
    events = [f"snap_clear_{i}" for i in range(30)]
    for i, event_id in enumerate(events):
        seed(
            session,
            event_id=event_id,
            deck_a=987100 + 2 * i,
            deck_b=987101 + 2 * i,
            players=(f"Clear A{i}", f"Clear B{i}"),
        )

    state_module._clear_decks_in_db()

    assert session.query(db.DeckRow).filter(db.DeckRow.event_id.in_(events)).count() == 0
    for event_id in events:
        assert len(_snapshots(session, event_id, "clear_decks")) == 1
    snap.restore_snapshot(session, _snapshots(session, events[7], "clear_decks")[0].id)
    assert _deck_ids(session, events[7]) == {987114, 987115}


# ---- re-scrape -----------------------------------------------------------------------------------


def _scraped(deck_id, event_id, player, **extra):
    d = _deck(deck_id, event_id, player, **extra)
    d["event_id"] = event_id
    return d


def test_rescraping_an_existing_event_snapshots_it_first(db_session_rollback):
    from api.services.scrape_store import persist_scraped_decks

    session = db_session_rollback
    seed(session)
    persist_scraped_decks(
        session,
        [_scraped(DECK_A, EID, "Snap Alice", rank="5"), _scraped(DECK_B, EID, "Snap Bob")],
        refresh_events=True,
    )
    session.flush()
    assert session.get(db.DeckRow, DECK_A).rank == "5"

    (row,) = _snapshots(session, EID, "rescrape")
    assert next(d for d in row.payload["decks"] if d["deck_id"] == DECK_A)["rank"] == "1"


def test_scraping_a_new_event_takes_no_snapshot(db_session_rollback):
    from api.services.scrape_store import persist_scraped_decks

    session = db_session_rollback
    persist_scraped_decks(
        session,
        [_scraped(987201, "snap_new_ev", "Snap New One"), _scraped(987202, "snap_new_ev", "Snap New Two")],
        refresh_events=False,
    )
    session.flush()
    assert session.query(EventSnapshotRow).filter(EventSnapshotRow.event_id == "snap_new_ev").count() == 0


def test_repeating_the_same_rescrape_adds_no_more_snapshots(db_session_rollback):
    from api.services.scrape_store import persist_scraped_decks

    session = db_session_rollback
    seed(session)
    scraped = [_scraped(DECK_A, EID, "Snap Alice", rank="5"), _scraped(DECK_B, EID, "Snap Bob")]
    for _ in range(4):
        persist_scraped_decks(session, [dict(d) for d in scraped], refresh_events=True)
        session.flush()
    # one before the first change, one of the changed state before the second run; then nothing new
    assert len(_snapshots(session, EID, "rescrape")) == 2
