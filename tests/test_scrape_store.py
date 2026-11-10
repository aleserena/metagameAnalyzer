from api.db import DeckRow, MatchupRow, create_event, upsert_deck, upsert_matchups_for_deck
from api.services.scrape_store import persist_scraped_decks

EID = "9900001"
D1, D2, D3 = 9900011, 9900012, 9900013


def _deck(deck_id, player, name="Deck"):
    return {
        "deck_id": deck_id,
        "event_id": int(EID),
        "format_id": "EDH",
        "name": name,
        "player": player,
        "player_id": None,
        "event_name": "Scrape Store Test",
        "date": "01/01/25",
        "rank": "1",
        "player_count": 8,
        "mainboard": [{"qty": 1, "card": "Sol Ring"}],
        "sideboard": [],
        "commanders": [],
        "archetype": "Test Arch",
    }


def _seed(session):
    create_event(session, "Scrape Store Test", "01/01/25", "EDH", origin="mtgtop8", event_id=EID, player_count=8)
    for did, player in ((D1, "Store A"), (D2, "Store B"), (D3, "Store C")):
        d = _deck(did, player)
        d.pop("player_id")
        upsert_deck(session, d)
    session.flush()
    upsert_matchups_for_deck(
        session,
        D1,
        [{"opponent_player": "Store B", "opponent_deck_id": D2, "result": "win", "round": 1}],
    )
    session.flush()


def test_refresh_keeps_matchups_and_updates_fields(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    decks = [_deck(D1, "Store A", name="Renamed"), _deck(D2, "Store B")]
    out = persist_scraped_decks(session, decks, refresh_events=True)
    session.flush()
    assert out["decks_saved"] == 2
    assert out["failed"] == []
    assert session.query(MatchupRow).filter(MatchupRow.deck_id.in_([D1, D2])).count() == 2
    assert session.query(DeckRow).filter(DeckRow.deck_id == D1).one().name == "Renamed"


def test_deck_missing_from_scrape_is_kept(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    persist_scraped_decks(session, [_deck(D1, "Store A")], refresh_events=True)
    session.flush()
    assert session.query(DeckRow).filter(DeckRow.deck_id == D3).count() == 1


def test_player_conflict_fails_one_deck_and_saves_the_rest(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    decks = [_deck(D1, "Store B"), _deck(D3, "Store C", name="Still Saved")]
    out = persist_scraped_decks(session, decks, refresh_events=True)
    session.flush()
    assert [f["deck_id"] for f in out["failed"]] == [D1]
    assert session.query(DeckRow).filter(DeckRow.deck_id == D3).one().name == "Still Saved"


def test_rescrape_leaves_every_deck_matching_the_event(db_session_rollback):
    from api.db import EventRow, update_event

    session = db_session_rollback
    _seed(session)
    update_event(session, EID, player_count=40, store="Card Shop", location="Town")
    session.flush()
    out = persist_scraped_decks(session, [_deck(D1, "Store A")], refresh_events=True)
    session.flush()
    assert out["failed"] == []
    ev = session.query(EventRow).filter(EventRow.event_id == EID).one()
    assert ev.player_count == 40
    decks = session.query(DeckRow).filter(DeckRow.event_id == EID).all()
    assert len(decks) == 3
    for d in decks:
        assert d.player_count == 40
        assert d.event_name == "Scrape Store Test @ Card Shop (Town)"


def test_data_error_fails_one_deck_and_saves_the_rest(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    bad = _deck(D1, "Store A")
    bad["rank"] = "x" * 100
    out = persist_scraped_decks(session, [bad, _deck(D3, "Store C", name="Still Saved")], refresh_events=True)
    session.flush()
    assert [f["deck_id"] for f in out["failed"]] == [D1]
    assert session.query(DeckRow).filter(DeckRow.deck_id == D3).one().name == "Still Saved"
