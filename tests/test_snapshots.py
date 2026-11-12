"""Event snapshots: take, dedupe, prune, list (api/services/snapshots.py)."""

from datetime import timedelta

from api import db
from api.db import EventSnapshotRow
from api.services import snapshots as snap

EID = "snap_ev_1"
DECK_A, DECK_B = 987001, 987002


def _deck(deck_id, event_id, player, **extra):
    return {
        "deck_id": deck_id,
        "event_id": event_id,
        "format_id": "EDH",
        "name": f"Deck of {player}",
        "player": player,
        "event_name": "Snap Event",
        "date": "01/01/25",
        "rank": "1",
        "player_count": 2,
        "commanders": ["Atraxa, Praetors' Voice"],
        "archetype": None,
        "mainboard": [{"qty": 1, "card": "Sol Ring"}],
        "sideboard": [],
        **extra,
    }


def seed(session, event_id=EID, deck_a=DECK_A, deck_b=DECK_B, players=("Snap Alice", "Snap Bob")):
    """An mtgtop8 event with two decks, one match (both sides stored) and one player email."""
    db.create_event(
        session, "Snap Event", "01/01/25", "EDH", event_id=event_id, player_count=2, origin=db.ORIGIN_MTGTOP8
    )
    db.upsert_deck(session, _deck(deck_a, event_id, players[0]))
    db.upsert_deck(session, _deck(deck_b, event_id, players[1]))
    session.flush()
    db.upsert_matchups_for_deck(
        session,
        deck_a,
        [
            {
                "opponent_player": players[1],
                "opponent_deck_id": deck_b,
                "opponent_archetype": None,
                "result": "win",
                "result_note": "2-0",
                "round": 1,
            }
        ],
    )
    db.set_player_email(session, players[0], "snap.alice@example.com")
    session.flush()


def _rows(session, event_id=EID):
    return (
        session.query(EventSnapshotRow)
        .filter(EventSnapshotRow.event_id == event_id)
        .order_by(EventSnapshotRow.id)
        .all()
    )


def test_snapshot_holds_decks_matchups_and_emails(db_session_rollback):
    session = db_session_rollback
    seed(session)
    sid = snap.take_snapshot(session, EID, "delete")
    row = session.get(EventSnapshotRow, sid)
    assert row.reason == "delete"
    assert row.event_id == EID and row.event_name == "Snap Event"
    assert {d["deck_id"] for d in row.payload["decks"]} == {DECK_A, DECK_B}
    assert len(row.payload["matchups"]) == 2  # both sides of the one match
    assert row.payload["player_emails"] == {"Snap Alice": "snap.alice@example.com"}
    assert row.payload["event"]["origin"] == db.ORIGIN_MTGTOP8
    assert row.payload["extras"]["deck_origins"] == {str(DECK_A): db.ORIGIN_MTGTOP8, str(DECK_B): db.ORIGIN_MTGTOP8}


def test_snapshot_records_hand_edited_fields(db_session_rollback):
    session = db_session_rollback
    seed(session)
    session.get(db.DeckRow, DECK_A).manual_fields = ["player"]
    db.get_event(session, EID).manual_fields = ["name"]
    session.flush()
    row = session.get(EventSnapshotRow, snap.take_snapshot(session, EID, "rescrape"))
    assert row.payload["extras"]["deck_manual_fields"] == {str(DECK_A): ["player"]}
    assert row.payload["extras"]["event_manual_fields"] == ["name"]


def test_snapshot_of_missing_event_returns_none(db_session_rollback):
    assert snap.take_snapshot(db_session_rollback, "no_such_event", "delete") is None
    assert _rows(db_session_rollback, "no_such_event") == []


def test_identical_snapshot_is_not_stored_twice(db_session_rollback):
    session = db_session_rollback
    seed(session)
    first = snap.take_snapshot(session, EID, "rescrape")
    assert snap.take_snapshot(session, EID, "rescrape") == first
    assert len(_rows(session)) == 1


def test_a_changed_event_gets_a_new_snapshot(db_session_rollback):
    session = db_session_rollback
    seed(session)
    first = snap.take_snapshot(session, EID, "rescrape")
    session.get(db.DeckRow, DECK_A).rank = "2"
    session.flush()
    assert snap.take_snapshot(session, EID, "rescrape") != first
    assert len(_rows(session)) == 2


def test_only_the_newest_ten_are_kept(db_session_rollback):
    session = db_session_rollback
    seed(session)
    ids = []
    for i in range(12):
        session.get(db.DeckRow, DECK_A).rank = str(i + 10)
        session.flush()
        ids.append(snap.take_snapshot(session, EID, "rescrape"))
    kept = [r.id for r in _rows(session)]
    assert snap.SNAPSHOT_KEEP_PER_EVENT == 10
    assert kept == ids[-10:]


def test_snapshots_older_than_ninety_days_are_dropped(db_session_rollback):
    session = db_session_rollback
    seed(session)
    old = snap.take_snapshot(session, EID, "delete")
    session.get(EventSnapshotRow, old).created_at = db.utcnow_naive() - timedelta(days=snap.SNAPSHOT_MAX_AGE_DAYS + 1)
    session.get(db.DeckRow, DECK_A).rank = "9"
    session.flush()
    new = snap.take_snapshot(session, EID, "delete")
    assert [r.id for r in _rows(session)] == [new]


def test_pruning_one_event_leaves_other_events_alone(db_session_rollback):
    session = db_session_rollback
    seed(session)
    seed(session, event_id="snap_ev_2", deck_a=987003, deck_b=987004, players=("Snap Carol", "Snap Dave"))
    other = snap.take_snapshot(session, "snap_ev_2", "delete")
    session.get(EventSnapshotRow, other).created_at = db.utcnow_naive() - timedelta(days=30)
    for i in range(11):
        session.get(db.DeckRow, DECK_A).rank = str(i + 10)
        session.flush()
        snap.take_snapshot(session, EID, "rescrape")
    assert [r.id for r in _rows(session, "snap_ev_2")] == [other]


def test_listing_is_newest_first_and_never_returns_the_payload(db_session_rollback):
    session = db_session_rollback
    seed(session)
    first = snap.take_snapshot(session, EID, "delete")
    session.get(db.DeckRow, DECK_A).rank = "7"
    session.flush()
    second = snap.take_snapshot(session, EID, "merge")
    listed = [s for s in snap.list_snapshots(session, event_id=EID)]
    assert [s["id"] for s in listed] == [second, first]
    assert listed[0] == {
        "id": second,
        "event_id": EID,
        "event_name": "Snap Event",
        "created_at": listed[0]["created_at"],
        "reason": "merge",
        "deck_count": 2,
        "matchup_count": 2,
    }
    assert listed[0]["created_at"].endswith("Z")
    assert "snap.alice@example.com" not in str(listed)
