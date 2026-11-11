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


def test_not_found_names_are_remembered_for_seven_days(monkeypatch):
    from src.mtgtop8 import card_lookup as cl

    calls = {"post": 0, "flavor": 0}

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [], "not_found": [{"name": "Nonexistent Card"}]}

    def fake_post(*a, **k):
        calls["post"] += 1
        return Resp()

    def fake_flavor(name):
        calls["flavor"] += 1
        return None

    now = [1_000_000.0]
    monkeypatch.setattr(cl, "_card_cache", {})
    monkeypatch.setattr(cl, "_load_cache", lambda: None)
    monkeypatch.setattr(cl, "_save_cache", lambda: None)
    monkeypatch.setattr(cl.requests, "post", fake_post)
    monkeypatch.setattr(cl, "_search_by_flavor_name", fake_flavor)
    monkeypatch.setattr(cl.time, "sleep", lambda s: None)
    monkeypatch.setattr(cl.time, "time", lambda: now[0])

    expected = {"Nonexistent Card": {"error": "not_found"}}
    assert cl._scryfall_lookup_cards(["Nonexistent Card"]) == expected
    assert cl._scryfall_lookup_cards(["Nonexistent Card"]) == expected
    assert calls == {"post": 1, "flavor": 1}

    now[0] += cl.NOT_FOUND_TTL_SECONDS + 1
    cl._scryfall_lookup_cards(["Nonexistent Card"])
    assert calls == {"post": 2, "flavor": 2}


def _setup_lookup(monkeypatch, cache, post, flavor):
    from src.mtgtop8 import card_lookup as cl

    monkeypatch.setattr(cl, "_card_cache", cache)
    monkeypatch.setattr(cl, "_load_cache", lambda: None)
    monkeypatch.setattr(cl, "_save_cache", lambda: None)
    monkeypatch.setattr(cl.requests, "post", post)
    monkeypatch.setattr(cl, "_search_by_flavor_name", flavor)
    monkeypatch.setattr(cl.time, "sleep", lambda s: None)
    return cl


class _NotFoundResp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": [], "not_found": [{"name": "Ghost Card"}]}


def test_flavor_search_transient_error_is_not_cached(monkeypatch):
    calls = {"flavor": 0}

    def flavor(name):
        calls["flavor"] += 1
        raise card_lookup._TransientLookupError("429")

    cache = {}
    cl = _setup_lookup(monkeypatch, cache, lambda *a, **k: _NotFoundResp(), flavor)
    assert cl._scryfall_lookup_cards(["Ghost Card"]) == {"Ghost Card": {"error": "not_found"}}
    assert "Ghost Card" not in cache
    cl._scryfall_lookup_cards(["Ghost Card"])
    assert calls["flavor"] == 2


def test_flavor_search_http_errors_classified(monkeypatch):
    from src.mtgtop8 import card_lookup as cl

    class Resp:
        def __init__(self, code):
            self.status_code = code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise cl.requests.HTTPError(str(self.status_code))

        def json(self):
            return {"data": []}

    monkeypatch.setattr(cl.time, "sleep", lambda s: None)
    monkeypatch.setattr(cl.requests, "get", lambda *a, **k: Resp(404))
    assert cl._search_by_flavor_name("x") is None
    for code in (429, 503):
        monkeypatch.setattr(cl.requests, "get", lambda *a, _c=code, **k: Resp(_c))
        try:
            cl._search_by_flavor_name("x")
        except cl._TransientLookupError:
            pass
        else:
            raise AssertionError("expected transient error")

    def boom(*a, **k):
        raise cl.requests.Timeout()

    monkeypatch.setattr(cl.requests, "get", boom)
    try:
        cl._search_by_flavor_name("x")
    except cl._TransientLookupError:
        pass
    else:
        raise AssertionError("expected transient error")


def test_failed_collection_chunk_is_not_cached_as_not_found(monkeypatch):
    calls = {"post": 0}

    def post(*a, **k):
        calls["post"] += 1
        raise card_lookup.requests.ConnectionError()

    cache = {}
    cl = _setup_lookup(monkeypatch, cache, post, lambda name: None)
    cl._scryfall_lookup_cards(["Ghost Card"])
    assert "Ghost Card" not in cache
    cl._scryfall_lookup_cards(["Ghost Card"])
    assert calls["post"] == 2


