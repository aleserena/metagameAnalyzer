"""Event structure (Swiss / single elimination) through the create, edit, merge, import and restore paths."""

from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from api import db
from api.db import event_row_to_dict, get_event


@pytest.fixture
def in_session(db_session_rollback, monkeypatch):
    """Run handlers inside the rolled-back test session."""
    session = db_session_rollback

    @contextmanager
    def scope():
        yield session
        session.flush()

    monkeypatch.setattr(db, "session_scope", scope)
    from api.routers import events as events_router

    monkeypatch.setattr(events_router, "_load_decks_from_db", lambda: None)
    monkeypatch.setattr(events_router, "_invalidate_events_cache", lambda: None)
    return session


def _structure(session, event_id):
    session.expire_all()
    d = event_row_to_dict(get_event(session, event_id))
    return d["structure"], d["bracket_size"]


def _update(event_id, **kw):
    """Call the PUT handler directly: every query param must be passed (defaults are Query objects)."""
    from api.routers.events import update_event_endpoint

    params = dict(event_name=None, date=None, format_id=None, player_count=None, store=None, location=None,
                  structure=None, bracket_size=None)
    params.update(kw)
    return update_event_endpoint(event_id, actor="admin", **params)


def _create(session, event_id, **kw):
    db.create_event(session, "Ev", "01/01/25", "EDH", event_id=event_id, player_count=16, **kw)
    session.flush()


def test_create_event_single_elim(in_session):
    from api.routers.events import create_event
    from api.schemas.events import CreateEventBody

    created = create_event(CreateEventBody(event_name="SE", date="01/01/25", player_count=44,
                                           structure="single_elimination", bracket_size=16))
    assert (created.structure, created.bracket_size) == ("single_elimination", 16)
    assert _structure(in_session, str(created.event_id)) == ("single_elimination", 16)


def test_create_event_single_elim_without_size_422(in_session):
    from api.routers.events import create_event
    from api.schemas.events import CreateEventBody

    with pytest.raises(HTTPException) as exc:
        create_event(CreateEventBody(event_name="SE", date="01/01/25", player_count=44, structure="single_elimination"))
    assert exc.value.status_code == 422


def test_update_event_structure_query_params(in_session):
    _create(in_session, "test_es_upd")
    _update("test_es_upd", structure="single_elimination", bracket_size=8)
    assert _structure(in_session, "test_es_upd") == ("single_elimination", 8)
    _update("test_es_upd", bracket_size=16)  # size only: keeps the stored structure
    assert _structure(in_session, "test_es_upd") == ("single_elimination", 16)
    with pytest.raises(HTTPException) as exc:
        _update("test_es_upd", bracket_size=12)
    assert exc.value.status_code == 422
    assert _structure(in_session, "test_es_upd") == ("single_elimination", 16)


def test_update_event_back_to_swiss_clears_bracket_size(in_session):
    _create(in_session, "test_es_back", structure="single_elimination", bracket_size=16)
    _update("test_es_back", structure="swiss")
    assert _structure(in_session, "test_es_back") == ("swiss", None)
    assert get_event(in_session, "test_es_back").bracket_size is None


def test_update_event_without_structure_leaves_it(in_session):
    _create(in_session, "test_es_keep", structure="single_elimination", bracket_size=16)
    _update("test_es_keep", event_name="Renamed")
    assert _structure(in_session, "test_es_keep") == ("single_elimination", 16)


def test_merge_keeps_single_elimination(in_session):
    from api.routers.events import merge_events
    from api.schemas.events import MergeEventsBody

    db.create_event(in_session, "Keep", "01/01/25", "EDH", origin=db.ORIGIN_MANUAL, event_id="test_es_mk", player_count=16)
    db.create_event(in_session, "Remove", "01/01/25", "EDH", origin=db.ORIGIN_MANUAL, event_id="test_es_mr",
                    player_count=16, structure="single_elimination", bracket_size=16)
    in_session.flush()
    merge_events(MergeEventsBody(event_id_keep="test_es_mk", event_id_remove="test_es_mr"))
    assert _structure(in_session, "test_es_mk") == ("single_elimination", 16)


