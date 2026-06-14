"""Tests for Scryfall card lookup and flavor-name resolution."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mtgtop8 import card_lookup


def test_scryfall_image_urls_builds_cdn_paths():
    sid = "67f4c93b-080c-4196-b095-6a120a221988"
    urls = card_lookup.scryfall_image_urls(sid)
    assert urls == {
        "small": f"https://cards.scryfall.io/small/front/6/7/{sid}.jpg",
        "normal": f"https://cards.scryfall.io/normal/front/6/7/{sid}.jpg",
        "large": f"https://cards.scryfall.io/large/front/6/7/{sid}.jpg",
    }


def test_scryfall_image_urls_back_face():
    sid = "abcd1234-0000-0000-0000-000000000000"
    urls = card_lookup.scryfall_image_urls(sid, face="back")
    assert urls["normal"] == f"https://cards.scryfall.io/normal/back/a/b/{sid}.jpg"


def test_scryfall_image_urls_none_for_missing_id():
    assert card_lookup.scryfall_image_urls("") is None
    assert card_lookup.scryfall_image_urls(None) is None


class _FakeCardRow:
    def __init__(self, **kw):
        self.name = kw.get("name", "")
        self.scryfall_id = kw.get("scryfall_id")
        self.layout = kw.get("layout", "normal")
        self.mana_cost = kw.get("mana_cost", "")
        self.cmc = kw.get("cmc", 0)
        self.type_line = kw.get("type_line", "")
        self.oracle_text = kw.get("oracle_text", "")
        self.colors = kw.get("colors", [])
        self.color_identity = kw.get("color_identity", [])
        self.card_faces = kw.get("card_faces", [])
        self.price_usd = kw.get("price_usd")
        self.price_usd_foil = kw.get("price_usd_foil")
        self.price_eur = kw.get("price_eur")
        self.price_eur_foil = kw.get("price_eur_foil")


def test_row_to_entry_single_face():
    row = _FakeCardRow(
        name="Lightning Bolt",
        scryfall_id="67f4c93b-080c-4196-b095-6a120a221988",
        layout="normal",
        mana_cost="{R}",
        cmc=1.0,
        type_line="Instant",
        colors=["R"],
        color_identity=["R"],
        card_faces=[{"name": "Lightning Bolt", "side": None}],
        price_usd="1.50",
    )
    entry = card_lookup._row_to_entry(row)
    assert entry["name"] == "Lightning Bolt"
    assert entry["image_uris"]["normal"].endswith("/6/7/67f4c93b-080c-4196-b095-6a120a221988.jpg")
    assert entry["card_faces"] == [{"name": "Lightning Bolt", "image_uris": entry["image_uris"]}]
    assert entry["prices"]["usd"] == "1.50"
    assert entry["prices"]["tix"] is None


def test_row_to_entry_two_faced_builds_front_and_back():
    row = _FakeCardRow(
        name="Delver of Secrets // Insectile Aberration",
        scryfall_id="11112222-3333-4444-5555-666677778888",
        layout="transform",
        card_faces=[
            {"name": "Delver of Secrets", "side": "a"},
            {"name": "Insectile Aberration", "side": "b"},
        ],
    )
    entry = card_lookup._row_to_entry(row)
    assert entry["image_uris"] is None
    assert len(entry["card_faces"]) == 2
    assert "/front/" in entry["card_faces"][0]["image_uris"]["normal"]
    assert "/back/" in entry["card_faces"][1]["image_uris"]["normal"]


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
