"""
Merge duplicate ``players`` rows that are already declared in ``player_aliases``.

For each alias string that maps to canonical ``player_id`` T, if another row exists whose
``display_name`` equals that alias (and id != T), merge that duplicate into T using
``api.db.merge_players`` (same as ``merge_players_by_ids``). That merge repoints decks,
matchups (including inverse rows keyed by ``opponent_deck_id``), emails, and aliases, then
deletes the duplicate player row.

After all merges, by default removes ``player_aliases`` rows that are redundant because the
target player's ``display_name`` already equals the alias (imports still resolve via
``players``). Use ``--keep-redundant-aliases`` to skip that cleanup.

Run with --apply repeatedly until "no merges" if the DB had chained duplicates (rare).

Requires PostgreSQL (``DATABASE_URL``).

Examples:
  python3 -m scripts.merge_alias_duplicate_players --dry-run
  python3 -m scripts.merge_alias_duplicate_players --apply
  python3 -m scripts.merge_alias_duplicate_players --apply --case-insensitive
  python3 -m scripts.merge_alias_duplicate_players --apply --keep-redundant-aliases
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from api import db as _db


def _load_env() -> None:
    project_root = Path(__file__).resolve().parent.parent
    env_base = project_root / ".env"
    if not env_base.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_base, override=False)
    except Exception:
        return


def _pick_merge(
    batch: list[tuple[int, int, str]],
) -> tuple[int, int, str] | None:
    """Prefer (from_id, to_id) where from_id is not a merge target in this batch (chain-safe)."""
    if not batch:
        return None
    tos = {t for _, t, _ in batch}
    for item in batch:
        if item[0] not in tos:
            return item
    return batch[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--case-insensitive",
        action="store_true",
        help="Match alias to display_name with case-insensitive compare",
    )
    parser.add_argument(
        "--keep-redundant-aliases",
        action="store_true",
        help="Do not delete player_aliases rows whose alias equals the target display_name",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")
    if args.dry_run and args.apply:
        parser.error("Use only one of --dry-run or --apply")

    _load_env()
    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    if args.dry_run:
        with _db.session_scope() as session:
            batch = _db.collect_alias_duplicate_player_merges(
                session, case_insensitive=args.case_insensitive
            )
            redundant = _db.list_redundant_player_aliases(
                session, case_insensitive=args.case_insensitive
            )
        report = {
            "dry_run": True,
            "candidates": [
                {
                    "merge_from_player_id": f,
                    "merge_into_player_id": t,
                    "alias": a,
                }
                for f, t, a in batch
            ],
            "count": len(batch),
            "redundant_aliases_would_prune": redundant,
            "redundant_aliases_count": len(redundant),
            "note": (
                "This is a single snapshot. After --apply, run again if new duplicates appear "
                "(chained merges). Redundant-alias list is current DB state; more rows may "
                "become redundant after merges."
            ),
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    total = 0
    rounds: list[dict] = []
    while True:
        with _db.session_scope() as session:
            batch = _db.collect_alias_duplicate_player_merges(
                session, case_insensitive=args.case_insensitive
            )
            if not batch:
                break
            f, t, alias = _pick_merge(batch)
            to_row = _db.get_player_by_id(session, t)
            if not to_row:
                raise RuntimeError(f"Target player id={t} missing")
            canonical = (to_row.display_name or "").strip() or "(unknown)"
            _db.merge_players(session, from_player_id=f, to_player_id=t, canonical_name=canonical)
            if _db.player_row_exists_in_database(session, f):
                raise RuntimeError(f"merge_players did not remove player id={f}")
            rounds.append(
                {
                    "merge_from_player_id": f,
                    "merge_into_player_id": t,
                    "alias": alias,
                    "canonical_display": canonical,
                }
            )
            total += 1

    pruned: list[str] = []
    if not args.keep_redundant_aliases:
        with _db.session_scope() as session:
            pruned = _db.prune_redundant_player_aliases(
                session, case_insensitive=args.case_insensitive
            )

    out = {
        "merges_applied": total,
        "rounds": rounds,
        "aliases_pruned": pruned,
        "aliases_pruned_count": len(pruned),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if total or pruned:
        print(
            "Run again with --dry-run to confirm no remaining alias/duplicate rows; "
            "restart the API after bulk merges."
        )
    else:
        print("No duplicate players found for current player_aliases.")


if __name__ == "__main__":
    main()
