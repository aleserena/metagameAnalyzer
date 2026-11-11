"""Add events.event_date and decks.event_date (DATE, indexed) next to the text date columns.

Revision ID: 017
Revises: 016
Create Date: 2026-11-11

Rows written by the previous release between this migration and the new deploy (or while an old release keeps
serving after a failed deploy) get event_date NULL. Re-run the backfill (it only touches rows with a NULL
event_date, so it is idempotent) or rely on release 2's Step 1 checks.

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
    for table in _TABLES:
        distinct = [
            r[0] for r in bind.execute(sa.text(f"SELECT DISTINCT date FROM {table} WHERE event_date IS NULL"))
        ]
        for text_value in distinct:
            parsed = _parse(text_value)
            if parsed is not None:
                bind.execute(
                    sa.text(f"UPDATE {table} SET event_date = :d WHERE date = :s AND event_date IS NULL"),
                    {"d": parsed, "s": text_value},
                )


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
