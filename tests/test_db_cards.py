"""DB tests for card lookup by name, including front-face fallback for double-faced cards."""

from api.db import get_cards_by_name, upsert_cards
from api.services.mtgjson import atomic_card_to_row


def _row(name):
    row = atomic_card_to_row(name, [{"name": name}])
    row.update(scryfall_id=None, mtgjson_uuid=None)
    return row


def test_front_face_and_exact_lookup(db_session_rollback):
    session = db_session_rollback
    upsert_cards(
        session,
        [
            _row("Zz Test Osborn // Zz Test Goblin"),
            _row("Zz Test Ring"),
            _row("Zz Test Fire // Zz Test Ice"),
            _row("Zz Test Fire"),
        ],
    )
    session.flush()
    found = get_cards_by_name(session, ["Zz Test Osborn", "Zz Test Ring", "Zz Test Fire", "Zz Test Missing"])
    assert set(found) == {"Zz Test Osborn", "Zz Test Ring", "Zz Test Fire"}
    assert found["Zz Test Osborn"].name == "Zz Test Osborn // Zz Test Goblin"
    assert found["Zz Test Fire"].name == "Zz Test Fire"
