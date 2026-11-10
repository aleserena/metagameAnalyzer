import threading
from unittest.mock import patch

from api.services import deck_index
from api.state import state


def test_color_identities_are_built_once_under_concurrency(sample_decks):
    state.set_decks(list(sample_decks))
    calls = []

    def slow_lookup(names):
        calls.append(names)
        return {
            "Spider-Man 2099": {"color_identity": ["U", "R"]},
            "Terra, Magical Adept": {"color_identity": ["R", "U"]},
        }

    with patch.object(deck_index, "lookup_cards", side_effect=slow_lookup):
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(deck_index.color_identities()))
            for _ in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert len(calls) == 1
    assert all(r == {811597: ["U", "R"], 811598: ["U", "R"]} for r in results)


def test_duplicate_map_follows_the_data_version(sample_decks):
    state.set_decks(list(sample_decks))
    with patch.object(deck_index, "find_duplicate_decks", return_value={}) as spy:
        deck_index.duplicate_map()
        deck_index.duplicate_map()
        assert spy.call_count == 1
        state.set_decks(list(sample_decks))
        deck_index.duplicate_map()
        assert spy.call_count == 2


def test_color_lookup_failure_yields_empty_map(sample_decks):
    state.set_decks(list(sample_decks))
    with patch.object(deck_index, "lookup_cards", side_effect=RuntimeError("boom")):
        assert deck_index.color_identities() == {}
