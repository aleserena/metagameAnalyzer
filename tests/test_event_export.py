from api.db import create_event, set_player_email, upsert_deck
from api.services.event_export import build_event_export

EID = "test_export_1"


def _seed(session):
    create_event(session, "Export", "01/01/25", "EDH", event_id=EID, player_count=1)
    upsert_deck(
        session,
        {
            "deck_id": 986001,
            "event_id": EID,
            "format_id": "EDH",
            "name": "D",
            "player": "Export Player",
            "event_name": "Export",
            "date": "01/01/25",
            "rank": "",
            "player_count": 1,
            "mainboard": [],
            "sideboard": [],
            "commanders": [],
            "archetype": None,
        },
    )
    session.flush()
    set_player_email(session, "Export Player", "export.player@example.com")
    session.flush()


def test_export_with_emails(db_session_rollback):
    _seed(db_session_rollback)
    out = build_event_export(db_session_rollback, EID, include_emails=True)
    assert out.player_emails == {"Export Player": "export.player@example.com"}


def test_export_without_emails(db_session_rollback):
    _seed(db_session_rollback)
    out = build_event_export(db_session_rollback, EID, include_emails=False)
    assert out.player_emails == {}
    assert len(out.decks) == 1


def test_export_unknown_event(db_session_rollback):
    assert build_event_export(db_session_rollback, "does-not-exist", include_emails=True) is None
