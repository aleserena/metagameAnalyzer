"""Add cards.front_face_name so double-faced cards resolve by their front face.

Revision ID: 015
Revises: 014
Create Date: 2026-11-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("front_face_name", sa.String(512), nullable=True))
    op.execute("UPDATE cards SET front_face_name = split_part(name, ' // ', 1) WHERE name LIKE '% // %'")
    op.create_index(op.f("ix_cards_front_face_name"), "cards", ["front_face_name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cards_front_face_name"), table_name="cards")
    op.drop_column("cards", "front_face_name")
