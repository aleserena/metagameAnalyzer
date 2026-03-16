from __future__ import annotations

"""
One-off maintenance script to merge duplicate players that only differ by accents/case.

It uses the same normalization logic as api.db._normalize_name_for_lookup and updates:
- decks.player_id / decks.player
- matchups.opponent_player_id / matchups.opponent_player
- player_emails.player_id
- player_aliases.alias -> canonical player_id

Usage (with DATABASE_URL configured, e.g. in your shell or .env loaded):

    python3 -m scripts.fix_duplicate_players

This will:
- Scan all players
- Group by normalized name
- For each group with >1 player:
  - Keep the lowest id as canonical
  - Repoint references from other ids to the canonical id
  - Create aliases for old display names
  - Delete the extra PlayerRow entries
"""

from dataclasses import dataclass
from typing import Dict, List

from api import db as _db


@dataclass
class PlayerCluster:
    norm: str
    ids: list[int]
    names: list[str]


def find_duplicate_clusters(session) -> list[PlayerCluster]:
    """Return clusters of players that share the same normalized name and have >1 row."""
    players = session.query(_db.PlayerRow).all()
    by_norm: Dict[str, List[_db.PlayerRow]] = {}
    for p in players:
        name = (p.display_name or "").strip()
        if not name:
            continue
        norm = _db._normalize_name_for_lookup(name)
        if not norm:
            continue
        by_norm.setdefault(norm, []).append(p)

    clusters: list[PlayerCluster] = []
    for norm, rows in by_norm.items():
        if len(rows) <= 1:
            continue
        rows_sorted = sorted(rows, key=lambda r: r.id)
        clusters.append(
            PlayerCluster(
                norm=norm,
                ids=[r.id for r in rows_sorted],
                names=[(r.display_name or "").strip() for r in rows_sorted],
            )
        )
    return clusters


def merge_cluster(session, cluster: PlayerCluster) -> None:
    """Merge all players in this cluster into the canonical (lowest id) player."""
    canonical_id = cluster.ids[0]
    canonical_row = _db.get_player_by_id(session, canonical_id)
    canonical_name = (canonical_row.display_name or "").strip() or "(unknown)" if canonical_row else "(unknown)"

    dup_ids = cluster.ids[1:]
    if not dup_ids:
        return

    print(f"  Canonical id={canonical_id}, name={canonical_name!r}")
    print(f"  Duplicate ids={dup_ids}, names={cluster.names[1:]}")

    # 1) decks: move player_id and player name to canonical
    decks = session.query(_db.DeckRow).filter(_db.DeckRow.player_id.in_(dup_ids)).all()
    for d in decks:
        print(f"    Deck {d.deck_id}: player_id {d.player_id} -> {canonical_id}, player -> {canonical_name!r}")
        d.player_id = canonical_id
        d.player = canonical_name

    # 2) matchups: opponent_player_id / opponent_player
    matchups = session.query(_db.MatchupRow).filter(_db.MatchupRow.opponent_player_id.in_(dup_ids)).all()
    for m in matchups:
        print(
            f"    Matchup {m.id}: opponent_player_id {m.opponent_player_id} -> {canonical_id}, "
            f"opponent_player -> {canonical_name!r}"
        )
        m.opponent_player_id = canonical_id
        m.opponent_player = canonical_name

    # 3) player_emails: move player_id
    email_rows = session.query(_db.PlayerEmailRow).filter(_db.PlayerEmailRow.player_id.in_(dup_ids)).all()
    for e in email_rows:
        print(f"    Email row: player_id {e.player_id} -> {canonical_id}")
        e.player_id = canonical_id

    # 4) aliases: ensure alias rows for all old display names
    for dup_name in cluster.names[1:]:
        alias = (dup_name or "").strip()
        if not alias or alias == canonical_name:
            continue
        existing = (
            session.query(_db.PlayerAliasRow)
            .filter(_db.PlayerAliasRow.alias == alias)
            .first()
        )
        if existing:
            if existing.player_id != canonical_id:
                print(
                    f"    Alias {alias!r}: player_id {existing.player_id} -> {canonical_id}"
                )
                existing.player_id = canonical_id
        else:
            print(f"    Creating alias {alias!r} -> player_id {canonical_id}")
            session.add(_db.PlayerAliasRow(alias=alias, player_id=canonical_id))

    # 5) delete duplicate PlayerRow entries
    for dup_id in dup_ids:
        dup = _db.get_player_by_id(session, dup_id)
        if not dup:
            continue
        print(f"    Deleting player id={dup.id}, name={dup.display_name!r}")
        session.delete(dup)


def main() -> None:
    if not _db.is_database_available():
        raise RuntimeError("Database not available; ensure DATABASE_URL is set and reachable.")

    with _db.session_scope() as session:
        clusters = find_duplicate_clusters(session)
        if not clusters:
            print("No duplicate players found (by normalized name). Nothing to do.")
            return

        print(f"Found {len(clusters)} duplicate player cluster(s).")
        for cluster in clusters:
            print(
                f"\nCluster norm={cluster.norm!r}: ids={cluster.ids}, "
                f"names={cluster.names}"
            )
            merge_cluster(session, cluster)

        print("\nDone. All changes have been committed in this transaction.")


if __name__ == "__main__":
    main()

