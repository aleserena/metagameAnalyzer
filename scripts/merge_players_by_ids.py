"""
Maintenance script: merge one or more player rows into a canonical player by **id**
(same outcome as `fix_player_names.py`, but no name lookup).

Uses `api.db.merge_players`: repoints decks, matchups, emails, aliases, then
deletes each merged-away `PlayerRow`.

Usage (DATABASE_URL in env or `.env`):

    python3 -m scripts.merge_players_by_ids --merge-from 101 102 --to 42 --dry-run
    python3 -m scripts.merge_players_by_ids --merge-from 101 102 --to 42 --apply

Optional:

    --canonical-name "Jane Doe"   # override string written to decks/matchups
    --no-alias                    # skip registering old display names in player_aliases
"""

from __future__ import annotations

import argparse
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


def _count_decks(session, player_id: int) -> int:
    return session.query(_db.DeckRow).filter(_db.DeckRow.player_id == player_id).count()


def _count_matchups_opponent(session, player_id: int) -> int:
    return (
        session.query(_db.MatchupRow)
        .filter(_db.MatchupRow.opponent_player_id == player_id)
        .count()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge player rows by id into a canonical player.")
    parser.add_argument(
        "--merge-from",
        nargs="+",
        type=int,
        metavar="ID",
        required=True,
        help="Player id(s) to remove after merging their data into --to",
    )
    parser.add_argument(
        "--to",
        type=int,
        required=True,
        help="Canonical player id to keep",
    )
    parser.add_argument(
        "--canonical-name",
        help="Display string for decks/matchups after merge (default: target player's display_name)",
    )
    parser.add_argument(
        "--no-alias",
        action="store_true",
        help="Do not add player_aliases for merged-away display names",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show plan only")
    parser.add_argument("--apply", action="store_true", help="Write changes")
    args = parser.parse_args()

    _load_env()

    if not args.dry_run and not args.apply:
        parser.error("Specify either --dry-run or --apply")

    merge_from = list(dict.fromkeys(args.merge_from))
    to_id = args.to

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    with _db.session_scope() as session:
        to_row = _db.get_player_by_id(session, to_id)
        if not to_row:
            raise SystemExit(f"No player row with id={to_id}; cannot merge into missing target.")

        canonical_display = (args.canonical_name or "").strip() or (
            (to_row.display_name or "").strip() or "(unknown)"
        )

        print(f"Target: id={to_id} display_name={to_row.display_name!r}")
        print(f"Effective canonical display for merged rows: {canonical_display!r}")

        to_merge = [fid for fid in merge_from if fid != to_id]
        if not to_merge:
            print("Nothing to merge (all --merge-from ids equal --to or empty).")
            return

        for fid in to_merge:
            from_row = _db.get_player_by_id(session, fid)
            if not from_row:
                print(f"Skip id={fid}: no such player row.")
                continue
            old_name = (from_row.display_name or "").strip()
            decks_n = _count_decks(session, fid)
            matchups_n = _count_matchups_opponent(session, fid)
            print(
                f"\nMerge from id={fid} name={from_row.display_name!r} "
                f"(decks={decks_n}, matchups_as_opponent={matchups_n}) -> id={to_id}"
            )
            if args.dry_run:
                continue
            _db.merge_players(
                session,
                from_player_id=fid,
                to_player_id=to_id,
                canonical_name=canonical_display,
            )
            session.flush()
            if _db.get_player_by_id(session, fid) is not None:
                raise RuntimeError(
                    f"merge_players did not remove player id={fid}; check DB constraints and merge_players."
                )
            print(f"    Deleted merged-away player row id={fid}.")
            if not args.no_alias and old_name and old_name != canonical_display:
                _db.set_player_alias(session, old_name, canonical_display)

        if args.dry_run:
            print("\nDry-run complete; no changes written.")
            return

        print(
            f"\nDone. Canonical id={to_id} now has "
            f"decks={_count_decks(session, to_id)}, "
            f"matchups_as_opponent={_count_matchups_opponent(session, to_id)}."
        )


if __name__ == "__main__":
    main()
