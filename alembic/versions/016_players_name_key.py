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

_CHUNK = 5000


def _key(name: str) -> str:
    """Must match api.db._normalize_name_for_lookup."""
    nfd = unicodedata.normalize("NFD", (name or "").strip().lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _backfill(conn) -> None:
    """Set name_key for every player in a few set-based statements (one round trip per chunk)."""
    rows = conn.execute(sa.text("SELECT id, display_name FROM players")).fetchall()
    stmt = sa.text(
        "UPDATE players p SET name_key = v.k "
        "FROM unnest(CAST(:ids AS integer[]), CAST(:keys AS text[])) AS v(id, k) "
        "WHERE p.id = v.id"
    )
    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i : i + _CHUNK]
        conn.execute(stmt, {"ids": [r[0] for r in chunk], "keys": [_key(r[1]) for r in chunk]})


def upgrade() -> None:
    op.add_column("players", sa.Column("name_key", sa.Text(), nullable=True))
    _backfill(op.get_bind())
    op.create_index(op.f("ix_players_name_key"), "players", ["name_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_players_name_key"), table_name="players")
    op.drop_column("players", "name_key")
