"""
Copy each event's name, date, format and player count onto its decks.

Decks keep their own copy of these fields; editing an event used to change only the
``events`` row. This repairs decks that drifted before event edits propagated.

Pass ``--db-env`` to choose the database. Without it the ambient ``DB_ENV`` decides, and
``.env`` sets that to ``staging``. Every run prints the database it resolved to; read that
line before trusting the output.

Examples:
  python3 -m scripts.sync_deck_event_fields --dry-run --db-env staging
  python3 -m scripts.sync_deck_event_fields --apply --db-env staging

After --apply, restart the API so ``state.decks`` reloads.
"""

from __future__ import annotations

import argparse

from api import db as _db
from scripts._env import VALID_DB_ENVS, load_env


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
        total = 0
        for (event_id,) in session.query(_db.EventRow.event_id).all():
            count = _db.sync_decks_with_event(session, event_id)
            if count:
                print(f"{event_id}: {count} decks updated")
            total += count
        print(f"Total: {total} decks updated")
        if args.dry_run:
            session.rollback()
            print("Dry run: nothing was saved.")
        else:
            session.commit()
            print("Done. Restart the API so state.decks reloads.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
