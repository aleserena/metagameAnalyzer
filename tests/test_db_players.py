"""Tests for player resolution: get_or_create_player, resolve_name_to_player_id, and response shape."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.db import (
    PlayerRow,
    get_or_create_player,
    get_player_by_id,
    merge_players_by_names,
    resolve_name_to_player_id,
    set_player_alias,
)


def test_get_or_create_player_creates_and_returns_stable_id(db_session_rollback):
    """get_or_create_player creates a player and returns the same id on second call."""
    session = db_session_rollback
    pid1, display1 = get_or_create_player(session, "Alice")
    assert isinstance(pid1, int)
    assert display1 == "Alice"
    row = get_player_by_id(session, pid1)
    assert row is not None
    assert row.display_name == "Alice"

    pid2, display2 = get_or_create_player(session, "Alice")
    assert pid2 == pid1
    assert display2 == "Alice"


def test_resolve_name_to_player_id_with_alias(db_session_rollback):
    """resolve_name_to_player_id returns (player_id, display_name) for an alias mapping to a player."""
    session = db_session_rollback
    pid, _ = get_or_create_player(session, "Bob")
    set_player_alias(session, "Bobby", "Bob")
    session.flush()

    resolved_id, resolved_name = resolve_name_to_player_id(session, "Bobby")
    assert resolved_id == pid
    assert resolved_name == "Bob"

    # Display name also resolves
    direct_id, direct_name = resolve_name_to_player_id(session, "Bob")
    assert direct_id == pid
    assert direct_name == "Bob"


def test_merge_players_by_names_merges_duplicate_when_alias_row_already_exists(db_session_rollback):
    """The duplicate is merged even if the alias row was written first.

    ``add_player_alias`` persists the alias before merging. Resolving the alias
    side by alias table first would return the canonical id, making the merge a
    silent no-op and leaving a duplicate players row that splits the player's
    record across the matchup matrix.
    """
    session = db_session_rollback
    dup_id, _ = get_or_create_player(session, "ZZTest Dal Miro")
    canon_id, _ = get_or_create_player(session, "ZZTest Dalmiro Vilca")
    assert dup_id != canon_id

    set_player_alias(session, "ZZTest Dal Miro", "ZZTest Dalmiro Vilca")
    session.flush()

    merge_players_by_names(session, "ZZTest Dal Miro", "ZZTest Dalmiro Vilca")
    session.flush()

    assert get_player_by_id(session, dup_id) is None, "duplicate players row should be merged away"
    assert get_player_by_id(session, canon_id) is not None
    remaining = session.query(PlayerRow).filter(PlayerRow.display_name == "ZZTest Dal Miro").first()
    assert remaining is None


def test_merge_players_by_names_is_noop_without_a_duplicate_row(db_session_rollback):
    """An alias with no duplicate players row leaves the canonical player untouched."""
    session = db_session_rollback
    canon_id, _ = get_or_create_player(session, "ZZTest Solo Player")
    set_player_alias(session, "ZZTest Solo Nickname", "ZZTest Solo Player")
    session.flush()

    merge_players_by_names(session, "ZZTest Solo Nickname", "ZZTest Solo Player")
    session.flush()

    row = get_player_by_id(session, canon_id)
    assert row is not None
    assert row.display_name == "ZZTest Solo Player"


def test_name_key_is_maintained_and_used(db_session_rollback, sql_log):
    from api.db import rename_player_display_name

    session = db_session_rollback
    pid, _ = get_or_create_player(session, "Zzkey Matías Pérez")
    assert session.get(PlayerRow, pid).name_key == "zzkey matias perez"
    sql_log.clear()
    assert resolve_name_to_player_id(session, "zzkey matias perez")[0] == pid  # found before commit
    assert get_or_create_player(session, "ZZKEY MATIAS PEREZ")[0] == pid
    selects = [s for s in sql_log if "FROM players" in s]
    assert selects and all("WHERE" in s for s in selects)
    rename_player_display_name(session, pid, "Zzkey Renamed Ñandú")
    session.flush()
    assert resolve_name_to_player_id(session, "zzkey renamed nandu")[0] == pid


def test_migration_016_key_matches_runtime_normalizer():
    import importlib.util

    from api.db import _normalize_name_for_lookup

    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "016_players_name_key.py"
    spec = importlib.util.spec_from_file_location("migration_016", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in ("  Matías Ñandú  ", "", "   ", "ABC"):
        assert mod._key(name) == _normalize_name_for_lookup(name)
