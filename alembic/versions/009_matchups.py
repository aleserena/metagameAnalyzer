"""Add matchups table for event feedback (deck vs opponent, result).

Revision ID: 009
Revises: 008
Create Date: 2025-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "matchups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("deck_id", sa.Integer(), nullable=False),
        sa.Column("opponent_player", sa.String(512), nullable=False),
        sa.Column("opponent_deck_id", sa.Integer(), nullable=True),
        sa.Column("opponent_archetype", sa.String(512), nullable=True),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("result_note", sa.String(512), nullable=True),
        sa.Column("round", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["deck_id"], ["decks.deck_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opponent_deck_id"], ["decks.deck_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_matchups_deck_id"), "matchups", ["deck_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_matchups_deck_id"), table_name="matchups")
    op.drop_table("matchups")
