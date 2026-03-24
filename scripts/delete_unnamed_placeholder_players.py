#!/usr/bin/env python3
"""
Remove blank-deck placeholder *players* (Unnamed, Unnamed 9, Unnamed9, …) and dependent data.

This deletes:
- All matchups where `opponent_player_id` is one of those players
- All decks whose `player_id` is one of those players (DB cascades delete their matchups)
- `player_aliases` and `player_emails` rows for those player ids
- The `players` rows themselves

Does **not** delete `(unknown)` or any non-placeholder display name.

Run from project root with DATABASE_URL (e.g. in .env):

  python3 -m scripts.delete_unnamed_placeholder_players --dry-run
  python3 -m scripts.delete_unnamed_placeholder_players --dry-run --verbose
  python3 -m scripts.delete_unnamed_placeholder_players --apply

After --apply, restart the API / reload decks so in-memory caches refresh.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from api import db as _db

_PLACEHOLDER_RE = re.compile(r"^Unnamed\s*\d*$", re.IGNORECASE)


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


def is_placeholder_display_name(name: str | None) -> bool:
    s = (name or "").strip()
    return bool(_PLACEHOLDER_RE.fullmatch(s))


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete Unnamed* placeholder players and dependent rows.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be deleted")
    parser.add_argument("--apply", action="store_true", help="Perform deletions")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print per-id / per-deck detail")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify either --dry-run or --apply")

    _load_env()

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    with _db.session_scope() as session:
        candidates = session.query(_db.PlayerRow).order_by(_db.PlayerRow.id).all()
        placeholder_rows = [p for p in candidates if is_placeholder_display_name(p.display_name)]
        ids = [p.id for p in placeholder_rows]

        if not ids:
            print("No placeholder players (Unnamed / Unnamed N) found; nothing to do.")
            return

        print(f"Placeholder players to remove: {len(ids)}")
        if args.verbose:
            for p in placeholder_rows:
                print(f"  player id={p.id} display_name={p.display_name!r}")

        n_matchups_opp = (
            session.query(_db.MatchupRow).filter(_db.MatchupRow.opponent_player_id.in_(ids)).count()
        )
        decks = (
            session.query(_db.DeckRow)
            .filter(_db.DeckRow.player_id.in_(ids))
            .order_by(_db.DeckRow.deck_id)
            .all()
        )
        n_aliases = session.query(_db.PlayerAliasRow).filter(_db.PlayerAliasRow.player_id.in_(ids)).count()
        n_emails = session.query(_db.PlayerEmailRow).filter(_db.PlayerEmailRow.player_id.in_(ids)).count()
        deck_ids_preview = [d.deck_id for d in decks]
        n_upload_links = (
            session.query(_db.EventUploadLinkRow)
            .filter(_db.EventUploadLinkRow.deck_id.in_(deck_ids_preview))
            .count()
            if deck_ids_preview
            else 0
        )

        print(f"  matchups (opponent_player_id in set): {n_matchups_opp}")
        print(f"  decks (player_id in set): {len(decks)}")
        print(f"  player_aliases rows: {n_aliases}")
        print(f"  player_emails rows: {n_emails}")
        print(f"  event_upload_links (deck_id will be nulled): {n_upload_links}")

        if args.verbose and decks:
            for d in decks:
                print(
                    f"  deck deck_id={d.deck_id} event_id={d.event_id!r} "
                    f"player_id={d.player_id} player={d.player!r}"
                )

        mode = "DRY-RUN" if args.dry_run else "APPLY"
        print(f"[{mode}] {'would delete' if args.dry_run else 'deleting'} the above")

        if not args.apply:
            return

        # 1) Opponent references must be cleared before players row delete (FK).
        session.query(_db.MatchupRow).filter(_db.MatchupRow.opponent_player_id.in_(ids)).delete(
            synchronize_session=False
        )

        # 2) Upload links may still reference deck_id without a DB FK — clear before deck delete.
        if deck_ids_preview:
            session.query(_db.EventUploadLinkRow).filter(
                _db.EventUploadLinkRow.deck_id.in_(deck_ids_preview)
            ).update({"deck_id": None}, synchronize_session=False)

        # 3) Decks owned by placeholder players (matchups on those decks cascade at DB level).
        for d in decks:
            _db.delete_deck(session, d.deck_id)

        session.query(_db.PlayerAliasRow).filter(_db.PlayerAliasRow.player_id.in_(ids)).delete(
            synchronize_session=False
        )
        session.query(_db.PlayerEmailRow).filter(_db.PlayerEmailRow.player_id.in_(ids)).delete(
            synchronize_session=False
        )

        session.query(_db.PlayerRow).filter(_db.PlayerRow.id.in_(ids)).delete(synchronize_session=False)

        print("Done. Restart the API or reload data so caches see the changes.")


if __name__ == "__main__":
    main()
