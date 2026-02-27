"""Add player_emails table for admin-stored player email (one per canonical player).

Revision ID: 008
Revises: 007
Create Date: 2025-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_emails",
        sa.Column("player", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("player"),
    )


def downgrade() -> None:
    op.drop_table("player_emails")
