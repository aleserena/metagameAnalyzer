import pytest

from api.formats import is_commander_format


@pytest.mark.parametrize(
    "fmt,expected",
    [
        ("EDH", True),
        ("cEDH", True),
        ("cedh", True),
        ("Commander", True),
        ("Modern", False),
        ("", False),
        (None, False),
    ],
)
def test_is_commander_format(fmt, expected):
    assert is_commander_format(fmt) is expected
