"""Tests for API helper functions."""

import pytest
import api.main as api_main


def test_normalize_split_cards_fire_ice(deck_with_split_card):
    """_normalize_split_cards converts Fire / Ice to Fire // Ice."""
    decks = [deck_with_split_card]
    api_main._normalize_split_cards(decks)
    main_cards = [c["card"] for c in decks[0]["mainboard"]]
    side_cards = [c["card"] for c in decks[0]["sideboard"]]
    assert "Fire // Ice" in main_cards
    assert "Life // Death" in side_cards
    assert "Fire / Ice" not in main_cards
    assert "Life / Death" not in side_cards


def test_normalize_split_cards_unchanged_when_correct():
    """_normalize_split_cards leaves Fire // Ice unchanged."""
    decks = [{"mainboard": [{"qty": 1, "card": "Fire // Ice"}], "sideboard": []}]
    api_main._normalize_split_cards(decks)
    assert decks[0]["mainboard"][0]["card"] == "Fire // Ice"


def test_parse_date_sortkey():
    """_parse_date_sortkey converts DD/MM/YY to YYMMDD."""
    assert api_main._parse_date_sortkey("15/02/26") == "260215"
    assert api_main._parse_date_sortkey("01/12/24") == "241201"
    assert api_main._parse_date_sortkey("invalid") == "invalid"


def test_deck_sort_key():
    """_deck_sort_key sorts by date desc, then rank asc."""
    d1 = {"date": "15/02/26", "rank": "2"}
    d2 = {"date": "15/02/26", "rank": "1"}
    d3 = {"date": "10/01/26", "rank": "1"}
    key1 = api_main._deck_sort_key(d1)
    key2 = api_main._deck_sort_key(d2)
    key3 = api_main._deck_sort_key(d3)
    assert key2 < key1  # same date, rank 1 before 2
    assert key1[0] < key3[0]  # 26/02/15 > 26/01/10 (negative for desc)


def test_date_in_range():
    """_date_in_range correctly filters DD/MM/YY dates."""
    assert api_main._date_in_range("15/02/26", "01/02/26", "28/02/26") is True
    assert api_main._date_in_range("01/01/26", "15/02/26", "28/02/26") is False
    assert api_main._date_in_range("01/03/26", "01/02/26", "28/02/26") is False
    assert api_main._date_in_range("15/02/26", None, None) is True
