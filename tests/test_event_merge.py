from types import SimpleNamespace as NS

import pytest

from api.routers.events import _resolve_merge_pairs

KEEP = [{"deck_id": 10, "player_id": 1}, {"deck_id": 11, "player_id": 2}]
REMOVE = [{"deck_id": 20, "player_id": 1}, {"deck_id": 21, "player_id": 3}]


def test_auto_and_manual_pairs():
    pairs = _resolve_merge_pairs(KEEP, REMOVE, [NS(deck_id_keep=11, deck_id_remove=21)])
    assert pairs == [(10, 20), (11, 21)]


def test_manual_pair_for_auto_paired_remove_is_ignored():
    pairs = _resolve_merge_pairs(KEEP, REMOVE, [NS(deck_id_keep=11, deck_id_remove=20)])
    assert pairs == [(10, 20)]


@pytest.mark.parametrize(
    "pair",
    [
        NS(deck_id_keep=99, deck_id_remove=21),
        NS(deck_id_keep=11, deck_id_remove=99),
        NS(deck_id_keep=10, deck_id_remove=21),
    ],
)
def test_invalid_manual_pair_is_rejected(pair):
    with pytest.raises(ValueError):
        _resolve_merge_pairs(KEEP, REMOVE, [pair])
