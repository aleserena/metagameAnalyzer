"""Events and decks: event_id Integer -> String. Manual events become m1, m2, etc.

Revision ID: 002
Revises: 001
Create Date: 2025-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_pg():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        raise RuntimeError("This migration is for PostgreSQL only.")


def upgrade() -> None:
    _ensure_pg()
    # 1) Events: add new string column and populate (mtgtop8: int as text; manual: m1, m2, ...)
    op.add_column("events", sa.Column("event_id_str", sa.String(32), nullable=True))
    conn = op.get_bind()
    # Manual events: assign m1, m2, ... by order of current event_id
    conn.execute(sa.text("""
        WITH ordered AS (
            SELECT event_id, row_number() OVER (ORDER BY event_id) AS rn
            FROM events WHERE origin = 'manual'
        )
        UPDATE events SET event_id_str = 'm' || ordered.rn::text
        FROM ordered WHERE events.event_id = ordered.event_id AND events.origin = 'manual'
    """))
    # MTGTop8: event_id as string
    conn.execute(sa.text("UPDATE events SET event_id_str = event_id::text WHERE origin = 'mtgtop8'"))
    op.alter_column("events", "event_id_str", nullable=False)
    # 2) Decks: add event_id_str and copy from events mapping
    op.add_column("decks", sa.Column("event_id_str", sa.String(32), nullable=True))
    conn.execute(sa.text("""
        UPDATE decks d SET event_id_str = e.event_id_str
        FROM events e WHERE e.event_id = d.event_id
    """))
    op.alter_column("decks", "event_id_str", nullable=False)
    # 3) Drop old PK and event_id from events
    op.drop_constraint("events_pkey", "events", type_="primary")
    op.drop_column("events", "event_id")
    op.alter_column("events", "event_id_str", new_column_name="event_id")
    op.create_primary_key("events_pkey", "events", ["event_id"])
    # 4) Drop event_id from decks and rename
    op.drop_column("decks", "event_id")
    op.alter_column("decks", "event_id_str", new_column_name="event_id")


def downgrade() -> None:
    _ensure_pg()
    # Reverse: add integer columns back, populate from string (m1 -> 1000000, m2 -> 1000001, numeric -> cast)
    op.add_column("events", sa.Column("event_id_int", sa.Integer(), nullable=True))
    conn = op.get_bind()
    # Manual: m1 -> 1000000, m2 -> 1000001
    conn.execute(sa.text("""
        WITH ordered AS (
            SELECT event_id, row_number() OVER (ORDER BY event_id) AS rn
            FROM events WHERE origin = 'manual'
        )
        UPDATE events SET event_id_int = 1000000 + ordered.rn - 1
        FROM ordered WHERE events.event_id = ordered.event_id AND events.origin = 'manual'
    """))
    conn.execute(sa.text("UPDATE events SET event_id_int = event_id::int WHERE origin = 'mtgtop8'"))
    op.alter_column("events", "event_id_int", nullable=False)
    op.add_column("decks", sa.Column("event_id_int", sa.Integer(), nullable=True))
    conn.execute(sa.text("""
        UPDATE decks d SET event_id_int = e.event_id_int
        FROM events e WHERE e.event_id = d.event_id
    """))
    op.alter_column("decks", "event_id_int", nullable=False)
    op.drop_constraint("events_pkey", "events", type_="primary")
    op.drop_column("events", "event_id")  # drop string column
    op.alter_column("events", "event_id_int", new_column_name="event_id")
    op.create_primary_key("events_pkey", "events", ["event_id"])
    op.drop_column("decks", "event_id")  # drop string column
    op.alter_column("decks", "event_id_int", new_column_name="event_id")
