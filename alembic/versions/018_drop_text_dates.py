"""Drop the text ``date`` columns from events and decks; ``event_date`` (DATE) is the only stored date.

Revision ID: 018
Revises: 017
Create Date: 2026-11-11

This is the one exception to the additive-migration rule: the previous release still reads and writes the
text column, so it stops working against this database once the migration commits. Deploy at a quiet time and
roll forward, not back, if the new release fails after the migration ran.

Before dropping anything the migration brings ``event_date`` in line with the text one last time (rows the
previous release wrote or edited after migration 017), then refuses to continue - failing the deploy and
leaving the schema untouched - if a date would be lost:

- a row whose text date is not empty but cannot be parsed, or
- a row whose year is outside 2000-2099, which cannot be shown as ``YY``.

Fix those rows by hand (correct the text, or set it to ``''`` to accept an empty date) and deploy again.
"""
from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (("events", "event_id"), ("decks", "deck_id"))
_CHUNK = 5000


def _parse(s):
    """Must match api.dates.parse_ddmmyy (a two-digit year is 20xx; impossible dates are None)."""
    if not s:
        return None
    parts = s.strip().split("/")
    if len(parts) != 3 or not all(p.isascii() and p.isdigit() for p in parts):
        return None
    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
    if len(parts[2]) <= 2:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _sync(bind) -> None:
    """Set ``event_date = parse(date)`` wherever they differ, set-based (one UPDATE per chunk of distinct dates)."""
    stmt_tpl = (
        "UPDATE {table} t SET event_date = v.d "
        "FROM unnest(CAST(:s AS text[]), CAST(:d AS date[])) AS v(s, d) "
        "WHERE t.date = v.s AND t.event_date IS DISTINCT FROM v.d"
    )
    for table, _pk in _TABLES:
        distinct = [r[0] for r in bind.execute(sa.text(f"SELECT DISTINCT date FROM {table}")) if r[0] is not None]
        pairs = [(v, _parse(v)) for v in distinct]
        stmt = sa.text(stmt_tpl.format(table=table))
        for i in range(0, len(pairs), _CHUNK):
            chunk = pairs[i : i + _CHUNK]
            bind.execute(stmt, {"s": [v for v, _ in chunk], "d": [d for _, d in chunk]})


def _check(bind) -> None:
    """Raise if dropping the text column would lose a date. Call after :func:`_sync`."""
    problems = []
    for table, pk in _TABLES:
        unparsed = bind.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE btrim(date) <> '' AND event_date IS NULL")
        ).scalar_one()
        if unparsed:
            sample = bind.execute(
                sa.text(
                    f"SELECT {pk}, date FROM {table} WHERE btrim(date) <> '' AND event_date IS NULL "
                    f"ORDER BY {pk} LIMIT 5"
                )
            ).all()
            shown = ", ".join(f"{r[0]}={r[1]!r}" for r in sample)
            problems.append(f"{table}: {unparsed} row(s) with a text date that cannot be parsed (e.g. {shown})")
        out_of_range = bind.execute(
            sa.text(
                f"SELECT count(*) FROM {table} "
                "WHERE event_date < DATE '2000-01-01' OR event_date >= DATE '2100-01-01'"
            )
        ).scalar_one()
        if out_of_range:
            problems.append(f"{table}: {out_of_range} row(s) with a year outside 2000-2099")
    if problems:
        raise RuntimeError(
            "Migration 018 stopped before dropping the text date columns; nothing was changed. "
            + "; ".join(problems)
            + ". Fix these rows (or set date = '' to accept an empty date) and deploy again."
        )


def upgrade() -> None:
    bind = op.get_bind()
    _sync(bind)
    _check(bind)
    for table, _pk in _TABLES:
        op.drop_column(table, "date")


def downgrade() -> None:
    for table, _pk in _TABLES:
        op.add_column(table, sa.Column("date", sa.String(32), nullable=False, server_default=""))
        op.execute(f"UPDATE {table} SET date = to_char(event_date, 'DD/MM/YY') WHERE event_date IS NOT NULL")
