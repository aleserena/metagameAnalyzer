"""One deck per player per event: unique constraint on (event_id, player).

Revision ID: 010
Revises: 009
Create Date: 2025-02-26

"""
from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_decks_event_id_player",
        "decks",
        ["event_id", "player"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_decks_event_id_player", "decks", type_="unique")
