from __future__ import annotations

"""
One-off maintenance script to merge duplicate players that only differ by accents/case.

It uses the same normalization logic as api.db._normalize_name_for_lookup and
api.db.merge_players for each duplicate (repoints all references, then deletes
the merged-away PlayerRow). Old display names are registered as player_aliases.

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

    for dup_id, dup_name in zip(dup_ids, cluster.names[1:], strict=True):
        dup_row = _db.get_player_by_id(session, dup_id)
        if not dup_row:
            print(f"    Skip id={dup_id}: row already gone")
            continue
        print(f"    Merge id={dup_id} name={dup_row.display_name!r} -> canonical (delete source row after repoint)")
        _db.merge_players(
            session,
            from_player_id=dup_id,
            to_player_id=canonical_id,
            canonical_name=canonical_name,
        )
        alias = (dup_name or "").strip()
        if alias and alias != canonical_name:
            _db.set_player_alias(session, alias, canonical_name)


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

