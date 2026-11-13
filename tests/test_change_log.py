"""Change log: what changed, when, and through which door (api/services/change_log.py)."""

from contextlib import contextmanager
from datetime import timedelta

import pytest

from api import db
from api.db import ChangeLogRow
from api.services import change_log as cl


@pytest.fixture
def in_session(db_session_rollback, monkeypatch):
    session = db_session_rollback

    @contextmanager
    def scope():
        yield session
        session.flush()

    monkeypatch.setattr(db, "session_scope", scope)
    monkeypatch.setattr(cl, "_last_prune", None)
    return session


def _rows(session, action=None):
    q = session.query(ChangeLogRow)
    if action:
        q = q.filter(ChangeLogRow.action == action)
    return q.order_by(ChangeLogRow.id).all()


def test_record_and_list_newest_first(db_session_rollback):
    session = db_session_rollback
    cl.record(session, actor=cl.ADMIN, action="event.create", summary="first", event_id="cl_ev_1")
    cl.record(session, actor=cl.ADMIN, action="deck.update", summary="second", event_id="cl_ev_1", deck_id=7)
    listed = cl.list_changes(session, event_id="cl_ev_1")
    assert [c["summary"] for c in listed] == ["second", "first"]
    assert listed[0] == {
        "id": listed[0]["id"],
        "at": listed[0]["at"],
        "actor": "admin",
        "action": "deck.update",
        "event_id": "cl_ev_1",
        "deck_id": 7,
        "summary": "second",
    }
    assert listed[0]["at"].endswith("Z")


def test_listing_filters_by_event_and_limits(db_session_rollback):
    session = db_session_rollback
    for i in range(5):
        cl.record(session, actor=cl.ADMIN, action="deck.update", summary=str(i), event_id="cl_ev_a")
    cl.record(session, actor=cl.ADMIN, action="deck.update", summary="other", event_id="cl_ev_b")
    assert [c["summary"] for c in cl.list_changes(session, event_id="cl_ev_a", limit=2)] == ["4", "3"]
    assert [c["summary"] for c in cl.list_changes(session, event_id="cl_ev_b")] == ["other"]


def test_summary_is_truncated_to_512_characters(db_session_rollback):
    session = db_session_rollback
    cl.record(session, actor=cl.ADMIN, action="deck.update", summary="x" * 2000, event_id="cl_ev_2")
    assert len(_rows(session, "deck.update")[-1].summary) == 512


def test_link_actor_names_type_and_label_not_the_token(db_session_rollback):
    session = db_session_rollback
    db.create_event(session, "CL", "01/01/25", "EDH", event_id="cl_ev_3", player_count=1)
    row = db.create_upload_link(
        session, "tok-change-log-secret", "cl_ev_3", label="Store organiser", link_type=db.LINK_TYPE_EVENT_EDIT
    )
    unlabelled = db.create_upload_link(session, "tok-change-log-secret-2", "cl_ev_3")
    assert cl.link_actor(row) == "link:event_edit:Store organiser"
    assert cl.link_actor(unlabelled) == "link:deck_upload:unlabelled"
    assert "tok-change-log" not in cl.link_actor(row) + cl.link_actor(unlabelled)


def test_actor_for_token_resolves_a_link_and_never_echoes_an_unknown_token(in_session):
    session = in_session
    db.create_event(session, "CL", "01/01/25", "EDH", event_id="cl_ev_4", player_count=1)
    db.create_upload_link(session, "tok-cl-4", "cl_ev_4", label="Ana", link_type=db.LINK_TYPE_EVENT_EDIT)
    session.flush()
    assert cl.actor_for_token("tok-cl-4") == "link:event_edit:Ana"
    assert cl.actor_for_token("some-made-up-token") == "link:unknown"
    assert cl.actor_for_token(None) == "unknown"


