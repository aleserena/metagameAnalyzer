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


# ---- hand corrections survive a re-scrape -------------------------------------------------------


def _hand_edit(session, deck_id, **changes):
    """What the deck edit endpoint does: write the changed fields and mark them as hand-edited."""
    from api import db

    row = session.get(DeckRow, deck_id)
    current = db.deck_row_to_dict(row)
    current.update(changes)
    if "player" in changes:
        current.pop("player_id", None)
    upsert_deck(session, current, manual_fields=tuple(changes))
    session.flush()


def _rescrape(session, *decks, force=True):
    out = persist_scraped_decks(session, [dict(d) for d in decks], refresh_events=force)
    session.flush()
    session.expire_all()
    return out


def test_rescrape_keeps_a_hand_corrected_player_and_refreshes_the_rest(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    _hand_edit(session, D1, player="Store A Corrected")
    corrected_id = session.get(DeckRow, D1).player_id

    scraped = _deck(D1, "Store A", name="New scraped name")
    scraped["rank"] = "7"
    _rescrape(session, scraped)

    row = session.get(DeckRow, D1)
    assert row.player == "Store A Corrected" and row.player_id == corrected_id
    assert row.name == "New scraped name" and row.rank == "7"  # untouched fields still refresh
    assert row.manual_fields == ["player"]


def test_a_normal_rescrape_also_keeps_corrections(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    _hand_edit(session, D1, rank="2")
    scraped = _deck(D1, "Store A")
    scraped["rank"] = "9"
    _rescrape(session, scraped, force=False)
    assert session.get(DeckRow, D1).rank == "2"


def test_hand_corrected_card_list_and_archetype_survive(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    fixed = [{"qty": 1, "card": "Island"}, {"qty": 1, "card": "Counterspell"}]
    _hand_edit(session, D1, mainboard=fixed, sideboard=[{"qty": 1, "card": "Negate"}], archetype="Fixed Arch")
    scraped = _deck(D1, "Store A")
    scraped["archetype"] = "Scraped Arch"
    _rescrape(session, scraped)
    row = session.get(DeckRow, D1)
    assert row.mainboard == fixed
    assert row.sideboard == [{"qty": 1, "card": "Negate"}]
    assert row.archetype == "Fixed Arch"
    assert sorted(row.manual_fields) == ["archetype", "mainboard", "sideboard"]


def test_field_set_back_to_the_scraped_value_stays_protected(db_session_rollback):
    """Confirming the scraped value by hand is still a hand edit."""
    session = db_session_rollback
    _seed(session)
    _hand_edit(session, D1, rank="1")  # same value the scrape gave
    scraped = _deck(D1, "Store A")
    scraped["rank"] = "4"
    _rescrape(session, scraped)
    assert session.get(DeckRow, D1).rank == "1"


def test_marking_fields_accumulates_across_edits(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    _hand_edit(session, D1, rank="2")
    _hand_edit(session, D1, name="Hand name")
    assert sorted(session.get(DeckRow, D1).manual_fields) == ["name", "rank"]


def test_unedited_deck_is_fully_refreshed(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    scraped = _deck(D2, "Store B", name="Fresh")
    scraped["rank"] = "3"
    _rescrape(session, scraped)
    row = session.get(DeckRow, D2)
    assert (row.name, row.rank, row.manual_fields) == ("Fresh", "3", None)


def test_decks_edited_before_this_release_are_not_protected(db_session_rollback):
    """Known limit: an old correction has no marker, so a re-scrape overwrites it."""
    session = db_session_rollback
    _seed(session)
    session.get(DeckRow, D1).rank = "2"  # edited, but manual_fields stays NULL
    session.flush()
    scraped = _deck(D1, "Store A")
    scraped["rank"] = "9"
    _rescrape(session, scraped)
    assert session.get(DeckRow, D1).rank == "9"


def test_only_known_field_names_are_marked(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    current = __import__("api.db", fromlist=["x"]).deck_row_to_dict(session.get(DeckRow, D1))
    upsert_deck(session, current, manual_fields=("rank", "event_id", "nonsense"))
    session.flush()
    assert session.get(DeckRow, D1).manual_fields == ["rank"]


def test_event_details_edited_by_hand_survive_a_forced_rescrape(db_session_rollback):
    from api import db

    session = db_session_rollback
    _seed(session)
    db.update_event(session, EID, event_name="Hand-fixed name", store="My Store", manual_fields=("name", "store"))
    session.flush()

    _rescrape(session, _deck(D1, "Store A"))  # scraped event name is "Scrape Store Test"

    event = db.get_event(session, EID)
    assert event.name == "Hand-fixed name" and event.store == "My Store"
    assert sorted(event.manual_fields) == ["name", "store"]


def test_unedited_event_is_refreshed_by_a_forced_rescrape(db_session_rollback):
    from api import db

    session = db_session_rollback
    _seed(session)
    scraped = _deck(D1, "Store A")
    scraped["event_name"] = "Renamed On Mtgtop8"
    _rescrape(session, scraped)
    assert db.get_event(session, EID).name == "Renamed On Mtgtop8"