def test_merge_preview_shows_structure(in_session):
    from api.routers.events import merge_preview

    db.create_event(in_session, "A", "01/01/25", "EDH", origin=db.ORIGIN_MANUAL, event_id="test_es_pa", player_count=16,
                    structure="single_elimination", bracket_size=8)
    db.create_event(in_session, "B", "01/01/25", "EDH", origin=db.ORIGIN_MANUAL, event_id="test_es_pb", player_count=16)
    in_session.flush()
    preview = merge_preview(event_id_a="test_es_pa", event_id_b="test_es_pb", manual_pairs=None)
    assert (preview.merged_preview["structure"], preview.merged_preview["bracket_size"]) == ("single_elimination", 8)


def test_export_import_round_trips_structure(in_session):
    from api.services.event_export import build_event_export
    from api.services.event_import import import_event_payload

    _create(in_session, "test_es_exp", structure="single_elimination", bracket_size=16)
    export = build_event_export(in_session, "test_es_exp", include_emails=False)
    assert (export.event.structure, export.event.bracket_size) == ("single_elimination", 16)
    result = import_event_payload(in_session, export)
    in_session.flush()
    assert _structure(in_session, result["event_id"]) == ("single_elimination", 16)


def test_import_old_payload_without_structure_is_swiss(in_session):
    from api.schemas.events import EventExportData
    from api.services.event_import import import_event_payload

    data = EventExportData.model_validate({"event": {"event_id": "x", "event_name": "Old", "date": "01/01/25",
                                                     "format_id": "EDH", "player_count": 8}})
    result = import_event_payload(in_session, data)
    in_session.flush()
    assert _structure(in_session, result["event_id"]) == ("swiss", None)


def test_snapshot_restore_round_trips_structure(in_session):
    from api.services.snapshots import restore_snapshot, take_snapshot

    _create(in_session, "test_es_snap", structure="single_elimination", bracket_size=16)
    snap_id = take_snapshot(in_session, "test_es_snap", "test")
    _update("test_es_snap", structure="swiss")
    restore_snapshot(in_session, snap_id)
    in_session.flush()
    assert _structure(in_session, "test_es_snap") == ("single_elimination", 16)


def test_snapshot_restore_old_payload_is_swiss(in_session):
    from api.db import EventSnapshotRow
    from api.services.snapshots import restore_snapshot, take_snapshot

    _create(in_session, "test_es_snap_old", structure="single_elimination", bracket_size=16)
    snap_id = take_snapshot(in_session, "test_es_snap_old", "test")
    snap = in_session.get(EventSnapshotRow, snap_id)
    payload = dict(snap.payload)
    payload["event"] = {k: v for k, v in payload["event"].items() if k not in ("structure", "bracket_size")}
    snap.payload = payload
    in_session.flush()
    restore_snapshot(in_session, snap_id)
    in_session.flush()
    assert _structure(in_session, "test_es_snap_old") == ("swiss", None)


def test_saving_matchups_keeps_the_round_of_a_bye(in_session, monkeypatch):
    """A first-round bye in a bracket must keep its round, or the editor can't put it back in its slot."""
    from api.db import DeckRow, MatchupRow
    from api.routers import decks as decks_router
    from api.schemas.matchups import AdminMatchupsBody, MatchupItem

    _create(in_session, "test_es_bye", structure="single_elimination", bracket_size=8)
    db.upsert_deck(in_session, {
        "deck_id": 989950, "event_id": "test_es_bye", "format_id": "EDH", "name": "D", "player": "Bye Taker",
        "event_name": "Ev", "date": "01/01/25", "rank": "5-8", "player_count": 16,
        "mainboard": [], "sideboard": [], "commanders": [], "archetype": None,
    }, origin="manual")
    in_session.flush()
    monkeypatch.setattr(decks_router, "_get_deck_by_id",
                        lambda deck_id: db.deck_row_to_dict(in_session.get(DeckRow, deck_id)))
    monkeypatch.setattr(decks_router, "_load_decks_from_db", lambda: None)
    decks_router.update_deck_matchups(
        989950, AdminMatchupsBody(matchups=[MatchupItem(opponent_player="", result="bye", round=1)]), actor="admin"
    )
    in_session.expire_all()
    rows = in_session.query(MatchupRow).filter(MatchupRow.deck_id == 989950).all()
    assert [(r.opponent_player, r.result, r.round) for r in rows] == [("Bye", "bye", 1)]
