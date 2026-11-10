"""Give existing never-expiring upload/feedback/event-edit links a 7-day expiry.

Revision ID: 014
Revises: 013
Create Date: 2026-11-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE event_upload_links "
        "SET expires_at = (now() AT TIME ZONE 'utc') + interval '7 days' "
        "WHERE expires_at IS NULL"
    )


def downgrade() -> None:
    pass  # the previous "no expiry" state cannot be told apart from links that had one
