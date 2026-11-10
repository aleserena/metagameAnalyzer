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
