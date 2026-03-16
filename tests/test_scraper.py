"""Unit tests for src.mtgtop8.scraper (pure functions and parsing)."""

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
