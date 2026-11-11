"""Unit tests for api.services.settings."""

# Import after potential env/path setup so we can monkeypatch before first use
import json

import pytest

import api.services.settings as settings_module


@pytest.fixture(autouse=True)
def _file_mode_unless_settings_rows(request, monkeypatch):
    """Legacy tests exercise the JSON-file path; DB tests request settings_rows."""
    if "settings_rows" not in request.fixturenames:
        monkeypatch.setattr(settings_module, "_db_available", lambda: False)
        settings_module._reset_cache_for_tests()


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


def test_legacy_file_is_imported_into_the_database_once(tmp_path, monkeypatch, settings_rows):
    monkeypatch.setattr(settings_module, "_DATA_DIR", tmp_path)
    f = tmp_path / "settings" / "rank_weights.json"
    f.parent.mkdir()
    f.write_text(json.dumps({"weights": {"1": 42.0}}))
    assert settings_module.get_rank_weights() == {"1": 42.0}
    f.unlink()
    settings_module._reset_cache_for_tests()
    assert settings_module.get_rank_weights() == {"1": 42.0}


def test_values_survive_a_restart(tmp_path, monkeypatch, settings_rows):
    monkeypatch.setattr(settings_module, "_DATA_DIR", tmp_path)
    settings_module.set_ignore_lands_cards(["Island", " Forest ", "Island"])
    settings_module._reset_cache_for_tests()
    assert settings_module.get_ignore_lands_cards() == ["Forest", "Island"]
    assert not (tmp_path / "settings" / "ignore_lands_cards.json").exists()


def test_malformed_file_and_no_row_gives_defaults_and_stores_nothing(tmp_path, monkeypatch, settings_rows):
    from api import db

    monkeypatch.setattr(settings_module, "_DATA_DIR", tmp_path)
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "rank_weights.json").write_text("{not json")
    assert settings_module.get_rank_weights() == dict(settings_module.DEFAULT_RANK_WEIGHTS)
    with db.session_scope() as session:
        assert db.get_setting(session, "rank_weights") is None
    assert settings_module._cache_get("rank_weights") is None


def test_database_error_on_read_gives_defaults(settings_rows, monkeypatch):
    from api import db

    def boom():
        raise RuntimeError("db down")

    # scoped patch: it must be undone before the settings_rows fixture cleans up
    with monkeypatch.context() as patch:
        patch.setattr(db, "session_scope", boom)
        assert settings_module.get_rank_weights() == dict(settings_module.DEFAULT_RANK_WEIGHTS)
    assert settings_module._cache_get("rank_weights") is None


def test_setting_a_value_bumps_the_version(tmp_path, monkeypatch, settings_rows):
    monkeypatch.setattr(settings_module, "_DATA_DIR", tmp_path)
    v = settings_module.version()
    settings_module.set_rank_weights({"1": 5.0})
    assert settings_module.version() == v + 1
