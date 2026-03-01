"""Players table, decks.player_id, player_aliases (alias->player_id), player_emails by player_id, matchups.opponent_player_id.

Revision ID: 012
Revises: 011
Create Date: 2025-03-01

Preserves existing player names and aliases: backfill uses current alias->canonical map
so one logical player = one player_id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create players table
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("display_name", name="uq_players_display_name"),
    )

    # 2. Add decks.player_id (nullable)
    op.add_column("decks", sa.Column("player_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_decks_player_id",
        "decks",
        "players",
        ["player_id"],
        ["id"],
    )

    # 3. Backfill decks: use current player_aliases (alias->canonical), one player per canonical
    alias_rows = conn.execute(sa.text("SELECT alias, canonical FROM player_aliases")).fetchall()
    alias_map = {str(r[0]).strip(): str(r[1]).strip() for r in alias_rows}
    deck_rows = conn.execute(sa.text("SELECT deck_id, player FROM decks")).fetchall()
    deck_canonical = {}
    canonicals = set()
    for (did, player) in deck_rows:
        p = (player or "").strip() or "(unknown)"
        c = alias_map.get(p, p)
        canonicals.add(c)
        deck_canonical[did] = c
    for c in canonicals:
        conn.execute(sa.text("INSERT INTO players (display_name) VALUES (:name) ON CONFLICT (display_name) DO NOTHING"), {"name": c})
    player_ids = {str(r[1]): r[0] for r in conn.execute(sa.text("SELECT id, display_name FROM players")).fetchall()}
    for did, c in deck_canonical.items():
        pid = player_ids.get(c)
        if pid is not None:
            conn.execute(sa.text("UPDATE decks SET player_id = :pid, player = :display WHERE deck_id = :did"), {"pid": pid, "display": c, "did": did})

    # 4. New player_aliases: alias -> player_id. Backfill from old (alias, canonical); create player if canonical only in aliases.
    op.create_table(
        "player_aliases_new",
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("alias"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], name="fk_player_aliases_new_player_id"),
    )
    old_alias_rows = conn.execute(sa.text("SELECT alias, canonical FROM player_aliases")).fetchall()
    for (alias_val, canonical_val) in old_alias_rows:
        alias_val = (alias_val or "").strip()
        canonical_val = (canonical_val or "").strip()
        if not alias_val or not canonical_val:
            continue
        conn.execute(sa.text("INSERT INTO players (display_name) VALUES (:name) ON CONFLICT (display_name) DO NOTHING"), {"name": canonical_val})
        row = conn.execute(sa.text("SELECT id FROM players WHERE display_name = :name"), {"name": canonical_val}).fetchone()
        if row:
            conn.execute(sa.text("INSERT INTO player_aliases_new (alias, player_id) VALUES (:alias, :pid) ON CONFLICT (alias) DO NOTHING"), {"alias": alias_val, "pid": row[0]})
    op.drop_table("player_aliases")
    op.rename_table("player_aliases_new", "player_aliases")

    # 5. player_emails by player_id
    op.create_table(
        "player_emails_new",
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("player_id"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], name="fk_player_emails_new_player_id"),
    )
    email_rows = conn.execute(sa.text("SELECT player, email FROM player_emails")).fetchall()
    display_to_id = {str(r[1]): r[0] for r in conn.execute(sa.text("SELECT id, display_name FROM players")).fetchall()}
    for (player_name, email) in email_rows:
        player_name = (player_name or "").strip()
        if not player_name:
            continue
        pid = display_to_id.get(player_name)
        if pid is not None:
            conn.execute(sa.text("INSERT INTO player_emails_new (player_id, email) VALUES (:pid, :email) ON CONFLICT (player_id) DO UPDATE SET email = EXCLUDED.email"), {"pid": pid, "email": (email or "").strip()})
    op.drop_table("player_emails")
    op.rename_table("player_emails_new", "player_emails")

    # 6. decks: player_id NOT NULL, drop (event_id, player) unique, add (event_id, player_id) unique
    op.drop_constraint("uq_decks_event_id_player", "decks", type_="unique")
    # Set any remaining null player_id to a sentinel "(unknown)" player
    conn.execute(sa.text("INSERT INTO players (display_name) VALUES ('(unknown)') ON CONFLICT (display_name) DO NOTHING"))
    unknown_id = conn.execute(sa.text("SELECT id FROM players WHERE display_name = '(unknown)'")).scalar()
    if unknown_id is not None:
        conn.execute(sa.text("UPDATE decks SET player_id = :uid WHERE player_id IS NULL"), {"uid": unknown_id})
    op.alter_column(
        "decks",
        "player_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_unique_constraint("uq_decks_event_id_player_id", "decks", ["event_id", "player_id"])

    # 7. matchups.opponent_player_id
    op.add_column("matchups", sa.Column("opponent_player_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_matchups_opponent_player_id",
        "matchups",
        "players",
        ["opponent_player_id"],
        ["id"],
    )
    alias_to_pid = {r[0]: r[1] for r in conn.execute(sa.text("SELECT alias, player_id FROM player_aliases")).fetchall()}
    display_to_pid = {r[1]: r[0] for r in conn.execute(sa.text("SELECT id, display_name FROM players")).fetchall()}
    matchup_rows = conn.execute(sa.text("SELECT id, opponent_player FROM matchups")).fetchall()
    for (mid, opp) in matchup_rows:
        opp = (opp or "").strip()
        if opp in ("Bye", "(drop)", ""):
            continue
        pid = alias_to_pid.get(opp)
        if pid is None:
            pid = display_to_pid.get(opp)
        if pid is None:
            conn.execute(sa.text("INSERT INTO players (display_name) VALUES (:name) ON CONFLICT (display_name) DO NOTHING"), {"name": opp})
            row = conn.execute(sa.text("SELECT id FROM players WHERE display_name = :name"), {"name": opp}).fetchone()
            if row:
                pid = row[0]
                display_to_pid[opp] = pid
        if pid is not None:
            conn.execute(sa.text("UPDATE matchups SET opponent_player_id = :pid WHERE id = :mid"), {"pid": pid, "mid": mid})


def downgrade() -> None:
    conn = op.get_bind()

    # 7. Remove matchups.opponent_player_id
    op.drop_constraint("fk_matchups_opponent_player_id", "matchups", type_="foreignkey")
    op.drop_column("matchups", "opponent_player_id")

    # 6. decks: drop (event_id, player_id) unique, add (event_id, player) unique, player_id nullable
    op.drop_constraint("uq_decks_event_id_player_id", "decks", type_="unique")
    op.alter_column("decks", "player_id", existing_type=sa.Integer(), nullable=True)
    op.create_unique_constraint("uq_decks_event_id_player", "decks", ["event_id", "player"])

    # 5. Restore player_emails (player string)
    op.create_table(
        "player_emails_old",
        sa.Column("player", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("player"),
    )
    rows = conn.execute(sa.text("SELECT player_id, email FROM player_emails")).fetchall()
    for (pid, email) in rows:
        name_row = conn.execute(sa.text("SELECT display_name FROM players WHERE id = :pid"), {"pid": pid}).fetchone()
        if name_row:
            conn.execute(sa.text("INSERT INTO player_emails_old (player, email) VALUES (:player, :email)"), {"player": name_row[0], "email": email or ""})
    op.drop_table("player_emails")
    op.rename_table("player_emails_old", "player_emails")

    # 4. Restore player_aliases (alias, canonical)
    op.create_table(
        "player_aliases_old",
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("canonical", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("alias"),
    )
    rows = conn.execute(sa.text("SELECT alias, player_id FROM player_aliases")).fetchall()
    for (alias_val, pid) in rows:
        name_row = conn.execute(sa.text("SELECT display_name FROM players WHERE id = :pid"), {"pid": pid}).fetchone()
        if name_row:
            conn.execute(sa.text("INSERT INTO player_aliases_old (alias, canonical) VALUES (:alias, :canonical)"), {"alias": alias_val, "canonical": name_row[0]})
    op.drop_table("player_aliases")
    op.rename_table("player_aliases_old", "player_aliases")

    # 2+3. Remove decks.player_id (decks.player already has display name from backfill; no revert of denormalized player)
    op.drop_constraint("fk_decks_player_id", "decks", type_="foreignkey")
    op.drop_column("decks", "player_id")

    # 1. Drop players
    op.drop_table("players")
