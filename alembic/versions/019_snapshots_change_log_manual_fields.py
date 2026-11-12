"""Add event_snapshots, change_log and the manual_fields columns on decks and events.

Revision ID: 019
Revises: 018
Create Date: 2026-11-12

Additive only (two new tables, two nullable columns, no backfill), so the previous release keeps
working against the migrated database. ``event_snapshots.event_id`` deliberately has no foreign key:
a snapshot must outlive the event it was taken from.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(32), nullable=False),
        sa.Column("event_name", sa.String(512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_event_snapshots_event_id", "event_snapshots", ["event_id"])
    op.create_index("ix_event_snapshots_created_at", "event_snapshots", ["created_at"])

    op.create_table(
        "change_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(32), nullable=True),
        sa.Column("deck_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(512), nullable=False, server_default=""),
    )
    op.create_index("ix_change_log_at", "change_log", ["at"])
    op.create_index("ix_change_log_event_id", "change_log", ["event_id"])

    # Field names edited by hand; a re-scrape leaves them alone. NULL = never edited.
    op.add_column("decks", sa.Column("manual_fields", postgresql.JSONB(), nullable=True))
    op.add_column("events", sa.Column("manual_fields", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "manual_fields")
    op.drop_column("decks", "manual_fields")
    op.drop_index("ix_change_log_event_id", table_name="change_log")
    op.drop_index("ix_change_log_at", table_name="change_log")
    op.drop_table("change_log")
    op.drop_index("ix_event_snapshots_created_at", table_name="event_snapshots")
    op.drop_index("ix_event_snapshots_event_id", table_name="event_snapshots")
    op.drop_table("event_snapshots")
