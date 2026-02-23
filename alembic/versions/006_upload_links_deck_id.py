"""Add deck_id to event_upload_links for one-time update-deck links.

Revision ID: 006
Revises: 005
Create Date: 2025-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "event_upload_links",
        sa.Column("deck_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("event_upload_links", "deck_id")
