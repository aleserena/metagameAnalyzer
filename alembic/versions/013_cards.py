"""Add cards table for MTGJSON-sourced card metadata.

Revision ID: 013
Revises: 012
Create Date: 2026-06-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cards",
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("scryfall_id", sa.String(64), nullable=True),
        sa.Column("mtgjson_uuid", sa.String(64), nullable=True),
        sa.Column("mana_cost", sa.String(128), nullable=False, server_default=""),
        sa.Column("cmc", sa.Float(), nullable=False, server_default="0"),
        sa.Column("type_line", sa.String(512), nullable=False, server_default=""),
        sa.Column("oracle_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("colors", JSONB(), nullable=False, server_default="[]"),
        sa.Column("color_identity", JSONB(), nullable=False, server_default="[]"),
        sa.Column("layout", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("card_faces", JSONB(), nullable=False, server_default="[]"),
        sa.Column("price_usd", sa.String(32), nullable=True),
        sa.Column("price_usd_foil", sa.String(32), nullable=True),
        sa.Column("price_eur", sa.String(32), nullable=True),
        sa.Column("price_eur_foil", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_index(op.f("ix_cards_mtgjson_uuid"), "cards", ["mtgjson_uuid"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cards_mtgjson_uuid"), table_name="cards")
    op.drop_table("cards")
