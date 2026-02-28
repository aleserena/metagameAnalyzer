"""Unit tests for api.services.settings."""

import pytest

# Import after potential env/path setup so we can monkeypatch before first use
import api.services.settings as settings_module


def test_get_rank_weights_default_when_missing(tmp_path, monkeypatch):
    """get_rank_weights returns analyzer defaults when file is missing."""
    monkeypatch.setattr(settings_module, "_DATA_DIR", tmp_path)
    assert not (tmp_path / "rank_weights.json").exists()
    weights = settings_module.get_rank_weights()
    assert isinstance(weights, dict)
    assert "1" in weights or len(weights) >= 1


def test_set_rank_weights_roundtrip(tmp_path, monkeypatch):
    """set_rank_weights persists and get_rank_weights returns stored mapping."""
    monkeypatch.setattr(settings_module, "_DATA_DIR", tmp_path)
    weights = {"1": 10.0, "2": 8.0, "3-4": 6.0}
    out = settings_module.set_rank_weights(weights)
    assert out == settings_module.get_rank_weights()
    assert out.get("1") == 10.0
    assert out.get("2") == 8.0


def test_get_ignore_lands_cards_default_when_missing(tmp_path, monkeypatch):
    """get_ignore_lands_cards returns default set when file is missing."""
    monkeypatch.setattr(settings_module, "_DATA_DIR", tmp_path)
    assert not (tmp_path / "ignore_lands_cards.json").exists()
    cards = settings_module.get_ignore_lands_cards()
    assert isinstance(cards, list)
    assert all(isinstance(c, str) for c in cards)
    assert sorted(cards) == cards


def test_set_ignore_lands_cards_roundtrip(tmp_path, monkeypatch):
    """set_ignore_lands_cards persists and get returns stored list."""
    monkeypatch.setattr(settings_module, "_DATA_DIR", tmp_path)
    cards = ["Forest", "Swamp", "Island"]
    out = settings_module.set_ignore_lands_cards(cards)
    assert out == settings_module.get_ignore_lands_cards()
    assert set(out) == {"Forest", "Swamp", "Island"}
    assert out == sorted(out)


def test_set_ignore_lands_cards_dedupes_and_sorts(tmp_path, monkeypatch):
    """set_ignore_lands_cards deduplicates and returns sorted list."""
    monkeypatch.setattr(settings_module, "_DATA_DIR", tmp_path)
    out = settings_module.set_ignore_lands_cards(["Mountain", "Forest", "Mountain", "  Island  "])
    assert out == ["Forest", "Island", "Mountain"]


def test_get_matchups_min_matches_when_db_unavailable(monkeypatch):
    """get_matchups_min_matches returns 0 when DB is not available."""
    monkeypatch.setattr(settings_module, "_db", None)
    assert settings_module.get_matchups_min_matches() == 0


def test_set_matchups_min_matches_when_db_unavailable(monkeypatch):
    """set_matchups_min_matches is no-op when DB unavailable, returns value."""
    monkeypatch.setattr(settings_module, "_db", None)
    out = settings_module.set_matchups_min_matches(5)
    assert out == 5