def test_rows_older_than_180_days_are_dropped(db_session_rollback, monkeypatch):
    session = db_session_rollback
    monkeypatch.setattr(cl, "_last_prune", None)
    old = ChangeLogRow(
        at=db.utcnow_naive() - timedelta(days=cl.CHANGE_LOG_MAX_AGE_DAYS + 1),
        actor="admin",
        action="deck.update",
        event_id="cl_ev_5",
        summary="ancient",
    )
    session.add(old)
    session.flush()
    cl.record(session, actor=cl.ADMIN, action="deck.update", summary="new", event_id="cl_ev_5")
    assert [c["summary"] for c in cl.list_changes(session, event_id="cl_ev_5")] == ["new"]
    assert cl.CHANGE_LOG_MAX_AGE_DAYS == 180


def test_log_writes_in_its_own_transaction(in_session):
    cl.log(cl.ADMIN, "settings.update", "rank weights changed")
    assert _rows(in_session, "settings.update")[-1].summary == "rank weights changed"


def test_a_failing_log_write_never_breaks_the_caller(monkeypatch, caplog):
    def boom():
        raise RuntimeError("database is down")

    monkeypatch.setattr(db, "session_scope", boom)
    cl.log(cl.ADMIN, "deck.update", "x")  # must not raise
    assert "Could not write change log" in caplog.text


# ---- handlers record what they did ------------------------------------------------------------


@pytest.fixture
def quiet_reload(monkeypatch):
    """Handlers reload the in-memory deck list after a change; not needed here."""
    from api.routers import events as events_router
    from api.routers import upload as upload_router

    for module in (events_router, upload_router):
        monkeypatch.setattr(module, "_load_decks_from_db", lambda: None)
    monkeypatch.setattr(events_router, "_invalidate_events_cache", lambda: None)


def test_public_upload_is_logged_with_the_link_as_actor(in_session, quiet_reload):
    from api.routers.upload import submit_deck_with_upload_link
    from api.schemas.decks import SubmitDeckBody

    session = in_session
    db.create_event(session, "CL upload", "01/01/25", "EDH", event_id="cl_ev_up", player_count=4)
    db.create_upload_link(session, "tok-cl-upload-secret", "cl_ev_up", label="Table 3")
    session.flush()

    submit_deck_with_upload_link(
        "tok-cl-upload-secret",
        SubmitDeckBody(name="My deck", player="Cl Uploader", mainboard=[{"qty": 1, "card": "Sol Ring"}]),
    )

    (row,) = _rows(session, "upload.deck")
    assert row.actor == "link:deck_upload:Table 3"
    assert row.event_id == "cl_ev_up" and row.deck_id is not None
    assert "Cl Uploader" in row.summary
    assert "tok-cl-upload-secret" not in row.actor + row.summary


def test_admin_event_delete_is_logged(in_session, quiet_reload):
    from api.routers.events import delete_event_endpoint

    session = in_session
    db.create_event(session, "CL delete", "01/01/25", "EDH", event_id="cl_ev_del", player_count=1)
    session.flush()
    delete_event_endpoint("cl_ev_del")
    (row,) = _rows(session, "event.delete")
    assert (row.actor, row.event_id) == ("admin", "cl_ev_del")


def test_a_failed_mutation_logs_nothing(in_session, quiet_reload):
    from fastapi import HTTPException

    from api.routers.events import delete_event_endpoint

    with pytest.raises(HTTPException) as exc:
        delete_event_endpoint("cl_ev_does_not_exist")
    assert exc.value.status_code == 404
    assert _rows(in_session, "event.delete") == []


def test_player_email_change_does_not_log_the_address(in_session):
    from api.routers.players import put_player_email
    from api.schemas.players import PlayerEmailBody

    session = in_session
    db.get_or_create_player(session, "Cl Email Player")
    session.flush()
    put_player_email(PlayerEmailBody(player="Cl Email Player", email="private.address@example.com"))
    put_player_email(PlayerEmailBody(player="Cl Email Player", email=""))
    rows = _rows(session, "player.email")
    assert [r.summary for r in rows] == ["Email set for Cl Email Player", "Email removed for Cl Email Player"]
    assert "private.address" not in " ".join(r.summary for r in session.query(ChangeLogRow))


