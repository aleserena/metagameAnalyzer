"""Unit tests for src.mtgtop8.scraper (pure functions and parsing)."""

import pytest
from src.mtgtop8 import scraper
from src.mtgtop8.models import Deck
from src.mtgtop8.scraper import (
    event_display_name,
    parse_event_display,
)


class TestParseEventDisplay:
    """Tests for parse_event_display."""

    def test_full_format(self):
        """Parses 'Name @ Store (Location)' into (name, store, location)."""
        name, store, location = parse_event_display("CR PdLL MTGAnjou @ Angers (France)")
        assert name == "CR PdLL MTGAnjou"
        assert store == "Angers"
        assert location == "France"

    def test_name_and_store_only(self):
        """String with @ but no parentheses returns (name, store, '')."""
        # Parser requires " (" and ")" and " @ " for location; otherwise returns (s, "", "")
        s = "Event Name @ Store Only"
        name, store, location = parse_event_display(s)
        assert name == s
        assert store == ""
        assert location == ""

    def test_name_only(self):
        """String without @ returns (trimmed, '', '')."""
        name, store, location = parse_event_display("Just Event Name")
        assert name == "Just Event Name"
        assert store == ""
        assert location == ""

    def test_empty_and_whitespace(self):
        """Empty or whitespace returns ('', '', '')."""
        assert parse_event_display("") == ("", "", "")
        assert parse_event_display("   ") == ("", "", "")

    def test_location_with_parentheses(self):
        """Location is text between last ' (' and ')'."""
        name, store, location = parse_event_display("Big Tourney @ Store Name (City, Country)")
        assert name == "Big Tourney"
        assert store == "Store Name"
        assert location == "City, Country"


class TestEventDisplayName:
    """Tests for event_display_name."""

    def test_name_only(self):
        """Returns name when store and location empty."""
        assert event_display_name("My Event") == "My Event"
        assert event_display_name("  Trimmed  ") == "Trimmed"

    def test_name_and_store(self):
        """Returns 'Name @ Store' when location empty."""
        assert event_display_name("Event", store="Store") == "Event @ Store"

    def test_name_store_location(self):
        """Returns 'Name @ Store (Location)' when all provided."""
        assert event_display_name("E", store="S", location="L") == "E @ S (L)"

    def test_empty_name_returns_unknown(self):
        """Empty name returns 'Unknown'."""
        assert event_display_name("") == "Unknown"
        assert event_display_name("  ") == "Unknown"

    def test_store_only_no_location(self):
        """Name + store, no location: no parentheses."""
        assert event_display_name("FN", store="SN") == "FN @ SN"


@pytest.mark.parametrize("workers", [1, 3])
def test_failed_deck_is_reported_and_others_kept(monkeypatch, workers):
    def fake_deck(event_id, deck_id, *_):
        if deck_id == 2:
            raise RuntimeError("boom")
        return Deck(
            deck_id=deck_id,
            event_id=event_id,
            format_id="EDH",
            name="N",
            player="P",
            event_name="E",
            date="01/01/25",
            rank="1",
            player_count=8,
            mainboard=[],
            sideboard=[],
            commanders=[],
        )

    monkeypatch.setattr(scraper, "SCRAPER_MAX_WORKERS", workers)
    monkeypatch.setattr(scraper, "scrape_deck_ids_from_event", lambda *a, **k: [1, 2, 3])
    monkeypatch.setattr(scraper, "scrape_deck_robust", fake_deck)
    errors = []
    decks = scraper.scrape(
        "EDH",
        event_ids=[77],
        on_deck_error=lambda e, d, msg: errors.append((e, d, msg)),
    )
    assert sorted(d.deck_id for d in decks) == [1, 3]
    assert errors == [(77, 2, "boom")]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1", "1"),
        ("3-4", "3-4"),
        ("33-64", "33-64"),
        ("65-128", "65-128"),
        ("47", "47"),
        ("128", "128"),
        ("129", None),
        ("0", None),
        ("Top 8", None),
    ],
)
def test_parse_rank_text(text, expected):
    from src.mtgtop8.scraper import _parse_rank_text

    assert _parse_rank_text(text) == expected
