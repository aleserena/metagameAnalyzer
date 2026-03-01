"""API integration tests using FastAPI TestClient."""

import sys
from pathlib import Path
from unittest.mock import patch

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
    """GET /api/health returns ok."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_get_decks_pagination(client, sample_decks):
    """GET /api/decks returns paginated results."""
    r = client.get("/api/decks?skip=0&limit=1")
    assert r.status_code == 200
    data = r.json()
    assert "decks" in data
    assert len(data["decks"]) == 1
    assert data["total"] == 2
    assert data["skip"] == 0
    assert data["limit"] == 1


def test_get_decks_filter_event_id(client, sample_decks):
    """GET /api/decks filters by event_id (single)."""
    event_id = sample_decks[0]["event_id"]
    r = client.get(f"/api/decks?event_id={event_id}")
    assert r.status_code == 200
    data = r.json()
    assert all(d["event_id"] == event_id for d in data["decks"])


def test_get_decks_filter_event_ids(client, sample_decks):
    """GET /api/decks filters by event_ids (multiple)."""
    ids = [d["event_id"] for d in sample_decks]
    event_ids = ",".join(str(i) for i in ids)
    r = client.get(f"/api/decks?event_ids={event_ids}")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) == len(sample_decks)
    assert all(d["event_id"] in ids for d in data["decks"])


def test_get_decks_filter_deck_name(client, sample_decks):
    """GET /api/decks filters by deck_name substring."""
    r = client.get("/api/decks?deck_name=Spider")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    assert any("Spider" in (d.get("name") or "") for d in data["decks"])


def test_get_decks_filter_archetype(client, sample_decks):
    """GET /api/decks filters by archetype substring."""
    r = client.get("/api/decks?archetype=Aggro")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    assert any("Aggro" in (d.get("archetype") or "") for d in data["decks"])
    r2 = client.get("/api/decks?archetype=Control")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["decks"]) >= 1
    assert any("Control" in (d.get("archetype") or "") for d in data2["decks"])


def test_get_decks_filter_player(client, sample_decks):
    """GET /api/decks filters by player substring."""
    r = client.get("/api/decks?player=Jeremy")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    assert any("Jeremy" in (d.get("player") or "") for d in data["decks"])


def test_get_decks_filter_player_ignores_accents(client, sample_decks):
    """GET /api/decks?player=... matches player names accent-insensitive (e.g. matias finds Matías)."""
    # Add a deck with accented name so we have Matías in the list
    deck_matias = dict(sample_decks[0])
    deck_matias["deck_id"] = 999001
    deck_matias["player"] = "Matías"
    deck_matias["player_id"] = 101
    api_main._decks = list(sample_decks) + [deck_matias]
    r = client.get("/api/decks?player=matias")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    assert any(d.get("player") == "Matías" for d in data["decks"])


def test_get_player_detail_ignores_accents(client, sample_decks):
    """GET /api/players/{name} finds player by accent-insensitive name (e.g. matias finds Matías)."""
    deck_matias = dict(sample_decks[0])
    deck_matias["deck_id"] = 999002
    deck_matias["player"] = "Matías"
    deck_matias["player_id"] = 102
    api_main._decks = list(sample_decks) + [deck_matias]
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/players/matias")
    assert r.status_code == 200
    data = r.json()
    assert data["player"] == "Matías"
    assert data["player_id"] == 102


def test_get_decks_filter_player_id(client, sample_decks):
    """GET /api/decks?player_id=X returns only decks for that player."""
    r = client.get("/api/decks?player_id=1")
    assert r.status_code == 200
    data = r.json()
    assert all(d.get("player_id") == 1 for d in data["decks"])
    assert len(data["decks"]) == 1
    assert data["decks"][0]["player_id"] == 1
    r2 = client.get("/api/decks?player_id=2")
    assert r2.status_code == 200
    data2 = r2.json()
    assert all(d.get("player_id") == 2 for d in data2["decks"])
    assert len(data2["decks"]) == 1


def test_get_decks_response_includes_player_id(client, sample_decks):
    """GET /api/decks returns decks with player_id when present."""
    r = client.get("/api/decks")
    assert r.status_code == 200
    data = r.json()
    for d in data["decks"]:
        assert "player_id" in d
    assert any(d.get("player_id") == 1 for d in data["decks"])
    assert any(d.get("player_id") == 2 for d in data["decks"])


def test_get_deck_detail_includes_player_id(client, sample_decks):
    """GET /api/decks/{id} returns deck with player_id when present."""
    deck_id = sample_decks[0]["deck_id"]
    r = client.get(f"/api/decks/{deck_id}")
    assert r.status_code == 200
    assert "player_id" in r.json()
    assert r.json()["player_id"] == 1


def test_get_decks_filter_card(client, sample_decks):
    """GET /api/decks filters by card name (mainboard/sideboard/commanders)."""
    r = client.get("/api/decks?card=Lightning")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    r2 = client.get("/api/decks?card=Spider-Man")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["decks"]) >= 1


def test_get_deck_by_id_200(client, sample_decks):
    """GET /api/decks/{id} returns 200 for existing deck."""
    deck_id = sample_decks[0]["deck_id"]
    r = client.get(f"/api/decks/{deck_id}")
    assert r.status_code == 200
    assert r.json()["deck_id"] == deck_id


def test_get_deck_by_id_404(client):
    """GET /api/decks/{id} returns 404 for non-existent deck."""
    r = client.get("/api/decks/999999")
    assert r.status_code == 404


def test_get_archetype_detail_404(client):
    """GET /api/archetypes/{name} returns 404 when no decks match."""
    r = client.get("/api/archetypes/NonexistentArchetype")
    assert r.status_code == 404


def test_get_archetype_detail_200(client, sample_decks):
    """GET /api/archetypes/{name} returns 200 with archetype, deck_count, average_analysis, top_cards_main."""
    archetype_name = sample_decks[0].get("archetype") or "UR Aggro"
    r = client.get(f"/api/archetypes/{archetype_name}")
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


def test_get_metagame_structure(client):
    """GET /api/metagame returns structure with top_cards_main, commander_distribution."""
    r = client.get("/api/metagame")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "commander_distribution" in data
    assert "top_cards_main" in data
    assert data["summary"]["total_decks"] == 2


def test_get_players_leaderboard(client):
    """GET /api/players returns leaderboard."""
    r = client.get("/api/players")
    assert r.status_code == 200
    data = r.json()
    assert "players" in data
    assert len(data["players"]) == 2


def test_post_cards_lookup(client):
    """POST /api/cards/lookup returns card metadata (uses real lookup or mock)."""
    r = client.post("/api/cards/lookup", json={"names": ["Lightning Bolt"]})
    assert r.status_code == 200
    # May return {} if no network, or Scryfall data if available
    data = r.json()
    assert isinstance(data, dict)


def test_get_cards_search(client):
    """GET /api/cards/search returns autocomplete results."""
    with patch.object(api_main, "autocomplete_cards", return_value=["Atraxa, Praetors' Voice", "Atraxa, Grand Unifier"]):
        r = client.get("/api/cards/search?q=Atra")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert data["data"] == ["Atraxa, Praetors' Voice", "Atraxa, Grand Unifier"]


def test_get_cards_search_short_query(client):
    """GET /api/cards/search returns empty list for query shorter than min length."""
    with patch.object(api_main, "autocomplete_cards", return_value=[]) as mock_autocomplete:
        r = client.get("/api/cards/search?q=A")
    assert r.status_code == 200
    data = r.json()
    assert data.get("data") == []
    mock_autocomplete.assert_called_once_with("A")


# --- Read-only public: date-range, format-info, decks compare/similar/analysis/duplicates ---


def test_get_date_range(client, sample_decks):
    """GET /api/date-range returns min_date, max_date, last_event_date from decks."""
    r = client.get("/api/date-range")
    assert r.status_code == 200
    data = r.json()
    assert "min_date" in data
    assert "max_date" in data
    assert "last_event_date" in data
    assert data["min_date"] == data["max_date"] == "15/02/26"


def test_get_date_range_empty(client):
    """GET /api/date-range returns nulls when no decks."""
    api_main._decks = []
    r = client.get("/api/date-range")
    assert r.status_code == 200
    assert r.json() == {"min_date": None, "max_date": None, "last_event_date": None}
    # patch_decks (autouse) restores _decks for next test


def test_get_format_info(client, sample_decks):
    """GET /api/format-info returns format_id and format_name from decks."""
    r = client.get("/api/format-info")
    assert r.status_code == 200
    data = r.json()
    assert data["format_id"] == "EDH"
    assert "format_name" in data


def test_get_decks_compare(client, sample_decks):
    """GET /api/decks/compare returns 2–4 decks by id."""
    ids = [sample_decks[0]["deck_id"], sample_decks[1]["deck_id"]]
    r = client.get(f"/api/decks/compare?ids={ids[0]},{ids[1]}")
    assert r.status_code == 200
    data = r.json()
    assert "decks" in data
    assert len(data["decks"]) == 2
    assert {d["deck_id"] for d in data["decks"]} == set(ids)


def test_get_decks_compare_400(client):
    """GET /api/decks/compare requires 2–4 ids."""
    r = client.get("/api/decks/compare?ids=1")
    assert r.status_code == 400
    r2 = client.get("/api/decks/compare?ids=1,2,3,4,5")
    assert r2.status_code == 400


def test_get_decks_duplicates(client, sample_decks):
    """GET /api/decks/duplicates returns list of duplicate groups."""
    r = client.get("/api/decks/duplicates")
    assert r.status_code == 200
    data = r.json()
    assert "duplicates" in data
    assert isinstance(data["duplicates"], list)


def test_get_deck_similar(client, sample_decks):
    """GET /api/decks/{id}/similar returns similar decks."""
    deck_id = sample_decks[0]["deck_id"]
    r = client.get(f"/api/decks/{deck_id}/similar?limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "similar" in data
    assert isinstance(data["similar"], list)


def test_get_deck_similar_404(client):
    """GET /api/decks/{id}/similar returns 404 for unknown deck."""
    r = client.get("/api/decks/999999/similar")
    assert r.status_code == 404


def test_get_deck_analysis(client, sample_decks):
    """GET /api/decks/{id}/analysis returns deck analysis."""
    deck_id = sample_decks[0]["deck_id"]
    r = client.get(f"/api/decks/{deck_id}/analysis")
    assert r.status_code == 200
    data = r.json()
    assert "mana_curve" in data
    assert "color_distribution" in data
    assert "lands_distribution" in data
    assert "type_distribution" in data


def test_get_deck_analysis_404(client):
    """GET /api/decks/{id}/analysis returns 404 for unknown deck."""
    r = client.get("/api/decks/999999/analysis")
    assert r.status_code == 404


# --- Auth ---


def test_auth_login_success(client):
    """POST /api/auth/login returns token when password matches."""
    with patch.dict("os.environ", {"ADMIN_PASSWORD": "secret"}):
        with patch.object(api_main, "ADMIN_PASSWORD", "secret"):
            r = client.post("/api/auth/login", json={"password": "secret"})
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data.get("user") == "admin"


def test_auth_login_invalid(client):
    """POST /api/auth/login returns 401 for wrong password."""
    with patch.object(api_main, "ADMIN_PASSWORD", "secret"):
        r = client.post("/api/auth/login", json={"password": "wrong"})
    assert r.status_code == 401


def test_auth_me_401_no_header(client):
    """GET /api/auth/me returns 401 without Authorization header."""
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_auth_me_200(client):
    """GET /api/auth/me returns user when valid token provided."""
    with patch.dict("os.environ", {"ADMIN_PASSWORD": "secret"}, clear=False):
        with patch.object(api_main, "ADMIN_PASSWORD", "secret"):
            login_r = client.post("/api/auth/login", json={"password": "secret"})
        token = login_r.json()["token"]
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"user": "admin"}


# --- Settings (no DB): use client_with_overrides and mock service where needed ---


def test_get_settings_ignore_lands_cards(client_with_overrides):
    """GET /api/settings/ignore-lands-cards returns cards list (admin)."""
    with patch.object(api_main.settings_service, "get_ignore_lands_cards", return_value=["Forest", "Swamp"]):
        r = client_with_overrides.get("/api/settings/ignore-lands-cards")
    assert r.status_code == 200
    assert r.json() == {"cards": ["Forest", "Swamp"]}


def test_put_settings_ignore_lands_cards(client_with_overrides):
    """PUT /api/settings/ignore-lands-cards updates and returns cards (admin)."""
    with patch.object(api_main.settings_service, "set_ignore_lands_cards", return_value=["Island", "Mountain"]):
        r = client_with_overrides.put("/api/settings/ignore-lands-cards", json={"cards": ["Island", "Mountain"]})
    assert r.status_code == 200
    assert r.json() == {"cards": ["Island", "Mountain"]}


def test_get_settings_rank_weights(client_with_overrides):
    """GET /api/settings/rank-weights returns weights (admin)."""
    with patch.object(api_main.settings_service, "get_rank_weights", return_value={"1": 10.0, "2": 8.0}):
        r = client_with_overrides.get("/api/settings/rank-weights")
    assert r.status_code == 200
    assert r.json() == {"weights": {"1": 10.0, "2": 8.0}}


def test_put_settings_rank_weights(client_with_overrides):
    """PUT /api/settings/rank-weights updates and returns weights (admin)."""
    with patch.object(api_main.settings_service, "set_rank_weights", return_value={"1": 10.0}):
        r = client_with_overrides.put("/api/settings/rank-weights", json={"weights": {"1": 10.0}})
    assert r.status_code == 200
    assert r.json() == {"weights": {"1": 10.0}}


def test_post_settings_clear_cache(client_with_overrides):
    """POST /api/settings/clear-cache clears Scryfall cache (admin)."""
    with patch.object(api_main, "clear_scryfall_cache"):
        r = client_with_overrides.post("/api/settings/clear-cache")
    assert r.status_code == 200
    assert "message" in r.json()


# --- Players / aliases (no DB required for GET) ---


def test_get_player_aliases(client):
    """GET /api/player-aliases returns alias map."""
    r = client.get("/api/player-aliases")
    assert r.status_code == 200
    assert "aliases" in r.json()
    assert isinstance(r.json()["aliases"], dict)


def test_get_players_with_date_filter(client, sample_decks):
    """GET /api/players accepts date_from/date_to."""
    r = client.get("/api/players?date_from=01/01/26&date_to=31/12/26")
    assert r.status_code == 200
    assert "players" in r.json()


def test_get_player_detail(client, sample_decks):
    """GET /api/players/{name} returns player stats and decks."""
    player = sample_decks[0]["player"]
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get(f"/api/players/{player}")
    assert r.status_code == 200
    data = r.json()
    assert data["player"]
    assert "decks" in data
    assert "wins" in data
    assert "points" in data


def test_get_player_detail_404(client):
    """GET /api/players/{name} returns 404 for unknown player."""
    r = client.get("/api/players/NonexistentPlayer123")
    assert r.status_code == 404


def test_get_players_similar(client, sample_decks):
    """GET /api/players/similar returns similar name suggestions."""
    r = client.get("/api/players/similar?name=Jeremy&limit=5")
    assert r.status_code == 200
    data = r.json()
    assert "similar" in data
    assert isinstance(data["similar"], list)


# --- Metagame with query params ---


def test_get_metagame_with_date_params(client, sample_decks):
    """GET /api/metagame accepts date_from, date_to and returns expected shape."""
    r = client.get("/api/metagame?date_from=01/01/26&date_to=31/12/26")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "commander_distribution" in data
    assert "top_cards_main" in data


# --- Events (with _database_available mocked so we use in-memory _decks) ---


def test_get_events_list(client, sample_decks):
    """GET /api/events returns events derived from decks when DB not used."""
    api_main._events_cache = None
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/events")
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
    """GET /api/events/{event_id} returns event when found from decks."""
    event_id = sample_decks[0]["event_id"]
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get(f"/api/events/{event_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["event_id"] == event_id
    assert "event_name" in data
    assert "date" in data


def test_get_event_by_id_404(client):
    """GET /api/events/{event_id} returns 404 when event not found."""
    with patch.object(api_main, "_database_available", return_value=False):
        r = client.get("/api/events/99999999")
    assert r.status_code == 404


# --- Matchups (with client_with_overrides and mocked DB) ---


def test_get_matchups_summary(client_with_overrides):
    """GET /api/matchups/summary returns structure when DB is mocked."""
    from contextlib import contextmanager

    @contextmanager
    def mock_session_scope():
        yield None

    mock_rows = []
    with patch.object(api_main, "_db") as mock_db:
        mock_db.session_scope = mock_session_scope
        mock_db.get_matchups_min_matches.return_value = 0
        mock_db.list_matchups_with_deck_info.return_value = []
        r = client_with_overrides.get("/api/matchups/summary")
    assert r.status_code == 200
    data = r.json()
    assert "list" in data and "matrix" in data and "min_matches" in data
