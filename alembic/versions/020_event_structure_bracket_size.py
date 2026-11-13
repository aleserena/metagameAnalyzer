"""Add events.structure and events.bracket_size (single-elimination events).

Revision ID: 020
Revises: 019
Create Date: 2026-11-13

Additive only (two nullable columns, no backfill), so the previous release keeps working against the
migrated database. NULL structure means Swiss + Top 8, as before; ``bracket_size`` is only used when
``structure = 'single_elimination'``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("structure", sa.String(32), nullable=True))
    op.add_column("events", sa.Column("bracket_size", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "bracket_size")
    op.drop_column("events", "structure")
