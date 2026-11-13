"""Tests for the single-elimination bracket rules (api/brackets.py)."""

import pytest

from api.brackets import (
    bracket_rounds,
    elimination_round,
    expected_matches_for_rank,
    is_single_elimination,
    rank_band_upper,
    round_label,
    validate_structure,
)


def test_validate_structure():
    assert validate_structure(None, None) == ("swiss", None)
    assert validate_structure("", 8) == ("swiss", None)
    assert validate_structure("swiss", 16) == ("swiss", None)
    assert validate_structure("single_elimination", 16) == ("single_elimination", 16)
    for bad in [("single_elimination", None), ("single_elimination", 12), ("single_elimination", 256), ("league", None)]:
        with pytest.raises(ValueError):
            validate_structure(*bad)


def test_is_single_elimination():
    assert is_single_elimination("single_elimination")
    assert not is_single_elimination("swiss")
    assert not is_single_elimination(None)


def test_bracket_rounds():
    assert [bracket_rounds(s) for s in (2, 4, 8, 16, 128)] == [1, 2, 3, 4, 7]


def test_rank_band_upper():
    assert [rank_band_upper(r) for r in ["1", "2", "3-4", "5-8", "9-16", "7", "65-128", "", None, "x"]] == [
        1, 2, 4, 8, 16, 8, 128, None, None, None,
    ]


def test_expected_matches_16():
    assert [expected_matches_for_rank(r, 16) for r in ["1", "2", "3-4", "5-8", "9-16", "17-32", "", "7"]] == [
        4, 4, 3, 2, 1, 0, 1, 2,
    ]


def test_expected_matches_8():
    assert [expected_matches_for_rank(r, 8) for r in ["1", "2", "3-4", "5-8", "9-16"]] == [3, 3, 2, 1, 0]


def test_elimination_round_16():
    assert [elimination_round(r, 16) for r in ["1", "2", "3-4", "5-8", "9-16", "17-32", ""]] == [
        None, 4, 3, 2, 1, None, None,
    ]


def test_round_label():
    assert [round_label(r, 16) for r in (1, 2, 3, 4)] == ["Round of 16", "Quarterfinal", "Semifinal", "Final"]
    assert round_label(1, 32) == "Round of 32"
    assert round_label(1, 2) == "Final"
