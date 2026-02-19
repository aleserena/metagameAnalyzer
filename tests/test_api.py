"""API integration tests using FastAPI TestClient."""

import sys
from pathlib import Path

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
    """GET /api/decks filters by event_id."""
    event_id = sample_decks[0]["event_id"]
    r = client.get(f"/api/decks?event_id={event_id}")
    assert r.status_code == 200
    data = r.json()
    assert all(d["event_id"] == event_id for d in data["decks"])


def test_get_decks_filter_deck_name(client, sample_decks):
    """GET /api/decks filters by deck_name substring."""
    r = client.get("/api/decks?deck_name=Spider")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    assert any("Spider" in (d.get("name") or "") for d in data["decks"])


def test_get_decks_filter_player(client, sample_decks):
    """GET /api/decks filters by player substring."""
    r = client.get("/api/decks?player=Jeremy")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decks"]) >= 1
    assert any("Jeremy" in (d.get("player") or "") for d in data["decks"])


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
