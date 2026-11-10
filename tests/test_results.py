import pytest

from api.results import effective_wld, invert_result


@pytest.mark.parametrize(
    "result,expected",
    [
        ("win", (1, 0, 0)),
        ("intentional_draw_win", (1, 0, 0)),
        ("2-1", (1, 0, 0)),
        ("loss", (0, 1, 0)),
        ("intentional_draw_loss", (0, 1, 0)),
        ("0-1", (0, 1, 0)),
        ("draw", (0, 0, 1)),
        ("intentional_draw", (0, 0, 1)),
        ("WIN ", (1, 0, 0)),
        ("bye", None),
        ("drop", None),
        ("", None),
        (None, None),
    ],
)
def test_effective_wld(result, expected):
    assert effective_wld(result) == expected


@pytest.mark.parametrize(
    "result,expected",
    [
        ("win", "loss"),
        ("loss", "win"),
        ("draw", "draw"),
        ("intentional_draw", "intentional_draw"),
        ("intentional_draw_win", "intentional_draw_loss"),
        ("intentional_draw_loss", "intentional_draw_win"),
    ],
)
def test_invert_result(result, expected):
    assert invert_result(result) == expected
