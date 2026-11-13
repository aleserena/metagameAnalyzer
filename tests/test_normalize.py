import time

import pytest

from api.db import archetype_canonical_key
from src.mtgtop8.normalize import canonical_card_name_for_compare, double_split_separators, normalize_card_name


def test_canonical_card_name_for_compare_double_faced():
    """Double-faced cards: full name and front-only match; returns lowercase for case-insensitive comparison."""
    assert canonical_card_name_for_compare("Norman Osborn // Green Goblin") == "norman osborn"
    assert canonical_card_name_for_compare("Norman Osborn") == "norman osborn"
    assert canonical_card_name_for_compare("  Delney // Streetwise Lookout  ") == "delney"
    assert canonical_card_name_for_compare("Fire // Ice") == "fire"


def test_normalize_card_name_split_and_suffixes():
    assert normalize_card_name("Fire / Ice") == "Fire // Ice"
    assert normalize_card_name("Fire // Ice") == "Fire // Ice"
    assert normalize_card_name("Ashling (ECC) 1 *F*") == "Ashling"


def test_normalize_card_name_handles_non_string():
    assert normalize_card_name(None) == ""
    assert normalize_card_name(123) == "123"



def test_normalize_card_name_suffix_variants():
    assert normalize_card_name("Sol Ring*F*") == "Sol Ring"
    assert normalize_card_name("Sol Ring *F* *C*") == "Sol Ring"
    assert normalize_card_name("Sol Ring (C21)") == "Sol Ring"
    assert normalize_card_name("Sol Ring (c21)  263 ") == "Sol Ring"
    assert normalize_card_name("Sol Ring (TOOLONG) 1") == "Sol Ring (TOOLONG) 1"
    assert normalize_card_name("Sol Ring (C21) 1 2") == "Sol Ring (C21) 1 2"
    assert normalize_card_name("Wear  /   Tear") == "Wear // Tear"
    assert normalize_card_name("Wear/Tear") == "Wear/Tear"


def test_double_split_separators_matches_the_old_regex_on_odd_spacing():
    # same as re.sub(r"\s+/\s+", " // ", s): the second slash's leading space was already consumed
    assert double_split_separators("a / / b") == "a // / b"
    assert double_split_separators("a // b / c") == "a // b / c"


@pytest.mark.parametrize("name", [
    "a" + " " * 50_000 + "x",
    "a" + " " * 50_000 + "/",
    "**" + "** " * 50_000 + "x",
    "***" + "****" * 50_000 + "x",
    "(AB)" + " " * 50_000 + "x",
], ids=["spaces", "spaces-slash", "stars", "star-runs", "set-code-spaces"])
def test_normalization_is_linear_on_adversarial_names(name):
    start = time.perf_counter()
    normalize_card_name(name)
    double_split_separators(name)
    archetype_canonical_key(name)
    assert time.perf_counter() - start < 0.5
