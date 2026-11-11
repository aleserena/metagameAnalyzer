"""
Make events.event_date and decks.event_date agree with the text ``date`` column.

Migration 017 backfills every row, but the previous release can still write rows afterwards:
new rows get a NULL event_date, and an edit of the text ``date`` leaves a stale non-NULL
event_date. Run this before the release that drops the text columns (plan Task 10). It sets
``event_date = parse_ddmmyy(date)`` wherever they differ (NULL vs a value, a value vs NULL, or
two different values) and is idempotent and safe to re-run.

Pass ``--db-env`` to choose the database. Without it the ambient ``DB_ENV`` decides, and
``.env`` sets that to ``staging``. Every run prints the database it resolved to.

Examples:
  python3 -m scripts.backfill_event_dates --dry-run --db-env prod
  python3 -m scripts.backfill_event_dates --apply --db-env prod
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from api import db as _db
from api.dates import parse_ddmmyy
from scripts._env import VALID_DB_ENVS, load_env

_TABLES = ("events", "decks")
_CHUNK = 5000


def sync_event_dates(session, apply: bool) -> dict[str, int]:
    """Return rows whose event_date differs from ``parse_ddmmyy(date)`` per table; fix them when ``apply``.

    Set-based: the distinct text dates are parsed in Python and joined back through ``unnest``.
    """
    counts: dict[str, int] = {}
    for table in _TABLES:
        distinct = [r[0] for r in session.execute(text(f"SELECT DISTINCT date FROM {table}"))]
        pairs = [(v, parse_ddmmyy(v)) for v in distinct if v is not None]
        verb = "UPDATE {t} t SET event_date = v.d" if apply else "SELECT count(*) FROM {t} t"
        stmt = text(
            verb.format(t=table)
            + (" FROM" if apply else ",")
            + " unnest(CAST(:s AS text[]), CAST(:d AS date[])) AS v(s, d)"
            " WHERE t.date = v.s AND t.event_date IS DISTINCT FROM v.d"
        )
        total = 0
        for i in range(0, len(pairs), _CHUNK):
            chunk = pairs[i : i + _CHUNK]
            params = {"s": [v for v, _ in chunk], "d": [d for _, d in chunk]}
            if apply:
                total += session.execute(stmt, params).rowcount
            else:
                total += session.execute(stmt, params).scalar_one()
        counts[table] = total
    return counts


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
        counts = sync_event_dates(session, apply=args.apply)
        for table, n in counts.items():
            print(f"{table}: {n} rows where event_date differs from the parsed text date")
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
