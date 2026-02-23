"""Add player_count to events (number of players in the event).

Revision ID: 003
Revises: 002
Create Date: 2025-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("player_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("events", "player_count")
