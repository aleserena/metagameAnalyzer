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


# ---- restore -----------------------------------------------------------------------------------


def _decks(session, event_id=EID):
    return {d["deck_id"]: d for d in db.get_decks_by_event(session, event_id)}


def _matchups(session, deck_ids):
    return sorted(
        (m["deck_id"], m["opponent_deck_id"], m["result"], m["round"])
        for m in db.list_matchups_by_decks(session, list(deck_ids))
    )


def test_restore_brings_back_a_deleted_event(db_session_rollback):
    session = db_session_rollback
    seed(session)
    before = _matchups(session, [DECK_A, DECK_B])
    sid = snap.take_snapshot(session, EID, "delete")
    db.delete_event(session, EID, delete_decks=True)
    session.flush()
    assert db.get_event(session, EID) is None

    out = snap.restore_snapshot(session, sid)

    assert out == {"event_id": EID, "deck_count": 2, "matchup_count": 2, "safety_snapshot_id": None}
    assert set(_decks(session)) == {DECK_A, DECK_B}
    assert _matchups(session, [DECK_A, DECK_B]) == before
    assert db.get_player_email(session, "Snap Alice") == "snap.alice@example.com"
    assert db.get_event(session, EID).name == "Snap Event"


def test_restore_undoes_edits_and_takes_a_safety_snapshot(db_session_rollback):
    session = db_session_rollback
    seed(session)
    sid = snap.take_snapshot(session, EID, "hadouken")
    deck = session.get(db.DeckRow, DECK_A)
    deck.rank = "99"
    deck.mainboard = [{"qty": 1, "card": "Island"}]
    db.upsert_matchups_for_deck(session, DECK_A, [])  # wipes the match
    db.update_event(session, EID, event_name="Renamed by mistake")
    session.flush()

    out = snap.restore_snapshot(session, sid)
    session.expire_all()

    restored = _decks(session)[DECK_A]
    assert restored["rank"] == "1"
    assert restored["mainboard"] == [{"qty": 1, "card": "Sol Ring"}]
    assert len(_matchups(session, [DECK_A, DECK_B])) == 2
    assert db.get_event(session, EID).name == "Snap Event"
    safety = session.get(EventSnapshotRow, out["safety_snapshot_id"])
    assert safety.reason == "before_restore"
    assert safety.payload["event"]["event_name"] == "Renamed by mistake"


def test_restore_can_itself_be_undone(db_session_rollback):
    session = db_session_rollback
    seed(session)
    sid = snap.take_snapshot(session, EID, "hadouken")
    session.get(db.DeckRow, DECK_A).rank = "99"
    session.flush()
    out = snap.restore_snapshot(session, sid)
    snap.restore_snapshot(session, out["safety_snapshot_id"])
    session.expire_all()
    assert _decks(session)[DECK_A]["rank"] == "99"


def test_restore_after_merge_moves_decks_back(db_session_rollback):
    session = db_session_rollback
    seed(session)
    db.create_event(session, "Kept Event", "01/01/25", "EDH", event_id="snap_ev_keep", player_count=2)
    session.flush()
    sid = snap.take_snapshot(session, EID, "merge")
    db.reassign_decks_to_event(session, EID, "snap_ev_keep", "Kept Event", "01/01/25")
    db.delete_event(session, EID)
    session.flush()
    assert set(_decks(session, "snap_ev_keep")) == {DECK_A, DECK_B}

    snap.restore_snapshot(session, sid)
    session.expire_all()

    assert set(_decks(session)) == {DECK_A, DECK_B}
    assert _decks(session, "snap_ev_keep") == {}


def test_restore_removes_decks_added_after_the_snapshot(db_session_rollback):
    session = db_session_rollback
    seed(session)
    sid = snap.take_snapshot(session, EID, "hadouken")
    db.upsert_deck(session, _deck(987009, EID, "Snap Latecomer"))
    session.flush()
    snap.restore_snapshot(session, sid)
    session.expire_all()
    assert set(_decks(session)) == {DECK_A, DECK_B}


def test_restore_recreates_a_player_that_was_deleted(db_session_rollback):
    session = db_session_rollback
    seed(session)
    sid = snap.take_snapshot(session, EID, "delete")
    alice_id = _decks(session)[DECK_A]["player_id"]
    db.delete_event(session, EID, delete_decks=True)
    session.flush()
    session.query(db.PlayerEmailRow).filter(db.PlayerEmailRow.player_id == alice_id).delete()
    session.query(db.PlayerRow).filter(db.PlayerRow.id == alice_id).delete()
    session.flush()

    snap.restore_snapshot(session, sid)
    session.expire_all()

    restored = _decks(session)[DECK_A]
    assert restored["player"] == "Snap Alice"
    assert restored["player_id"] is not None


def test_restore_keeps_a_player_renamed_since(db_session_rollback):
    """The deck stays attached to the same player; it does not resurrect the old name as a new player."""
    session = db_session_rollback
    seed(session)
    sid = snap.take_snapshot(session, EID, "hadouken")
    alice_id = _decks(session)[DECK_A]["player_id"]
    session.get(db.PlayerRow, alice_id).display_name = "Snap Alice Renamed"
    session.flush()

    snap.restore_snapshot(session, sid)
    session.expire_all()

    restored = _decks(session)[DECK_A]
    assert restored["player_id"] == alice_id
    assert restored["player"] == "Snap Alice Renamed"
    assert session.query(db.PlayerRow).filter(db.PlayerRow.display_name == "Snap Alice").count() == 0


def test_restore_keeps_origin_and_hand_edited_fields(db_session_rollback):
    session = db_session_rollback
    seed(session)
    session.get(db.DeckRow, DECK_A).manual_fields = ["player"]
    db.get_event(session, EID).manual_fields = ["name"]
    session.flush()
    sid = snap.take_snapshot(session, EID, "delete")
    db.delete_event(session, EID, delete_decks=True)
    session.flush()

    snap.restore_snapshot(session, sid)
    session.expire_all()

    assert db.get_event(session, EID).origin == db.ORIGIN_MTGTOP8
    assert db.get_event(session, EID).manual_fields == ["name"]
    deck = session.get(db.DeckRow, DECK_A)
    assert deck.origin == db.ORIGIN_MTGTOP8
    assert deck.manual_fields == ["player"]
    assert session.get(db.DeckRow, DECK_B).manual_fields is None


def test_restore_of_unknown_snapshot_raises_lookup_error(db_session_rollback):
    import pytest

    with pytest.raises(LookupError):
        snap.restore_snapshot(db_session_rollback, 999_999_999)
