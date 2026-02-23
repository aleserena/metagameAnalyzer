"""Add store and location to events.

Revision ID: 004
Revises: 003
Create Date: 2025-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("store", sa.String(512), nullable=False, server_default=""))
    op.add_column("events", sa.Column("location", sa.String(512), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("events", "location")
    op.drop_column("events", "store")
