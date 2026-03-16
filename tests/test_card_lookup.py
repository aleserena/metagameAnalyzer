"""Tests for Scryfall card lookup and flavor-name resolution."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mtgtop8 import card_lookup


def test_build_entry_requires_card_faces():
    """_build_entry produces an entry with card_faces (required for valid cache)."""
    card = {
        "name": "Shinko, the Bloodsoaked Keep",
        "image_uris": {"normal": "https://example.com/img.png"},
        "mana_cost": "{R}",
        "type_line": "Legendary Land",
        "cmc": 0,
        "colors": [],
        "color_identity": ["R"],
    }
    entry = card_lookup._build_entry(card)
    assert "card_faces" in entry
    assert len(entry["card_faces"]) >= 1
    assert entry["name"] == "Shinko, the Bloodsoaked Keep"
    assert "error" not in entry


@patch("src.mtgtop8.card_lookup.requests.get")
@patch("src.mtgtop8.card_lookup.requests.post")
@patch("src.mtgtop8.card_lookup.time.sleep")
def test_lookup_cards_resolves_flavor_name_when_collection_not_found(mock_sleep, mock_post, mock_get):
    """When collection lookup misses, lookup retries by flavor_name."""
    card_lookup.clear_cache()

    # Collection API: no direct exact-name hit for the in-universe flavor name.
    mock_post.return_value = MagicMock()
    mock_post.return_value.raise_for_status = MagicMock()
    mock_post.return_value.json.return_value = {
        "not_found": [{"name": "Helm's Deep"}],
        "data": [],
    }

    # Search API: flavor_name search returns the canonical paper card.
    mock_get.return_value = MagicMock()
    mock_get.return_value.raise_for_status = MagicMock()
    mock_get.return_value.json.return_value = {
        "data": [
            {
                "name": "Shinko, the Bloodsoaked Keep",
                "flavor_name": "Helm's Deep",
                "image_uris": {"normal": "https://example.com/img.png"},
                "card_faces": [{"name": "Shinko, the Bloodsoaked Keep", "image_uris": {"normal": "https://example.com/img.png"}}],
                "mana_cost": "",
                "type_line": "Legendary Land",
                "cmc": 0,
                "colors": [],
                "color_identity": ["R"],
                "games": ["paper"],
            }
        ]
    }

    result = card_lookup.lookup_cards(["Helm's Deep"])

    assert "Helm's Deep" in result
    assert "error" not in result["Helm's Deep"]
    assert "card_faces" in result["Helm's Deep"]
    assert result["Helm's Deep"]["name"] == "Shinko, the Bloodsoaked Keep"
    mock_get.assert_called()
    mock_post.assert_called()
