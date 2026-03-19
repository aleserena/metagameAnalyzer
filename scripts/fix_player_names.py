"""
One-off maintenance script to fix a player name typo:

- "Gustavo Rupulo" -> "Gustavo Rupolo"

It merges the player row for the alias name into the canonical player row, so all
related data (decks and matchups, and therefore event coverage via decks) is combined.

Usage:
  python3 -m scripts.fix_gustavo_rupolo --dry-run
  python3 -m scripts.fix_gustavo_rupolo --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path

from api import db as _db


DEFAULT_ALIAS = "Gustavo Rupulo"
DEFAULT_CANONICAL = "Gustavo Rupolo"


def _load_env() -> None:
    """Best-effort load of project .env so DATABASE_URL is available for this script."""
    project_root = Path(__file__).resolve().parent.parent
    env_base = project_root / ".env"
    if not env_base.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_base, override=False)
    except Exception:
        # If python-dotenv isn't installed, we just rely on DATABASE_URL being set already.
        return


def _count_decks_for_player(session, player_id: int) -> int:
    return session.query(_db.DeckRow).filter(_db.DeckRow.player_id == player_id).count()


def _count_matchups_where_opponent_player(session, player_id: int) -> int:
    return session.query(_db.MatchupRow).filter(_db.MatchupRow.opponent_player_id == player_id).count()


def _find_player_by_exact_display_name(session, display_name: str):
    display_name = (display_name or "").strip()
    if not display_name:
        return None
    return (
        session.query(_db.PlayerRow)
        .filter(_db.PlayerRow.display_name == display_name)
        .first()
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alias", default=DEFAULT_ALIAS, help="Alias display name to merge")
    parser.add_argument("--canonical", default=DEFAULT_CANONICAL, help="Canonical display name")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, but do nothing")
    parser.add_argument("--apply", action="store_true", help="Apply the merge (writes to DB)")
    args = parser.parse_args()

    _load_env()

    if not args.dry_run and not args.apply:
        parser.error("Specify either --dry-run or --apply")

    alias = (args.alias or "").strip()
    canonical = (args.canonical or "").strip()
    if not alias or not canonical:
        raise SystemExit("Both --alias and --canonical must be non-empty")

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    with _db.session_scope() as session:
        alias_row = _find_player_by_exact_display_name(session, alias)
        canonical_row = _find_player_by_exact_display_name(session, canonical)

        if not alias_row:
            print(f"No player row found with display_name={alias!r}; nothing to merge.")
            return

        if canonical_row:
            canonical_id = canonical_row.id
            canonical_effective_display = (canonical_row.display_name or "").strip() or canonical
        else:
            if args.dry_run:
                print(f"Canonical row display_name={canonical!r} not found; dry-run would create it.")
                canonical_effective_display = canonical
                canonical_id = None
            else:
                canonical_id, canonical_effective_display = _db.get_or_create_player(session, canonical)
                canonical_row = _find_player_by_exact_display_name(session, canonical_effective_display)

        alias_id = alias_row.id
        print(f"Alias: id={alias_id} name={alias_row.display_name!r}")
        if canonical_row:
            print(f"Canonical: id={canonical_row.id} name={canonical_row.display_name!r}")
        else:
            print(f"Canonical: (missing) name={canonical!r}")

        if canonical_id is not None and alias_id == canonical_id:
            print("Alias and canonical already point to the same player row; nothing to do.")
            return

        decks_before = _count_decks_for_player(session, alias_id)
        matchups_before = _count_matchups_where_opponent_player(session, alias_id)
        print(f"Related decks before: {decks_before}")
        print(f"Related matchups (as opponent) before: {matchups_before}")

        if args.dry_run:
            if canonical_id is None:
                print("Dry-run complete (no merge executed).")
                return
            print("Dry-run: merge would happen and alias would be added to player_aliases.")
            return

        # Merge and then ensure alias resolves to canonical.
        if canonical_id is None:
            raise RuntimeError("Internal error: expected canonical_id to exist in --apply mode.")

        _db.merge_players(
            session,
            from_player_id=alias_id,
            to_player_id=canonical_id,
            canonical_name=canonical_effective_display,
        )
        _db.set_player_alias(session, alias, canonical_effective_display)

        decks_after = _count_decks_for_player(session, canonical_id)
        matchups_after = _count_matchups_where_opponent_player(session, canonical_id)
        print(f"Done. Related decks now on canonical: {decks_after}")
        print(f"Related matchups (as opponent) now on canonical: {matchups_after}")


if __name__ == "__main__":
    main()

