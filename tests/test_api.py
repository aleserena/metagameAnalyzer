"""API integration tests using FastAPI TestClient."""

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api.main as api_main
from api.main import app


@pytest.fixture(autouse=True)
def patch_decks(sample_decks):
    """Patch _decks before each API test."""
    original = api_main._decks
    api_main._decks = list(sample_decks)
    yield
    api_main._decks = original


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    """GET /api/v1/health returns ok."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_info(client):
    """GET /api/v1/info returns build_id and db_env."""
    r = client.get("/api/v1/info")
    assert r.status_code == 200
    data = r.json()
    assert "build_id" in data
    assert "db_env" in data
    assert data["build_id"] in ("dev",) or len(data["build_id"]) == 7
    assert data["db_env"] in ("dev", "staging", "prod", "postgres", "json")


def test_get_decks_pagination(client, sample_decks):
    """GET /api/v1/decks returns paginated results."""
    r = client.get("/api/v1/decks?skip=0&limit=1")
    assert r.status_code == 200
    data = r.json()
    assert "decks" in data
    assert len(data["decks"]) == 1
    assert data["total"] == 2
    assert data["skip"] == 0
    assert data["limit"] == 1


def test_get_decks_filter_event_id(client, sample_decks):
    """GET /api/v1/decks filters by event_id (single)."""
    event_id = sample_decks[0]["event_id"]
    r = client.get(f"/api/v1/decks?event_id={event_id}")
    assert r.status_code == 200
    data = r.json()
    assert all(d["event_id"] == event_id for d in data["decks"])


def test_get_decks_filter_event_ids(client, sample_decks):
    """GET /api/v1/decks filters by event_ids (multiple)."""
    ids = [d["event_id"] for d in sample_decks]
    event_ids = ",".join(str(i) for i in ids)
    r = client.get(f"/api/v1/decks?event_ids={event_ids}")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) == len(sample_decks)
    assert all(d["event_id"] in ids for d in data["decks"])


def test_get_decks_filter_deck_name(client, sample_decks):
    """GET /api/v1/decks filters by deck_name substring."""
    r = client.get("/api/v1/decks?deck_name=Spider")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    assert any("Spider" in (d.get("name") or "") for d in data["decks"])


def test_get_decks_filter_archetype(client, sample_decks):
    """GET /api/v1/decks filters by archetype substring."""
    r = client.get("/api/v1/decks?archetype=Aggro")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    assert any("Aggro" in (d.get("archetype") or "") for d in data["decks"])
    r2 = client.get("/api/v1/decks?archetype=Control")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["decks"]) >= 1
    assert any("Control" in (d.get("archetype") or "") for d in data2["decks"])


def test_get_decks_filter_player(client, sample_decks):
    """GET /api/v1/decks filters by player substring."""
    r = client.get("/api/v1/decks?player=Jeremy")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    assert any("Jeremy" in (d.get("player") or "") for d in data["decks"])


def test_get_decks_filter_player_ignores_accents(client, sample_decks):
    """GET /api/v1/decks?player=... matches player names accent-insensitive (e.g. matias finds Matías)."""
    # Add a deck with accented name so we have Matías in the list
    deck_matias = dict(sample_decks[0])
    deck_matias["deck_id"] = 999001
    deck_matias["player"] = "Matías"
    deck_matias["player_id"] = 101
    api_main._decks = list(sample_decks) + [deck_matias]
    r = client.get("/api/v1/decks?player=matias")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    assert any(d.get("player") == "Matías" for d in data["decks"])


def test_get_player_detail_ignores_accents(client, sample_decks):
    """GET /api/v1/players/{name} finds player by accent-insensitive name (e.g. matias finds Matías)."""
    deck_matias = dict(sample_decks[0])
    deck_matias["deck_id"] = 999002
    deck_matias["player"] = "Matías"
    deck_matias["player_id"] = 102
    api_main._decks = list(sample_decks) + [deck_matias]
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/matias")
    assert r.status_code == 200
    data = r.json()
    assert data["player"] == "Matías"
    assert data["player_id"] == 102


def test_get_decks_filter_player_id(client, sample_decks):
    """GET /api/v1/decks?player_id=X returns only decks for that player."""
    r = client.get("/api/v1/decks?player_id=1")
    assert r.status_code == 200
    data = r.json()
    assert all(d.get("player_id") == 1 for d in data["decks"])
    assert len(data["decks"]) == 1
    assert data["decks"][0]["player_id"] == 1
    r2 = client.get("/api/v1/decks?player_id=2")
    assert r2.status_code == 200
    data2 = r2.json()
    assert all(d.get("player_id") == 2 for d in data2["decks"])
    assert len(data2["decks"]) == 1


def test_get_decks_response_includes_player_id(client, sample_decks):
    """GET /api/v1/decks returns decks with player_id when present."""
    r = client.get("/api/v1/decks")
    assert r.status_code == 200
    data = r.json()
    for d in data["decks"]:
        assert "player_id" in d
    assert any(d.get("player_id") == 1 for d in data["decks"])
    assert any(d.get("player_id") == 2 for d in data["decks"])


def test_get_deck_detail_includes_player_id(client, sample_decks):
    """GET /api/v1/decks/{id} returns deck with player_id when present."""
    deck_id = sample_decks[0]["deck_id"]
    r = client.get(f"/api/v1/decks/{deck_id}")
    assert r.status_code == 200
    assert "player_id" in r.json()
    assert r.json()["player_id"] == 1


def test_get_decks_filter_card(client, sample_decks):
    """GET /api/v1/decks filters by card name (mainboard/sideboard/commanders)."""
    r = client.get("/api/v1/decks?card=Lightning")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    r2 = client.get("/api/v1/decks?card=Spider-Man")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["decks"]) >= 1


def test_get_deck_by_id_200(client, sample_decks):
    """GET /api/v1/decks/{id} returns 200 for existing deck."""
    deck_id = sample_decks[0]["deck_id"]
    r = client.get(f"/api/v1/decks/{deck_id}")
    assert r.status_code == 200
    assert r.json()["deck_id"] == deck_id


def test_get_deck_by_id_404(client):
    """GET /api/v1/decks/{id} returns 404 for non-existent deck."""
    r = client.get("/api/v1/decks/999999")
    assert r.status_code == 404


def test_get_archetype_detail_404(client):
    """GET /api/v1/archetypes/{name} returns 404 when no decks match."""
    r = client.get("/api/v1/archetypes/NonexistentArchetype")
    assert r.status_code == 404


def test_get_archetype_detail_200(client, sample_decks):
    """GET /api/v1/archetypes/{name} returns 200 with archetype, deck_count, average_analysis, top_cards_main."""
    archetype_name = sample_decks[0].get("archetype") or "UR Aggro"
    r = client.get(f"/api/v1/archetypes/{archetype_name}")
    assert r.status_code == 200
    data = r.json()
    assert data["archetype"] == archetype_name
    assert data["deck_count"] >= 1
    assert "average_analysis" in data
    a = data["average_analysis"]
    assert "mana_curve" in a
    assert "color_distribution" in a
    assert "lands_distribution" in a
    assert "type_distribution" in a
    assert "top_cards_main" in data
    assert isinstance(data["top_cards_main"], list)


def _trends_decks() -> list[dict]:
    """Build decks spanning multiple events/dates for card-trends tests.

    Archetype "Trend Deck":
      - Older (events 100, 101, 102; Jan–Feb) play OldCard heavily.
      - Recent (event 200; Apr) drops OldCard entirely and plays NewCard.
    """
    base = {
        "format_id": "EDH",
        "name": "Trend",
        "player_count": 8,
        "sideboard": [],
        "commanders": [],
        "archetype": "Trend Deck",
    }

    def mk(deck_id: int, event_id: int, date: str, mainboard: list[dict]) -> dict:
        return {
            **base,
            "deck_id": deck_id,
            "event_id": event_id,
            "date": date,
            "rank": "1",
            "player": f"P{deck_id}",
            "event_name": f"Event {event_id}",
            "mainboard": mainboard,
        }

    old_main = [
        {"qty": 4, "card": "OldCard"},
        {"qty": 4, "card": "StapleCard"},
    ]
    new_main = [
        {"qty": 4, "card": "NewCard"},
        {"qty": 4, "card": "StapleCard"},
    ]
    return [
        mk(1001, 100, "01/01/26", old_main),
        mk(1002, 100, "01/01/26", old_main),
        mk(1003, 101, "15/01/26", old_main),
        mk(1004, 101, "15/01/26", old_main),
        mk(1005, 102, "01/02/26", old_main),
        mk(1006, 102, "01/02/26", old_main),
        mk(1007, 200, "01/04/26", new_main),
        mk(1008, 200, "01/04/26", new_main),
    ]


def test_archetype_card_trends_events_mode(client):
    """recency_mode=events splits on last N distinct event IDs and flags new/legacy cards."""
    api_main._decks = _trends_decks()
    r = client.get(
        "/api/v1/archetypes/Trend%20Deck/card-trends",
        params={"recency_mode": "events", "recency_value": 1, "min_recent_play_rate": 50, "max_older_play_rate": 10},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["archetype"] == "Trend Deck"
    assert data["recent"]["event_count"] == 1
    assert data["recent"]["deck_count"] == 2
    assert data["older"]["event_count"] == 3
    assert data["older"]["deck_count"] == 6
    new_names = [c["card"] for c in data["new_cards"]]
    legacy_names = [c["card"] for c in data["legacy_cards"]]
    assert "NewCard" in new_names
    assert "OldCard" in legacy_names
    assert "StapleCard" not in new_names
    assert "StapleCard" not in legacy_names


def test_archetype_card_trends_days_mode(client):
    """recency_mode=days splits on date window."""
    api_main._decks = _trends_decks()
    r = client.get(
        "/api/v1/archetypes/Trend%20Deck/card-trends",
        params={"recency_mode": "days", "recency_value": 30, "min_recent_play_rate": 50, "max_older_play_rate": 10},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["recent"]["deck_count"] == 2  # only the April decks within 30 days of max
    assert data["older"]["deck_count"] == 6
    assert any(c["card"] == "NewCard" for c in data["new_cards"])
    assert any(c["card"] == "OldCard" for c in data["legacy_cards"])


def test_archetype_card_trends_ratio_mode(client):
    """recency_mode=ratio splits the chronologically-sorted decks by percentage."""
    api_main._decks = _trends_decks()
    r = client.get(
        "/api/v1/archetypes/Trend%20Deck/card-trends",
        params={"recency_mode": "ratio", "recency_value": 25, "min_recent_play_rate": 50, "max_older_play_rate": 10},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["recent"]["deck_count"] == 2  # ceil(8 * 0.25) = 2
    assert data["older"]["deck_count"] == 6
    assert any(c["card"] == "NewCard" for c in data["new_cards"])


def test_archetype_card_trends_custom_mode(client):
    """recency_mode=custom uses recent_from date."""
    api_main._decks = _trends_decks()
    r = client.get(
        "/api/v1/archetypes/Trend%20Deck/card-trends",
        params={"recency_mode": "custom", "recent_from": "01/03/26", "min_recent_play_rate": 50, "max_older_play_rate": 10},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["recent"]["deck_count"] == 2
    assert data["older"]["deck_count"] == 6


def test_archetype_card_trends_custom_requires_dates(client):
    """recency_mode=custom without recent_from or recent_to returns 400."""
    api_main._decks = _trends_decks()
    r = client.get(
        "/api/v1/archetypes/Trend%20Deck/card-trends",
        params={"recency_mode": "custom"},
    )
    assert r.status_code == 400


def test_archetype_card_trends_empty_older_warning(client):
    """When recency covers all events, the response includes a warning and empty legacy list."""
    api_main._decks = _trends_decks()
    r = client.get(
        "/api/v1/archetypes/Trend%20Deck/card-trends",
        params={"recency_mode": "events", "recency_value": 99},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["older"]["deck_count"] == 0
    assert data["warning"]
    assert data["legacy_cards"] == []


def test_archetype_card_trends_unknown_404(client):
    """Unknown archetype returns 404."""
    r = client.get(
        "/api/v1/archetypes/NonExistentArchetype/card-trends",
        params={"recency_mode": "events", "recency_value": 3},
    )
    assert r.status_code == 404


def test_archetype_detail_includes_top_players_and_typical_list(client):
    """GET /api/v1/archetypes/{name} now includes top_players and typical_list buckets."""
    api_main._decks = _trends_decks()
    r = client.get("/api/v1/archetypes/Trend%20Deck")
    assert r.status_code == 200
    data = r.json()
    assert "top_players" in data
    assert isinstance(data["top_players"], list)
    # 8 distinct players across trend decks
    assert len(data["top_players"]) >= 1
    assert all("player" in p and "deck_count" in p for p in data["top_players"])
    assert "typical_list" in data
    tl = data["typical_list"]
    assert set(tl.keys()) == {"core", "staple", "flex", "tech"}
    # StapleCard is in 100% of decks at 4 copies -> should land in core
    core_cards = [e["card"] for e in tl["core"]]
    assert "StapleCard" in core_cards


def test_archetype_detail_mana_pips_by_color(client):
    """average_analysis.mana_pips_by_color is present and parses colored pips correctly."""
    decks = [{
        "deck_id": 2001,
        "event_id": 300,
        "date": "10/03/26",
        "rank": "1",
        "player": "MP1",
        "event_name": "Pip Event",
        "format_id": "EDH",
        "name": "Pip Test",
        "player_count": 8,
        "sideboard": [],
        "commanders": [],
        "archetype": "Pip Deck",
        "mainboard": [
            {"qty": 4, "card": "Lightning Bolt"},
            {"qty": 4, "card": "Counterspell"},
            {"qty": 20, "card": "Mountain"},
        ],
    }]
    api_main._decks = decks

    def fake_lookup(names):
        meta = {
            "Lightning Bolt": {"name": "Lightning Bolt", "mana_cost": "{R}", "cmc": 1, "type_line": "Instant", "colors": ["R"], "color_identity": ["R"]},
            "Counterspell": {"name": "Counterspell", "mana_cost": "{U}{U}", "cmc": 2, "type_line": "Instant", "colors": ["U"], "color_identity": ["U"]},
            "Mountain": {"name": "Mountain", "mana_cost": "", "cmc": 0, "type_line": "Basic Land — Mountain", "colors": [], "color_identity": ["R"]},
        }
        return {n: meta.get(n, {}) for n in names}

    with patch("api.main.lookup_cards", side_effect=fake_lookup):
        r = client.get("/api/v1/archetypes/Pip%20Deck")
    assert r.status_code == 200
    pips = r.json()["average_analysis"]["mana_pips_by_color"]
    # 4 bolts = 4 red pips, 4 counterspells = 8 blue pips, Mountain is land (ignored)
    assert pips["R"] == 4.0
    assert pips["U"] == 8.0
    assert pips["W"] == 0.0


def test_archetype_weekly_stats_basic(client):
    """weekly-stats returns one row per ISO week with archetype and global counts."""
    api_main._decks = _trends_decks()
    r = client.get("/api/v1/archetypes/Trend%20Deck/weekly-stats")
    assert r.status_code == 200
    data = r.json()
    assert data["archetype"] == "Trend Deck"
    weeks = data["weeks"]
    assert len(weeks) >= 3
    assert all({"week", "week_start", "archetype_decks", "total_decks", "share_pct", "top8_rate_pct"}.issubset(w.keys()) for w in weeks)
    # All decks are this archetype, so share should be 100% in every week.
    for w in weeks:
        assert w["share_pct"] == 100.0
        assert w["archetype_decks"] == w["total_decks"]
    # Totals across weeks equal total deck count.
    assert sum(w["archetype_decks"] for w in weeks) == 8


def test_archetype_weekly_stats_unknown_404(client):
    """Unknown archetype returns 404."""
    r = client.get("/api/v1/archetypes/NonExistentArchetype/weekly-stats")
    assert r.status_code == 404


def test_get_metagame_structure(client):
    """GET /api/v1/metagame returns structure with top_cards_main, commander_distribution."""
    r = client.get("/api/v1/metagame")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "commander_distribution" in data
    assert "top_cards_main" in data
    assert data["summary"]["total_decks"] == 2


def test_get_players_leaderboard(client):
    """GET /api/v1/players returns leaderboard."""
    r = client.get("/api/v1/players")
    assert r.status_code == 200
    data = r.json()
    assert "players" in data
    assert len(data["players"]) == 2


def test_post_cards_lookup(client):
    """POST /api/v1/cards/lookup returns card metadata (uses real lookup or mock)."""
    r = client.post("/api/v1/cards/lookup", json={"names": ["Lightning Bolt"]})
    assert r.status_code == 200
    # May return {} if no network, or Scryfall data if available
    data = r.json()
    assert isinstance(data, dict)


def test_get_cards_search(client):
    """GET /api/v1/cards/search returns autocomplete results."""
    with patch.object(api_main, "autocomplete_cards", return_value=["Atraxa, Praetors' Voice", "Atraxa, Grand Unifier"]):
        r = client.get("/api/v1/cards/search?q=Atra")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert data["data"] == ["Atraxa, Praetors' Voice", "Atraxa, Grand Unifier"]


def test_get_cards_search_short_query(client):
    """GET /api/v1/cards/search returns empty list for query shorter than min length."""
    with patch.object(api_main, "autocomplete_cards", return_value=[]) as mock_autocomplete:
        r = client.get("/api/v1/cards/search?q=A")
    assert r.status_code == 200
    data = r.json()
    assert data.get("data") == []
    mock_autocomplete.assert_called_once_with("A")


# --- Read-only public: date-range, format-info, decks compare/similar/analysis/duplicates ---


def test_get_date_range(client, sample_decks):
    """GET /api/v1/date-range returns min_date, max_date, last_event_date from decks."""
    r = client.get("/api/v1/date-range")
    assert r.status_code == 200
    data = r.json()
    assert "min_date" in data
    assert "max_date" in data
    assert "last_event_date" in data
    assert data["min_date"] == data["max_date"] == "15/02/26"


def test_get_date_range_empty(client):
    """GET /api/v1/date-range returns nulls when no decks."""
    api_main._decks = []
    r = client.get("/api/v1/date-range")
    assert r.status_code == 200
    assert r.json() == {"min_date": None, "max_date": None, "last_event_date": None}
    # patch_decks (autouse) restores _decks for next test


def test_get_format_info(client, sample_decks):
    """GET /api/v1/format-info returns format_id and format_name from decks."""
    r = client.get("/api/v1/format-info")
    assert r.status_code == 200
    data = r.json()
    assert data["format_id"] == "EDH"
    assert "format_name" in data


def test_get_decks_compare(client, sample_decks):
    """GET /api/v1/decks/compare returns 2–4 decks by id."""
    ids = [sample_decks[0]["deck_id"], sample_decks[1]["deck_id"]]
    r = client.get(f"/api/v1/decks/compare?ids={ids[0]},{ids[1]}")
    assert r.status_code == 200
    data = r.json()
    assert "decks" in data
    assert len(data["decks"]) == 2
    assert {d["deck_id"] for d in data["decks"]} == set(ids)


def test_get_decks_compare_400(client):
    """GET /api/v1/decks/compare requires 2–4 ids."""
    r = client.get("/api/v1/decks/compare?ids=1")
    assert r.status_code == 400
    r2 = client.get("/api/v1/decks/compare?ids=1,2,3,4,5")
    assert r2.status_code == 400


def test_get_decks_duplicates(client, sample_decks):
    """GET /api/v1/decks/duplicates returns list of duplicate groups."""
    r = client.get("/api/v1/decks/duplicates")
    assert r.status_code == 200
    data = r.json()
    assert "duplicates" in data
    assert isinstance(data["duplicates"], list)


def test_get_deck_similar(client, sample_decks):
    """GET /api/v1/decks/{id}/similar returns similar decks."""
    deck_id = sample_decks[0]["deck_id"]
    r = client.get(f"/api/v1/decks/{deck_id}/similar?limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "similar" in data
    assert isinstance(data["similar"], list)


def test_get_deck_similar_404(client):
    """GET /api/v1/decks/{id}/similar returns 404 for unknown deck."""
    r = client.get("/api/v1/decks/999999/similar")
    assert r.status_code == 404


def test_get_deck_analysis(client, sample_decks):
    """GET /api/v1/decks/{id}/analysis returns deck analysis."""
    deck_id = sample_decks[0]["deck_id"]
    r = client.get(f"/api/v1/decks/{deck_id}/analysis")
    assert r.status_code == 200
    data = r.json()
    assert "mana_curve" in data
    assert "color_distribution" in data
    assert "lands_distribution" in data
    assert "type_distribution" in data


def test_get_deck_analysis_404(client):
    """GET /api/v1/decks/{id}/analysis returns 404 for unknown deck."""
    r = client.get("/api/v1/decks/999999/analysis")
    assert r.status_code == 404


# --- Auth ---


def test_auth_login_success(client):
    """POST /api/v1/auth/login returns token when password matches."""
    with patch.dict("os.environ", {"ADMIN_PASSWORD": "secret"}):
        with patch.object(api_main, "ADMIN_PASSWORD", "secret"):
            r = client.post("/api/v1/auth/login", json={"password": "secret"})
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data.get("user") == "admin"


def test_auth_login_invalid(client):
    """POST /api/v1/auth/login returns 401 for wrong password."""
    with patch.object(api_main, "ADMIN_PASSWORD", "secret"):
        r = client.post("/api/v1/auth/login", json={"password": "wrong"})
    assert r.status_code == 401


def test_auth_me_401_no_header(client):
    """GET /api/v1/auth/me returns 401 without Authorization header."""
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_auth_me_200(client):
    """GET /api/v1/auth/me returns user when valid token provided."""
    with patch.dict("os.environ", {"ADMIN_PASSWORD": "secret"}, clear=False):
        with patch.object(api_main, "ADMIN_PASSWORD", "secret"):
            login_r = client.post("/api/v1/auth/login", json={"password": "secret"})
        token = login_r.json()["token"]
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"user": "admin"}


# --- Settings (no DB): use client_with_overrides and mock service where needed ---


def test_get_settings_ignore_lands_cards(client_with_overrides):
    """GET /api/v1/settings/ignore-lands-cards returns cards list (admin)."""
    with patch.object(api_main.settings_service, "get_ignore_lands_cards", return_value=["Forest", "Swamp"]):
        r = client_with_overrides.get("/api/v1/settings/ignore-lands-cards")
    assert r.status_code == 200
    assert r.json() == {"cards": ["Forest", "Swamp"]}


def test_put_settings_ignore_lands_cards(client_with_overrides):
    """PUT /api/v1/settings/ignore-lands-cards updates and returns cards (admin)."""
    with patch.object(api_main.settings_service, "set_ignore_lands_cards", return_value=["Island", "Mountain"]):
        r = client_with_overrides.put("/api/v1/settings/ignore-lands-cards", json={"cards": ["Island", "Mountain"]})
    assert r.status_code == 200
    assert r.json() == {"cards": ["Island", "Mountain"]}


def test_get_settings_rank_weights(client_with_overrides):
    """GET /api/v1/settings/rank-weights returns weights (admin)."""
    with patch.object(api_main.settings_service, "get_rank_weights", return_value={"1": 10.0, "2": 8.0}):
        r = client_with_overrides.get("/api/v1/settings/rank-weights")
    assert r.status_code == 200
    assert r.json() == {"weights": {"1": 10.0, "2": 8.0}}


def test_put_settings_rank_weights(client_with_overrides):
    """PUT /api/v1/settings/rank-weights updates and returns weights (admin)."""
    with patch.object(api_main.settings_service, "set_rank_weights", return_value={"1": 10.0}):
        r = client_with_overrides.put("/api/v1/settings/rank-weights", json={"weights": {"1": 10.0}})
    assert r.status_code == 200
    assert r.json() == {"weights": {"1": 10.0}}


def test_post_settings_clear_cache(client_with_overrides):
    """POST /api/v1/settings/clear-cache clears Scryfall cache (admin)."""
    with patch.object(api_main, "clear_scryfall_cache"):
        r = client_with_overrides.post("/api/v1/settings/clear-cache")
    assert r.status_code == 200
    assert "message" in r.json()


# --- Players / aliases (no DB required for GET) ---


def test_get_player_aliases(client):
    """GET /api/v1/player-aliases returns alias map."""
    r = client.get("/api/v1/player-aliases")
    assert r.status_code == 200
    assert "aliases" in r.json()
    assert isinstance(r.json()["aliases"], dict)


def test_get_players_with_date_filter(client, sample_decks):
    """GET /api/v1/players accepts date_from/date_to."""
    r = client.get("/api/v1/players?date_from=01/01/26&date_to=31/12/26")
    assert r.status_code == 200
    assert "players" in r.json()


def test_get_player_detail(client, sample_decks):
    """GET /api/v1/players/{name} returns player stats and decks."""
    player = sample_decks[0]["player"]
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get(f"/api/v1/players/{player}")
    assert r.status_code == 200
    data = r.json()
    assert data["player"]
    assert "decks" in data
    assert "wins" in data
    assert "points" in data


def test_get_player_detail_404(client):
    """GET /api/v1/players/{name} returns 404 for unknown player."""
    r = client.get("/api/v1/players/NonexistentPlayer123")
    assert r.status_code == 404


def test_get_players_similar(client, sample_decks):
    """GET /api/v1/players/similar returns similar name suggestions."""
    r = client.get("/api/v1/players/similar?name=Jeremy&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "similar" in data
    assert isinstance(data["similar"], list)


# --- Metagame with query params ---


def test_get_metagame_with_date_params(client, sample_decks):
    """GET /api/v1/metagame accepts date_from, date_to and returns expected shape."""
    r = client.get("/api/v1/metagame?date_from=01/01/26&date_to=31/12/26")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "commander_distribution" in data
    assert "top_cards_main" in data


# --- Events (with _database_available mocked so we use in-memory _decks) ---


def test_get_events_list(client, sample_decks):
    """GET /api/v1/events returns events derived from decks when DB not used."""
    api_main._events_cache = None
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/events")
    assert r.status_code == 200
    data = r.json()
    assert "events" in data
    assert isinstance(data["events"], list)
    assert len(data["events"]) >= 1
    ev = data["events"][0]
    assert "event_id" in ev
    assert "event_name" in ev
    assert ev.get("event_id") == sample_decks[0]["event_id"]


def test_get_event_by_id(client, sample_decks):
    """GET /api/v1/events/{event_id} returns event when found from decks."""
    event_id = sample_decks[0]["event_id"]
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get(f"/api/v1/events/{event_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["event_id"] == event_id
    assert "event_name" in data
    assert "date" in data


def test_get_event_by_id_404(client):
    """GET /api/v1/events/{event_id} returns 404 when event not found."""
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/events/99999999")
    assert r.status_code == 404


# --- Matchups (with client_with_overrides and mocked DB) ---


def test_get_matchups_summary(client_with_overrides):
    """GET /api/v1/matchups/summary returns structure when DB is mocked."""
    @contextmanager
    def mock_session_scope():
        yield None

    with patch.object(api_main, "_db") as mock_db:
        mock_db.session_scope = mock_session_scope
        mock_db.list_matchups_with_deck_info.return_value = []
        r = client_with_overrides.get("/api/v1/matchups/summary")
    assert r.status_code == 200
    data = r.json()
    assert "list" in data and "matrix" in data and "min_matches" in data
    assert data["min_matches"] == 0
    assert data.get("include_opponents_below_min") is False
    r2 = client_with_overrides.get("/api/v1/matchups/summary?min_matches=3")
    assert r2.status_code == 200
    assert r2.json()["min_matches"] == 3
    r3 = client_with_overrides.get(
        "/api/v1/matchups/summary?min_matches=3&include_opponents_below_min=true"
    )
    assert r3.status_code == 200
    assert r3.json()["include_opponents_below_min"] is True


# --- POST /api/v1/load ---


def test_post_load_from_path_json(client_with_overrides, sample_deck_dict, tmp_path, monkeypatch):
    """JSON body with only path loads file under DATA_DIR (in-memory when DB off)."""
    monkeypatch.setattr(api_main, "DATA_DIR", tmp_path)
    (tmp_path / "import.json").write_text(json.dumps([sample_deck_dict]), encoding="utf-8")
    with patch.object(api_main, "_database_available", return_value=False):
        r = client_with_overrides.post("/api/v1/load", json={"path": "import.json"})
    assert r.status_code == 200
    assert r.json()["loaded"] == 1
    assert api_main._decks[0]["deck_id"] == sample_deck_dict["deck_id"]


def test_post_load_path_wins_over_inline_decks(client_with_overrides, sample_deck_dict, sample_decks, tmp_path, monkeypatch):
    """Non-empty path is applied before inline decks when both are sent."""
    monkeypatch.setattr(api_main, "DATA_DIR", tmp_path)
    (tmp_path / "one.json").write_text(json.dumps([sample_deck_dict]), encoding="utf-8")
    with patch.object(api_main, "_database_available", return_value=False):
        r = client_with_overrides.post(
            "/api/v1/load",
            json={"path": "one.json", "decks": sample_decks},
        )
    assert r.status_code == 200
    assert r.json()["loaded"] == 1
    assert api_main._decks[0]["deck_id"] == sample_deck_dict["deck_id"]


def test_post_load_rejects_path_traversal(client_with_overrides, tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "DATA_DIR", tmp_path)
    r = client_with_overrides.post("/api/v1/load", json={"path": "../outside.json"})
    assert r.status_code == 400


def test_post_load_rejects_absolute_path(client_with_overrides, tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "DATA_DIR", tmp_path)
    r = client_with_overrides.post("/api/v1/load", json={"path": str(tmp_path / "x.json")})
    assert r.status_code == 400


def test_post_load_empty_body_400(client_with_overrides):
    r = client_with_overrides.post("/api/v1/load", json={})
    assert r.status_code == 400


def test_post_load_inline_decks_attaches_event_id(client_with_overrides, sample_deck_dict):
    """event_id on LoadBody is applied when DB is available (mocked)."""
    ev = SimpleNamespace(event_id="m42", name="Linked Event", date="03/03/25", format_id="EDH")

    @contextmanager
    def session_scope():
        yield MagicMock()

    deck = dict(sample_deck_dict)
    deck["deck_id"] = None
    with patch.object(api_main, "_database_available", return_value=True):
        with patch.object(api_main, "_persist_decks_to_db"):
            with patch.object(api_main, "_db") as mock_db:
                mock_db.session_scope = session_scope
                mock_db.get_event = MagicMock(return_value=ev)
                mock_db.next_manual_deck_id.return_value = 2_000_500
                mock_db.ORIGIN_MANUAL = "manual"
                mock_db.ORIGIN_MTGTOP8 = "mtgtop8"
                mock_db.MANUAL_DECK_ID_START = 2_000_000
                r = client_with_overrides.post(
                    "/api/v1/load",
                    json={"decks": [deck], "event_id": "m42"},
                )
    assert r.status_code == 200
    assert api_main._decks[0]["event_id"] == "m42"
    assert api_main._decks[0]["event_name"] == "Linked Event"
    assert api_main._decks[0]["deck_id"] == 2_000_500


def test_post_load_new_event_creates_and_attaches(client_with_overrides, sample_deck_dict):
    row = SimpleNamespace(event_id="m1", name="Fresh", date="04/04/25", format_id="EDH")

    @contextmanager
    def session_scope():
        yield MagicMock()

    deck = dict(sample_deck_dict)
    deck["deck_id"] = 99
    with patch.object(api_main, "_database_available", return_value=True):
        with patch.object(api_main, "_persist_decks_to_db"):
            with patch.object(api_main, "_db") as mock_db:
                mock_db.session_scope = session_scope
                mock_db.create_event = MagicMock(return_value=row)
                mock_db.next_manual_deck_id.return_value = 2_000_600
                mock_db.ORIGIN_MANUAL = "manual"
                mock_db.ORIGIN_MTGTOP8 = "mtgtop8"
                mock_db.MANUAL_DECK_ID_START = 2_000_000
                r = client_with_overrides.post(
                    "/api/v1/load",
                    json={
                        "decks": [deck],
                        "new_event": {"event_name": "Fresh", "date": "04/04/25", "format_id": "EDH"},
                    },
                )
    assert r.status_code == 200
    assert api_main._decks[0]["event_id"] == "m1"
    assert api_main._decks[0]["event_name"] == "Fresh"
    assert api_main._decks[0]["deck_id"] == 2_000_600


# ---------- Player analysis endpoint ---------------------------------------


def _analysis_fixture_decks():
    """Decks for analysis tests: one player with 3 events across time, plus opponents."""
    return [
        {
            "deck_id": 100001, "event_id": 5001, "format_id": "LE", "name": "Target 1",
            "player": "Target", "player_id": 9001,
            "event_name": "Event A", "date": "01/01/25", "rank": "1", "player_count": 32,
            "mainboard": [{"qty": 4, "card": "Lightning Bolt"}, {"qty": 20, "card": "Mountain"}],
            "sideboard": [], "commanders": [], "archetype": "Red Aggro",
        },
        {
            "deck_id": 100002, "event_id": 5002, "format_id": "LE", "name": "Target 2",
            "player": "Target", "player_id": 9001,
            "event_name": "Event B", "date": "15/02/25", "rank": "3-4", "player_count": 64,
            "mainboard": [{"qty": 4, "card": "Lightning Bolt"}, {"qty": 2, "card": "Goblin Guide"}, {"qty": 20, "card": "Mountain"}],
            "sideboard": [], "commanders": [], "archetype": "Red Aggro",
        },
        {
            "deck_id": 100003, "event_id": 5003, "format_id": "MO", "name": "Target 3",
            "player": "Target", "player_id": 9001,
            "event_name": "Event C", "date": "20/03/25", "rank": "5-8", "player_count": 128,
            "mainboard": [{"qty": 4, "card": "Counterspell"}, {"qty": 20, "card": "Island"}],
            "sideboard": [], "commanders": [], "archetype": "UW Control",
        },
        {
            "deck_id": 100010, "event_id": 5001, "format_id": "LE", "name": "Opp 1",
            "player": "Rival", "player_id": 9002,
            "event_name": "Event A", "date": "01/01/25", "rank": "2", "player_count": 32,
            "mainboard": [{"qty": 20, "card": "Plains"}], "sideboard": [],
            "commanders": [], "archetype": "UW Control",
        },
    ]


def test_player_analysis_by_id_shape(client):
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/id/9001/analysis")
    assert r.status_code == 200
    data = r.json()
    assert data["player"] == "Target"
    assert data["player_id"] == 9001
    # Required top-level keys
    for key in (
        "per_event", "leaderboard_history", "archetype_distribution",
        "archetype_performance", "color_distribution", "color_count_distribution",
        "format_distribution", "commander_distribution", "average_mana_curve",
        "top_cards", "pet_cards", "field_size_buckets", "metagame_comparison",
        "highlights",
    ):
        assert key in data, f"missing key {key}"
    assert len(data["per_event"]) == 3
    # per_event is sorted by date ascending
    dates = [e["date"] for e in data["per_event"]]
    assert dates == ["01/01/25", "15/02/25", "20/03/25"]


def test_player_analysis_leaderboard_history_chronological(client):
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/id/9001/analysis")
    assert r.status_code == 200
    hist = r.json()["leaderboard_history"]
    assert len(hist) == 3  # one snapshot per target event date
    # Dates in ascending order
    keys = [p["date"] for p in hist]
    assert keys == sorted(keys, key=lambda s: s.split("/")[::-1])
    # After first event (win with 8pts), target is #1
    assert hist[0]["rank"] == 1
    assert hist[0]["total_players"] >= 2


def test_player_analysis_archetype_performance(client):
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/id/9001/analysis")
    assert r.status_code == 200
    rows = r.json()["archetype_performance"]
    red = next(row for row in rows if row["archetype"] == "Red Aggro")
    assert red["count"] == 2
    assert red["win_pct"] == 50.0  # 1 win of 2
    assert red["top8_pct"] == 100.0  # 1 and 3-4 both top-8
    assert red["best_finish"] == "1"


def test_player_analysis_highlights_streak_and_field_win(client):
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/id/9001/analysis")
    h = r.json()["highlights"]
    assert h["total_events"] == 3
    assert h["longest_top8_streak"] == 3  # all three decks are top-8
    assert h["biggest_field_win"] == 32
    assert h["best_finish"] == "1"
    assert h["first_event_date"] == "01/01/25"
    assert h["last_event_date"] == "20/03/25"


def test_player_analysis_format_and_color_count(client):
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/id/9001/analysis")
    data = r.json()
    # Two decks in LE, one in MO
    by_fmt = {row["format_id"]: row["count"] for row in data["format_distribution"]}
    assert by_fmt["LE"] == 2
    assert by_fmt["MO"] == 1
    # Color count distribution has three decks across buckets
    assert sum(data["color_count_distribution"].values()) == 3
    # Commander distribution is empty for non-EDH player
    assert data["commander_distribution"] == []


def test_player_analysis_by_name(client):
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/Target/analysis")
    assert r.status_code == 200
    assert r.json()["player"] == "Target"


def test_player_analysis_404(client):
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/id/99999/analysis")
    assert r.status_code == 404


def test_player_analysis_top_cards_excludes_basics(client):
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/id/9001/analysis")
    cards = {c["card"] for c in r.json()["top_cards"]}
    assert "Mountain" not in cards
    assert "Island" not in cards
    assert "Plains" not in cards


def test_player_analysis_accepts_string_event_id(client):
    """Manually-created events use string IDs like 'm1'; response must serialize cleanly."""
    decks = _analysis_fixture_decks()
    manual_deck = {
        "deck_id": 100099, "event_id": "m1", "format_id": "LE", "name": "Manual",
        "player": "Target", "player_id": 9001,
        "event_name": "Manual Event", "date": "05/04/25", "rank": "1", "player_count": 16,
        "mainboard": [{"qty": 4, "card": "Lightning Bolt"}],
        "sideboard": [], "commanders": [], "archetype": "Red Aggro",
    }
    api_main._decks = decks + [manual_deck]
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/id/9001/analysis")
    assert r.status_code == 200
    event_ids = [e["event_id"] for e in r.json()["per_event"]]
    assert "m1" in event_ids


def test_player_detail_by_id_respects_date_range(client):
    """/players/id/{id} stats and decks list are filtered to the date window."""
    api_main._decks = _analysis_fixture_decks()
    # Narrow to just Feb 2025 (only one of the three decks -> Event B / 15/02/25)
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/id/9001?date_from=01/02/25&date_to=28/02/25")
    assert r.status_code == 200
    data = r.json()
    assert data["player_id"] == 9001
    assert data["deck_count"] == 1
    dates = [d["date"] for d in data["decks"]]
    assert dates == ["15/02/25"]
    # Top-8 count matches the single in-range deck (rank 3-4)
    assert data["top8"] == 1
    assert data["top2"] == 0
    assert data["wins"] == 0


def test_player_detail_by_name_respects_date_range(client):
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/Target?date_from=01/03/25&date_to=31/03/25")
    assert r.status_code == 200
    data = r.json()
    assert data["deck_count"] == 1
    assert [d["date"] for d in data["decks"]] == ["20/03/25"]


def test_player_detail_existing_player_empty_window_returns_zeros(client):
    """When a known player has no decks in the window, return zero stats (not 404)."""
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/v1/players/id/9001?date_from=01/01/30&date_to=31/12/30")
    assert r.status_code == 200
    data = r.json()
    assert data["player_id"] == 9001
    assert data["deck_count"] == 0
    assert data["wins"] == 0 and data["top8"] == 0
    assert data["decks"] == []


def test_player_analysis_respects_date_range(client):
    """Analysis endpoint filters per_event and leaderboard history to the window."""
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get(
            "/api/v1/players/id/9001/analysis?date_from=01/02/25&date_to=31/03/25"
        )
    assert r.status_code == 200
    data = r.json()
    dates = [e["date"] for e in data["per_event"]]
    assert dates == ["15/02/25", "20/03/25"]
    # Leaderboard history is recomputed over filtered window (one snapshot per player's event date)
    lb_dates = [p["date"] for p in data["leaderboard_history"]]
    assert lb_dates == ["15/02/25", "20/03/25"]


def test_player_analysis_date_range_empty_window(client):
    """Known player with no decks in window still returns a valid (empty) analysis shape."""
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get(
            "/api/v1/players/id/9001/analysis?date_from=01/01/30&date_to=31/12/30"
        )
    assert r.status_code == 200
    data = r.json()
    assert data["per_event"] == []
    assert data["leaderboard_history"] == []
    assert data["archetype_distribution"] == []


def test_player_analysis_by_name_date_range(client):
    api_main._decks = _analysis_fixture_decks()
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get(
            "/api/v1/players/Target/analysis?date_from=01/03/25&date_to=31/03/25"
        )
    assert r.status_code == 200
    assert [e["date"] for e in r.json()["per_event"]] == ["20/03/25"]
