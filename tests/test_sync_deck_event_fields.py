from api.db import DeckRow, create_event, sync_decks_with_event, upsert_deck
from scripts.sync_deck_event_fields import format_changes


def test_changes_are_reported_for_a_drifted_deck(db_session_rollback):
    session = db_session_rollback
    create_event(session, "Sync Rep", "01/01/25", "EDH", origin="mtgtop8", event_id="9900100", player_count=32)
    upsert_deck(
        session,
        {
            "deck_id": 9900101, "event_id": 9900100, "format_id": "EDH", "name": "D", "player": "Sync P",
            "event_name": "Old Name", "date": "01/01/25", "rank": "1", "player_count": 8,
            "mainboard": [], "sideboard": [], "commanders": [], "archetype": "A",
        },
    )
    session.flush()
    changes: list = []
    assert sync_decks_with_event(session, "9900100", changes) == 1
    assert (9900101, "event_name", "Old Name", "Sync Rep") in changes
    assert (9900101, "player_count", 8, 32) in changes
    assert session.query(DeckRow).filter(DeckRow.deck_id == 9900101).one().player_count == 32
    lines = format_changes(changes, limit=1)
    assert len(lines) == 2 and lines[1] == "... and 1 more"
