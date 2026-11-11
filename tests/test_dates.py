from datetime import date

import pytest

from api.dates import in_range, parse_bound, parse_ddmmyy, sort_key


@pytest.mark.parametrize(
    "s,expected",
    [
        ("05/03/25", date(2025, 3, 5)),
        ("05/03/2025", date(2025, 3, 5)),
        ("31/12/99", date(2099, 12, 31)),
        (" 01/01/24 ", date(2024, 1, 1)),
        ("31/02/25", None),
        ("2025-03-05", None),
        ("", None),
        (None, None),
        ("garbage", None),
    ],
)
def test_parse_ddmmyy(s, expected):
    assert parse_ddmmyy(s) == expected


def test_parse_bound_accepts_iso():
    assert parse_bound("2025-03-05T00:00:00Z") == date(2025, 3, 5)
    assert parse_bound("05/03/25") == date(2025, 3, 5)


@pytest.mark.parametrize(
    "deck,frm,to,expected",
    [
        ("15/02/25", "01/02/25", "28/02/25", True),
        ("15/02/25", "16/02/25", None, False),
        ("15/02/25", None, "14/02/25", False),
        ("15/02/25", "2025-02-15", "15/02/2025", True),
        ("", "01/02/25", "28/02/25", True),
        ("15/02/25", "nonsense", None, True),
        ("31/01/25", "01/02/25", None, False),
    ],
)
def test_in_range(deck, frm, to, expected):
    assert in_range(deck, frm, to) is expected


def test_sort_key():
    assert sort_key("05/03/25") == "250305"
    assert sort_key("05/03/2025") == "250305"
    assert sort_key("bad") == "bad"


def test_format_ddmmyy():
    from api.dates import format_ddmmyy

    assert format_ddmmyy(date(2025, 3, 5)) == "05/03/25"
    assert format_ddmmyy(None) == ""
