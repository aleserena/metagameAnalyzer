"""
Fill players.name_key where it is NULL.

Migration 016 backfills every player, but players inserted by the previous release between
the migration and the new deploy have a NULL key and so are invisible to the indexed
accent-insensitive lookup. This is idempotent and safe to re-run.

Pass ``--db-env`` to choose the database. Without it the ambient ``DB_ENV`` decides, and
``.env`` sets that to ``staging``. Every run prints the database it resolved to.

Examples:
  python3 -m scripts.backfill_player_name_keys --dry-run --db-env staging
  python3 -m scripts.backfill_player_name_keys --apply --db-env staging
"""

from __future__ import annotations

import argparse

from api import db as _db
from scripts._env import VALID_DB_ENVS, load_env


def backfill_name_keys(session) -> list[tuple[int, str, str]]:
    """Set name_key on every player where it is NULL; return ``(id, display_name, key)`` per change."""
    changes: list[tuple[int, str, str]] = []
    for row in session.query(_db.PlayerRow).filter(_db.PlayerRow.name_key.is_(None)).all():
        row.name_key = _db._normalize_name_for_lookup(row.display_name or "")
        changes.append((row.id, row.display_name, row.name_key))
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--db-env",
        choices=VALID_DB_ENVS,
        help="Which database to target. Overrides DB_ENV; .env defaults it to staging.",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")
    if args.dry_run and args.apply:
        parser.error("Use only one of --dry-run or --apply")

    target = load_env(args.db_env)
    print(f"target database: {target}")
    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")
    factory = _db.get_session_factory_cached()
    if factory is None:
        raise RuntimeError("Database session factory unavailable")

    session = factory()
    try:
        changes = backfill_name_keys(session)
        for pid, name, key in changes[:5]:
            print(f"player {pid}: {name!r} -> {key!r}")
        if len(changes) > 5:
            print(f"... and {len(changes) - 5} more")
        print(f"Total: {len(changes)} players with NULL name_key")
        if args.dry_run:
            session.rollback()
            print("Dry run: nothing was saved.")
        else:
            session.commit()
            print("Done.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
