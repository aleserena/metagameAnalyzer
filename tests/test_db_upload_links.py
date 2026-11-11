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