def test_legacy_not_found_entry_is_refetched(monkeypatch):
    calls = {"post": 0}

    def post(*a, **k):
        calls["post"] += 1
        return _NotFoundResp()

    cache = {"Ghost Card": {"error": "not_found"}}
    cl = _setup_lookup(monkeypatch, cache, post, lambda name: None)
    cl._scryfall_lookup_cards(["Ghost Card"])
    assert calls["post"] == 1
    assert "checked_at" in cache["Ghost Card"]


def test_names_beyond_a_short_collection_response_are_not_cached_as_not_found(monkeypatch):
    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"name": "Real Card", "prices": {"usd": "1"}}], "not_found": []}

    cache = {}
    cl = _setup_lookup(monkeypatch, cache, lambda *a, **k: Resp(), lambda name: None)
    monkeypatch.setattr(cl, "_card_is_paper", lambda card: True)
    monkeypatch.setattr(cl, "_build_entry", lambda card: {"name": card["name"]})
    cl._scryfall_lookup_cards(["Real Card", "Leftover Card"])
    assert "Leftover Card" not in cache
    assert cache["Real Card"] == {"name": "Real Card"}


def test_db_error_does_not_fall_back_to_scryfall_for_everything(monkeypatch):
    from src.mtgtop8 import card_lookup as cl
    import api.db as db

    monkeypatch.setattr(db, "is_database_available", lambda: True)

    def boom():
        raise RuntimeError("connection reset")

    monkeypatch.setattr(db, "session_scope", boom)
    called = []
    monkeypatch.setattr(cl, "_scryfall_lookup_cards", lambda names: called.append(names) or {})
    assert cl.lookup_cards(["Sol Ring", "Island"]) == {}
    assert called == []


def test_lookup_cards_strict_reraises_db_error(monkeypatch):
    from src.mtgtop8 import card_lookup as cl
    import api.db as db
    import pytest

    monkeypatch.setattr(db, "is_database_available", lambda: True)

    def boom():
        raise RuntimeError("connection reset")

    monkeypatch.setattr(db, "session_scope", boom)
    with pytest.raises(RuntimeError):
        cl.lookup_cards(["Sol Ring"], strict=True)


# ---- bounded Scryfall fallback (public lookups) ---------------------------------------------


def _no_database(monkeypatch):
    """Every name is missing from the cards table; record what goes to the Scryfall fallback."""
    from src.mtgtop8 import card_lookup as cl
    import api.db as db

    monkeypatch.setattr(db, "is_database_available", lambda: False)
    monkeypatch.setattr(cl, "SCRYFALL_FALLBACK_ENABLED", True)
    sent: list[str] = []

    def fake_fallback(names):
        sent.extend(names)
        return {n: {"name": n} for n in names}

    monkeypatch.setattr(cl, "_scryfall_lookup_cards", fake_fallback)
    return cl, sent


def test_max_fallback_limits_names_sent_to_scryfall(monkeypatch):
    cl, sent = _no_database(monkeypatch)
    names = [f"Unknown {i}" for i in range(20)]
    result = cl.lookup_cards(names, max_fallback=5)
    assert sent == names[:5]
    assert all(result[n] == {"name": n} for n in names[:5])
    assert all(result[n] == {"error": "not_found"} for n in names[5:])


def test_names_over_the_fallback_limit_are_not_cached_as_not_found(monkeypatch):
    cl, _ = _no_database(monkeypatch)
    monkeypatch.setattr(cl, "_card_cache", {})
    names = [f"Unknown {i}" for i in range(20)]
    cl.lookup_cards(names, max_fallback=5)
    assert all(n not in cl._card_cache for n in names[5:])


def test_max_fallback_none_sends_every_missing_name(monkeypatch):
    cl, sent = _no_database(monkeypatch)
    names = [f"Unknown {i}" for i in range(20)]
    cl.lookup_cards(names)
    assert sent == names


def test_max_fallback_zero_never_calls_scryfall(monkeypatch):
    cl, sent = _no_database(monkeypatch)
    result = cl.lookup_cards(["Unknown"], max_fallback=0)
    assert sent == []
    assert result == {"Unknown": {"error": "not_found"}}
