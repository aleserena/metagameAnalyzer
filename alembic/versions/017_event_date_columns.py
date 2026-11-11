"""Add events.event_date and decks.event_date (DATE, indexed) next to the text date columns.

Revision ID: 017
Revises: 016
Create Date: 2026-11-11

Rows written or edited by the previous release after this migration (NULL or stale event_date) are
repaired by migration 018 before it drops the text columns.
"""
from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("events", "decks")
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


def _backfill(bind) -> None:
    """Set event_date per table in a few set-based statements (there is no index on ``date`` yet).

    One UPDATE per distinct date would full-scan the table each time while the ADD COLUMN lock is held.
    """
    stmt_tpl = (
        "UPDATE {table} t SET event_date = v.d "
        "FROM unnest(CAST(:s AS text[]), CAST(:d AS date[])) AS v(s, d) "
        "WHERE t.date = v.s AND t.event_date IS NULL"
    )
    for table in _TABLES:
        distinct = [
            r[0] for r in bind.execute(sa.text(f"SELECT DISTINCT date FROM {table} WHERE event_date IS NULL"))
        ]
        pairs = [(v, _parse(v)) for v in distinct]
        pairs = [(v, d) for v, d in pairs if d is not None]
        stmt = sa.text(stmt_tpl.format(table=table))
        for i in range(0, len(pairs), _CHUNK):
            chunk = pairs[i : i + _CHUNK]
            bind.execute(stmt, {"s": [v for v, _ in chunk], "d": [d for _, d in chunk]})


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("event_date", sa.Date(), nullable=True))
    _backfill(op.get_bind())
    for table in _TABLES:
        op.create_index(f"ix_{table}_event_date", table, ["event_date"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_event_date", table_name=table)
        op.drop_column(table, "event_date")
