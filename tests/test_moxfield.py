from unittest.mock import MagicMock, patch

from api.routers.decks import _extract_moxfield_boards

CARD = {"abc": {"quantity": 2, "card": {"name": "Sol Ring"}}}
CMD = {"xyz": {"quantity": 1, "card": {"name": "Atraxa, Praetors' Voice"}}}


def test_v2_shape():
    assert _extract_moxfield_boards({"commanders": CMD, "mainboard": CARD, "sideboard": {}}) == (
        ["Atraxa, Praetors' Voice"],
        [{"qty": 2, "card": "Sol Ring"}],
        [],
    )


def test_v3_shape():
    data = {
        "boards": {
            "commanders": {"cards": CMD},
            "mainboard": {"cards": CARD},
            "sideboard": {"cards": {}},
        }
    }
    assert _extract_moxfield_boards(data) == (
        ["Atraxa, Praetors' Voice"],
        [{"qty": 2, "card": "Sol Ring"}],
        [],
    )


def test_import_returns_502_when_nothing_parsed(client_with_overrides):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"name": "Empty"}
    with patch("api.routers.decks.requests.get", return_value=resp):
        r = client_with_overrides.post(
            "/api/v1/decks/import-moxfield",
            json={"url": "https://www.moxfield.com/decks/abc123"},
        )
    assert r.status_code == 502
