"""Add link_type to event_upload_links for event-edit links.

Revision ID: 007
Revises: 006
Create Date: 2025-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "event_upload_links",
        sa.Column("link_type", sa.String(32), nullable=True),
    )
    # Backfill: deck_update where deck_id IS NOT NULL, else deck_upload
    op.execute(
        "UPDATE event_upload_links SET link_type = CASE WHEN deck_id IS NOT NULL THEN 'deck_update' ELSE 'deck_upload' END WHERE link_type IS NULL"
    )
    op.alter_column(
        "event_upload_links",
        "link_type",
        existing_type=sa.String(32),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("event_upload_links", "link_type")
