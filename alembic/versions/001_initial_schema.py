"""Initial schema: events, decks, player_aliases, settings.

Revision ID: 001
Revises:
Create Date: 2025-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("format_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("date", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "decks",
        sa.Column("deck_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("format_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("player", sa.String(512), nullable=False),
        sa.Column("event_name", sa.String(512), nullable=False),
        sa.Column("date", sa.String(32), nullable=False),
        sa.Column("rank", sa.String(32), nullable=False),
        sa.Column("player_count", sa.Integer(), nullable=False),
        sa.Column("commanders", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("archetype", sa.String(512), nullable=True),
        sa.Column("mainboard", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sideboard", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("deck_id"),
    )
    op.create_table(
        "player_aliases",
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("canonical", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("alias"),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("player_aliases")
    op.drop_table("decks")
    op.drop_table("events")
