from datetime import datetime, timedelta, timezone

from api.db import create_event, create_upload_link


def test_link_without_expiry_gets_seven_days(db_session_rollback):
    session = db_session_rollback
    create_event(session, "Links", "01/01/25", "EDH", event_id="test_links_1", player_count=1)
    row = create_upload_link(session, "tok-default-expiry", "test_links_1")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert row.expires_at.tzinfo is None
    assert timedelta(days=7) - timedelta(minutes=1) < row.expires_at - now <= timedelta(days=7)


def test_explicit_expiry_is_kept(db_session_rollback):
    session = db_session_rollback
    create_event(session, "Links", "01/01/25", "EDH", event_id="test_links_2", player_count=1)
    when = datetime(2030, 1, 1)
    assert create_upload_link(session, "tok-explicit", "test_links_2", expires_at=when).expires_at == when


def test_iso_utc_marks_naive_utc_datetimes_with_z():
    from api.db import iso_utc

    assert iso_utc(datetime(2030, 1, 2, 3, 4, 5)) == "2030-01-02T03:04:05Z"
    assert iso_utc(None) is None


def test_admin_link_listing_timestamps_are_utc_with_z(db_session_rollback):
    from api.db import get_all_upload_links

    session = db_session_rollback
    create_event(session, "Links", "01/01/25", "EDH", event_id="test_links_3", player_count=1)
    create_upload_link(session, "tok-z-suffix", "test_links_3")
    session.flush()
    row = next(r for r in get_all_upload_links(session) if r["token"] == "tok-z-suffix")
    assert row["expires_at"].endswith("Z")
    assert row["created_at"].endswith("Z")


# ---- event-edit links close 12 hours after first open ---------------------------------------


def _event_edit_link(session, event_id, token, **kwargs):
    from api import db

    create_event(session, "Links", "01/01/25", "EDH", event_id=event_id, player_count=1)
    row = create_upload_link(session, token, event_id, link_type=db.LINK_TYPE_EVENT_EDIT, **kwargs)
    session.flush()  # the test session does not autoflush
    return row


def test_sitting_window_shortens_a_seven_day_link(db_session_rollback):
    from api import db

    session = db_session_rollback
    row = _event_edit_link(session, "test_links_sit_1", "tok-sit-1")
    assert db.mark_upload_link_used(session, "tok-sit-1", sitting_hours=12) is True
    remaining = row.expires_at - db.utcnow_naive()
    assert timedelta(hours=11, minutes=59) < remaining <= timedelta(hours=12)
    assert row.used_at is not None


def test_sitting_window_never_extends_a_shorter_link(db_session_rollback):
    from api import db

    session = db_session_rollback
    soon = db.utcnow_naive() + timedelta(hours=1)
    row = _event_edit_link(session, "test_links_sit_2", "tok-sit-2", expires_at=soon)
    db.mark_upload_link_used(session, "tok-sit-2", sitting_hours=12)
    assert row.expires_at == soon


def test_sitting_window_applies_to_a_link_without_expiry(db_session_rollback):
    from api import db

    session = db_session_rollback
    row = _event_edit_link(session, "test_links_sit_3", "tok-sit-3")
    row.expires_at = None  # legacy rows created before links had a default expiry
    db.mark_upload_link_used(session, "tok-sit-3", sitting_hours=12)
    assert row.expires_at is not None
    assert row.expires_at - db.utcnow_naive() <= timedelta(hours=12)


def test_mark_used_without_sitting_hours_leaves_expiry_alone(db_session_rollback):
    from api import db

    session = db_session_rollback
    row = _event_edit_link(session, "test_links_sit_4", "tok-sit-4")
    before = row.expires_at
    db.mark_upload_link_used(session, "tok-sit-4")
    assert row.expires_at == before


def _use_session(monkeypatch, session):
    """Make the upload router and the auth dependencies run inside the rolled-back test session."""
    from contextlib import contextmanager

    from api import db

    @contextmanager
    def scope():
        yield session
        session.flush()

    monkeypatch.setattr(db, "session_scope", scope)


def test_opening_an_event_edit_link_starts_the_sitting_window(db_session_rollback, monkeypatch):
    from api import db
    from api.routers.upload import get_event_edit_link_info

    session = db_session_rollback
    row = _event_edit_link(session, "test_links_sit_5", "tok-sit-5")
    _use_session(monkeypatch, session)
    assert get_event_edit_link_info("tok-sit-5") == {"event_id": "test_links_sit_5"}
    assert row.expires_at - db.utcnow_naive() <= timedelta(hours=db.EVENT_EDIT_SITTING_HOURS)


def test_event_edit_token_still_works_after_link_is_opened(db_session_rollback, monkeypatch):
    from api.dependencies import require_admin_or_event_edit
    from api.routers.upload import get_event_edit_link_info

    session = db_session_rollback
    _event_edit_link(session, "test_links_sit_6", "tok-sit-6")
    _use_session(monkeypatch, session)
    get_event_edit_link_info("tok-sit-6")
    assert require_admin_or_event_edit("test_links_sit_6", None, "tok-sit-6") == "event_edit"


def test_event_edit_token_rejected_once_sitting_window_has_passed(db_session_rollback, monkeypatch):
    import pytest
    from fastapi import HTTPException

    from api import db
    from api.dependencies import require_admin_or_event_edit
    from api.routers.upload import get_event_edit_link_info

    session = db_session_rollback
    row = _event_edit_link(session, "test_links_sit_7", "tok-sit-7")
    _use_session(monkeypatch, session)
    get_event_edit_link_info("tok-sit-7")
    row.expires_at = db.utcnow_naive() - timedelta(minutes=1)
    with pytest.raises(HTTPException) as exc:
        require_admin_or_event_edit("test_links_sit_7", None, "tok-sit-7")
    assert exc.value.status_code == 401
    assert exc.value.detail == "Event edit link expired"
