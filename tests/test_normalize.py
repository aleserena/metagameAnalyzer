from src.mtgtop8.normalize import canonical_card_name_for_compare, normalize_card_name


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

