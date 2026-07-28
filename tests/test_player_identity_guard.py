"""Startup guard: surface players split across two ids by a stale alias duplicate."""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.state import log_split_player_identities, state


def _mock_db(dupes):
    mock_db = MagicMock()
    scope = MagicMock()
    scope.__enter__.return_value = MagicMock()
    mock_db.session_scope.return_value = scope
    mock_db.collect_alias_duplicate_player_merges.return_value = dupes
    return mock_db


def test_warns_when_an_alias_still_has_its_own_player_row(caplog):
    """A duplicate players row splits one person across the matchup matrix; say so loudly."""
    with (
        patch.object(state, "database_available", return_value=True),
        patch("api.state._db", _mock_db([(493, 584, "Dal Miro")])),
        caplog.at_level(logging.WARNING, logger="api.state"),
    ):
        log_split_player_identities()

    assert "Dal Miro" in caplog.text
    assert "493" in caplog.text and "584" in caplog.text
    assert "merge_alias_duplicate_players" in caplog.text, "should name the fix command"


def test_silent_when_no_split_identities(caplog):
    with (
        patch.object(state, "database_available", return_value=True),
        patch("api.state._db", _mock_db([])),
        caplog.at_level(logging.WARNING, logger="api.state"),
    ):
        log_split_player_identities()

    assert caplog.text == ""


def test_no_database_is_not_an_error(caplog):
    with (
        patch.object(state, "database_available", return_value=False),
        caplog.at_level(logging.WARNING, logger="api.state"),
    ):
        log_split_player_identities()

    assert caplog.text == ""


def test_db_failure_does_not_break_startup(caplog):
    mock_db = MagicMock()
    mock_db.session_scope.side_effect = RuntimeError("connection refused")
    with (
        patch.object(state, "database_available", return_value=True),
        patch("api.state._db", mock_db),
        caplog.at_level(logging.WARNING, logger="api.state"),
    ):
        log_split_player_identities()  # must not raise

    assert "connection refused" in caplog.text
