"""Unique constraint on matchups (deck_id, round, opponent_player) to prevent duplicates.

Revision ID: 011
Revises: 010
Create Date: 2025-03-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove duplicate rows (keep row with smallest id per deck_id, round, opponent_player)
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text("""
            DELETE FROM matchups a
            USING matchups b
            WHERE a.deck_id = b.deck_id
              AND (a.round IS NOT DISTINCT FROM b.round)
              AND a.opponent_player = b.opponent_player
              AND a.id > b.id
        """))
    op.create_unique_constraint(
        "uq_matchups_deck_id_round_opponent_player",
        "matchups",
        ["deck_id", "round", "opponent_player"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_matchups_deck_id_round_opponent_player",
        "matchups",
        type_="unique",
    )
