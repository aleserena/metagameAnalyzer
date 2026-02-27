from src.mtgtop8.normalize import normalize_card_name


def test_normalize_card_name_split_and_suffixes():
    assert normalize_card_name("Fire / Ice") == "Fire // Ice"
    assert normalize_card_name("Fire // Ice") == "Fire // Ice"
    assert normalize_card_name("Ashling (ECC) 1 *F*") == "Ashling"


def test_normalize_card_name_handles_non_string():
    assert normalize_card_name(None) == ""
    assert normalize_card_name(123) == "123"

