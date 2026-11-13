"""Hand-edit endpoints mark the fields they change, so the next re-scrape leaves them alone."""

from contextlib import contextmanager

import pytest

from api import db
from api.db import DeckRow
from api.services.scrape_store import persist_scraped_decks
from tests.test_scrape_store import D1, EID, _deck, _seed


@pytest.fixture
def in_session(db_session_rollback, monkeypatch):
    """Run handlers inside the rolled-back test session, reading decks straight from the database."""
    session = db_session_rollback

    @contextmanager
    def scope():
        yield session
        session.flush()

    monkeypatch.setattr(db, "session_scope", scope)
    from api.routers import decks as decks_router
    from api.routers import events as events_router
    from api.routers import upload as upload_router

    def deck_from_db(deck_id):
        row = session.get(DeckRow, deck_id)
        return db.deck_row_to_dict(row) if row else None

    for module in (decks_router, upload_router):
        monkeypatch.setattr(module, "_get_deck_by_id", deck_from_db)
        monkeypatch.setattr(module, "_load_decks_from_db", lambda: None)
    monkeypatch.setattr(events_router, "_load_decks_from_db", lambda: None)
    monkeypatch.setattr(events_router, "_invalidate_events_cache", lambda: None)
    _seed(session)
    # Like a real EDH deck from mtgtop8: it has a commander, so the "first card is the commander"
    # default of the edit handlers does not kick in.
    session.get(DeckRow, D1).commanders = ["Sol Ring"]
    session.flush()
    return session


def _manual(session, deck_id=D1):
    session.expire_all()
    return sorted(session.get(DeckRow, deck_id).manual_fields or [])


def _forced_rescrape(session):
    scraped = _deck(D1, "Store A", name="Scraped name")
    scraped["rank"] = "8"
    scraped["mainboard"] = [{"qty": 1, "card": "Scraped Card"}]
    persist_scraped_decks(session, [scraped], refresh_events=True)
    session.flush()
    session.expire_all()
    return session.get(DeckRow, D1)


def test_saving_the_deck_form_protects_only_what_changed(in_session):
    """The deck page sends all seven fields on every save."""
    from api.routers.decks import update_deck_endpoint
    from api.schemas.decks import UpdateDeckBody

    stored = db.deck_row_to_dict(in_session.get(DeckRow, D1))
    update_deck_endpoint(
        D1,
        UpdateDeckBody(
            name=stored["name"],
            player=stored["player"],
            rank="2",  # the only real change
            archetype=stored["archetype"],
            commanders=stored["commanders"],
            mainboard=stored["mainboard"],
            sideboard=stored["sideboard"],
        ),
        role="admin",
        actor="admin",
    )

    assert _manual(in_session) == ["rank"]
    row = _forced_rescrape(in_session)
    assert row.rank == "2"
    assert row.name == "Scraped name" and row.mainboard == [{"qty": 1, "card": "Scraped Card"}]


def test_admin_deck_edit_marks_only_the_fields_it_changed(in_session):
    from api.routers.decks import update_deck_endpoint
    from api.schemas.decks import UpdateDeckBody

    update_deck_endpoint(D1, UpdateDeckBody(rank="2", archetype="Hand Arch"), role="admin", actor="admin")

    assert _manual(in_session) == ["archetype", "rank"]
    row = _forced_rescrape(in_session)
    assert (row.rank, row.archetype) == ("2", "Hand Arch")
    assert row.name == "Scraped name"  # not edited by hand, so it follows mtgtop8


def test_organiser_deck_edit_through_an_edit_link_is_protected_too(in_session):
    from api.routers.decks import update_deck_endpoint
    from api.schemas.decks import UpdateDeckBody

    update_deck_endpoint(
        D1, UpdateDeckBody(player="Store A Fixed"), role="event_edit", actor="link:event_edit:Organiser"
    )

    assert _manual(in_session) == ["player"]
    assert _forced_rescrape(in_session).player == "Store A Fixed"


def test_player_updating_their_deck_through_a_link_protects_it(in_session):
    from api.routers.upload import submit_deck_with_upload_link
    from api.schemas.decks import SubmitDeckBody

    session = in_session
    db.create_upload_link(session, "tok-manual-update", EID, deck_id=D1)
    session.flush()
    submit_deck_with_upload_link(
        "tok-manual-update",
        SubmitDeckBody(name="My real list", player="Store A", rank="1", mainboard=[{"qty": 1, "card": "Island"}]),
    )

    # player, rank and sideboard were resent unchanged; the commander follows the new first card (EDH)
    assert _manual(session) == ["commanders", "mainboard", "name"]
    row = _forced_rescrape(session)
    assert row.name == "My real list"
    assert row.mainboard == [{"qty": 1, "card": "Island"}]


def test_feedback_link_protects_the_archetype_and_the_replaced_deck_list(in_session):
    from api.routers.upload import submit_decklist_with_upload_link, submit_feedback_with_upload_link
    from api.schemas.decks import DeckListBody
    from api.schemas.upload import EventFeedbackBody

    session = in_session
    db.create_upload_link(session, "tok-manual-feedback", EID, deck_id=D1, link_type=db.LINK_TYPE_FEEDBACK)
    session.flush()
    submit_decklist_with_upload_link(
        "tok-manual-feedback", DeckListBody(mainboard=[{"qty": 1, "card": "Forest"}], sideboard=[], commanders=[])
    )
    assert _manual(session) == ["commanders", "mainboard"]  # sideboard was resent unchanged

    submit_feedback_with_upload_link("tok-manual-feedback", EventFeedbackBody(archetype="Reported Arch", matchups=[]))
    assert _manual(session) == ["archetype", "commanders", "mainboard"]

    row = _forced_rescrape(session)
    assert row.archetype == "Reported Arch"
    assert row.mainboard == [{"qty": 1, "card": "Forest"}]
    assert row.rank == "8"  # not touched by the player, so it follows mtgtop8


def test_event_edit_marks_the_fields_it_sent(in_session):
    from api.routers.events import update_event_endpoint

    session = in_session
    update_event_endpoint(
        EID,
        actor="admin",
        event_name="Corrected event name",
        date=None,
        format_id=None,
        player_count=16,
        store="Corrected store",
        location=None,
    )
    session.expire_all()
    event = db.get_event(session, EID)
    assert sorted(event.manual_fields) == ["name", "store"]  # player_count is not a protected field

    _forced_rescrape(session)
    event = db.get_event(session, EID)
    assert (event.name, event.store) == ("Corrected event name", "Corrected store")


def test_saving_the_event_form_unchanged_protects_nothing(in_session):
    """The event page sends every detail on save, then re-saves every deck."""
    from api.routers.events import update_event_endpoint

    session = in_session
    event = db.get_event(session, EID)
    update_event_endpoint(
        EID,
        actor="admin",
        event_name=event.name,
        date=event.date,
        format_id=event.format_id,
        player_count=event.player_count,
        store=event.store,
        location=event.location,
    )
    session.expire_all()
    assert db.get_event(session, EID).manual_fields is None


def test_a_commander_filled_in_by_the_edit_is_protected_too(in_session):
    """EDH decks without a commander get their first card as commander on any hand edit."""
    from api.routers.decks import update_deck_endpoint
    from api.schemas.decks import UpdateDeckBody

    session = in_session
    session.get(DeckRow, D1).commanders = []
    session.flush()
    update_deck_endpoint(D1, UpdateDeckBody(rank="2"), role="admin", actor="admin")
    assert _manual(session) == ["commanders", "rank"]
    assert _forced_rescrape(session).commanders == ["Sol Ring"]
