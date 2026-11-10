"""Add players.name_key (accent-insensitive normalized name) with an index.

Revision ID: 016
Revises: 015
Create Date: 2026-11-10

"""
import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _key(name: str) -> str:
    """Must match api.db._normalize_name_for_lookup."""
    nfd = unicodedata.normalize("NFD", (name or "").strip().lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def upgrade() -> None:
    op.add_column("players", sa.Column("name_key", sa.Text(), nullable=True))
    conn = op.get_bind()
    for pid, name in conn.execute(sa.text("SELECT id, display_name FROM players")).fetchall():
        conn.execute(sa.text("UPDATE players SET name_key = :k WHERE id = :id"), {"k": _key(name), "id": pid})
    op.create_index(op.f("ix_players_name_key"), "players", ["name_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_players_name_key"), table_name="players")
    op.drop_column("players", "name_key")
