"""Tests for commander/partner role filtering in card autocomplete search."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.dialects import postgresql

from api.db import _card_role_predicate
from src.mtgtop8 import card_lookup


def _sql(predicate) -> str:
    return str(
        predicate.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()


def test_role_predicate_none_for_empty_or_unknown():
    assert _card_role_predicate(None) is None
    assert _card_role_predicate("") is None
    assert _card_role_predicate("not_a_role") is None


def test_role_predicate_commander_includes_legendary_creature_and_can_be_commander():
    sql = _sql(_card_role_predicate("commander"))
    assert "legendary" in sql
    assert "creature" in sql
    assert "can be your commander" in sql


def test_role_predicate_partner_excludes_partner_with():
    sql = _sql(_card_role_predicate("partner"))
    assert "%partner%" in sql
    assert "%partner with%" in sql
    assert "not" in sql


def test_role_predicate_background_filters_type_line():
    sql = _sql(_card_role_predicate("background"))
    assert "background" in sql


def test_autocomplete_cards_forwards_role_to_db():
    fake_session = MagicMock()
    scope = MagicMock()
    scope.__enter__.return_value = fake_session

    with (
        patch("api.db.is_database_available", return_value=True),
        patch("api.db.session_scope", return_value=scope),
        patch("api.db.search_card_names", return_value=["Tymna the Weaver"]) as mock_search,
    ):
        result = card_lookup.autocomplete_cards("Tym", role="partner")

    assert result == ["Tymna the Weaver"]
    mock_search.assert_called_once_with(fake_session, "Tym", limit=20, role="partner")