def test_current_actor_is_admin_for_an_admin_token_and_the_link_otherwise(in_session, monkeypatch):
    from api import dependencies as deps

    session = in_session
    db.create_event(session, "CL actor", "01/01/25", "EDH", event_id="cl_ev_actor", player_count=1)
    db.create_upload_link(session, "tok-cl-actor", "cl_ev_actor", label="Luis", link_type=db.LINK_TYPE_EVENT_EDIT)
    session.flush()
    monkeypatch.setattr(deps, "ADMIN_PASSWORD", "test-admin-password")
    assert deps.current_actor(f"Bearer {deps._create_admin_token()}", None) == "admin"
    assert deps.current_actor(None, "tok-cl-actor") == "link:event_edit:Luis"
    assert deps.current_actor("Bearer not-a-real-token", None) == "unknown"


# ---- Settings routes: snapshots and change log --------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/v1/settings/snapshots"),
        ("post", "/api/v1/settings/snapshots/1/restore"),
        ("get", "/api/v1/settings/change-log"),
    ],
)
def test_recovery_routes_require_admin(method, path):
    from fastapi.testclient import TestClient

    from api.main import app

    assert getattr(TestClient(app), method)(path).status_code == 401


def test_snapshot_listing_route_never_returns_the_payload(in_session):
    from api.routers.settings import get_settings_snapshots
    from api.services import snapshots as snap
    from tests.test_snapshots import EID, seed

    seed(in_session)
    sid = snap.take_snapshot(in_session, EID, "delete")
    out = get_settings_snapshots(event_id=EID, search=None, limit=50)
    assert [s["id"] for s in out["snapshots"]] == [sid]
    assert "payload" not in out["snapshots"][0]
    assert "snap.alice@example.com" not in str(out)


def test_restore_route_restores_reloads_and_logs(in_session, monkeypatch):
    from api.routers import settings as settings_router
    from api.services import snapshots as snap
    from tests.test_snapshots import DECK_A, DECK_B, EID, seed

    session = in_session
    reloads = []
    monkeypatch.setattr(settings_router, "_load_decks_from_db", lambda: reloads.append("decks"))
    seed(session)
    sid = snap.take_snapshot(session, EID, "delete")
    db.delete_event(session, EID, delete_decks=True)
    session.flush()

    out = settings_router.post_restore_snapshot(sid)

    assert out["event_id"] == EID and out["deck_count"] == 2
    assert {d["deck_id"] for d in db.get_decks_by_event(session, EID)} == {DECK_A, DECK_B}
    assert reloads == ["decks"]
    (row,) = _rows(session, "event.restore")
    assert (row.actor, row.event_id) == ("admin", EID)


def test_restore_route_returns_404_for_an_unknown_snapshot(in_session):
    from fastapi import HTTPException

    from api.routers.settings import post_restore_snapshot

    with pytest.raises(HTTPException) as exc:
        post_restore_snapshot(999_999_999)
    assert exc.value.status_code == 404
    assert _rows(in_session, "event.restore") == []


def test_change_log_route_lists_newest_first(in_session):
    from api.routers.settings import get_settings_change_log

    cl.record(in_session, actor=cl.ADMIN, action="deck.update", summary="one", event_id="cl_route_ev")
    cl.record(in_session, actor=cl.ADMIN, action="deck.update", summary="two", event_id="cl_route_ev")
    out = get_settings_change_log(event_id="cl_route_ev", limit=50)
    assert [c["summary"] for c in out["changes"]] == ["two", "one"]


def test_snapshot_listing_route_searches_by_event_name(in_session):
    from api.routers.settings import get_settings_snapshots
    from api.services import snapshots as snap
    from tests.test_snapshots import EID, seed

    seed(in_session)
    sid = snap.take_snapshot(in_session, EID, "delete")
    assert [s["id"] for s in get_settings_snapshots(event_id=None, search="snap ev", limit=50)["snapshots"]] == [sid]
    assert get_settings_snapshots(event_id=None, search="no such event name", limit=50)["snapshots"] == []
