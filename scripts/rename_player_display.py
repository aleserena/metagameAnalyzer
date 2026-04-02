"""
Rename a player's canonical display name in PostgreSQL (players.display_name) and
sync denormalized decks.player, matchup opponent strings, and inverse rows.

Use on production (Railway) after SSH/shell with DATABASE_URL, or locally against a copy.

Examples:
  python3 -m scripts.rename_player_display --player-id 43 --to "Pedro Picco" --dry-run
  python3 -m scripts.rename_player_display --player-id 43 --to "Pedro Picco" --apply

After --apply, restart the API or reload decks so in-memory caches pick up deck.player changes.
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player-id", type=int, required=True)
    parser.add_argument("--to", dest="new_name", required=True, help="New display name")
    parser.add_argument(
        "--no-alias",
        action="store_true",
        help="Do not register the old name as a player_aliases pointer to this player",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")
    if args.dry_run and args.apply:
        parser.error("Use only one of --dry-run or --apply")

    _load_env()
    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    factory = _db.get_session_factory_cached()
    if factory is None:
        raise RuntimeError("Database session factory unavailable")

    if args.dry_run:
        session = factory()
        try:
            prow = _db.get_player_by_id(session, args.player_id)
            if not prow:
                raise SystemExit(f"No player with id={args.player_id}")
            old = (prow.display_name or "").strip()
            conflict = (
                session.query(_db.PlayerRow)
                .filter(
                    _db.PlayerRow.display_name == args.new_name.strip(),
                    _db.PlayerRow.id != args.player_id,
                )
                .first()
            )
            out = {
                "dry_run": True,
                "player_id": args.player_id,
                "current_name": old,
                "new_name": args.new_name.strip(),
                "would_conflict_with_player_id": conflict.id if conflict else None,
            }
            print(json.dumps(out, indent=2, ensure_ascii=False))
        finally:
            session.rollback()
            session.close()
        return

    with _db.session_scope() as session:
        summary = _db.rename_player_display_name(
            session,
            args.player_id,
            args.new_name,
            add_alias_for_old_name=not args.no_alias,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("Done. Restart the API (or reload decks) so cached deck lists show the new name.")


if __name__ == "__main__":
    main()
