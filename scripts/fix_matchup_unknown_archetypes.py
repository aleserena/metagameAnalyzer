"""
Maintenance script to fix "(unknown)" archetypes in the matchups matrix.

The matchups matrix (see api/main.py) aggregates by:
- deck archetype: `decks.archetype`
- opponent archetype: `matchups.opponent_archetype`

When `matchups.opponent_archetype` is NULL/empty/"(unknown)", the matrix shows
"(unknown)" even if the opponent deck has a known archetype.

This script backfills `matchups.opponent_archetype` from the opponent deck's
`decks.archetype` using `matchups.opponent_deck_id`.

Run with:
  python3 -m scripts.fix_matchup_unknown_archetypes --dry-run
  python3 -m scripts.fix_matchup_unknown_archetypes --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path

from api import db as _db


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
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, but do nothing")
    parser.add_argument("--apply", action="store_true", help="Apply the fix (writes to DB)")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify either --dry-run or --apply")

    _load_env()

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    # Avoid heavy updates: only touch opponent_archetype that are missing/unknown,
    # and only fill when opponent deck has a non-empty archetype.
    with _db.session_scope() as session:
        from sqlalchemy import and_, func, or_

        q = (
            session.query(_db.MatchupRow, _db.DeckRow.archetype)
            .outerjoin(_db.DeckRow, _db.DeckRow.deck_id == _db.MatchupRow.opponent_deck_id)
            .filter(_db.MatchupRow.opponent_deck_id.isnot(None))
            .filter(
                or_(
                    _db.MatchupRow.opponent_archetype.is_(None),
                    func.trim(_db.MatchupRow.opponent_archetype) == "",
                    func.lower(func.trim(_db.MatchupRow.opponent_archetype)) == "(unknown)",
                )
            )
        )

        candidates = q.all()
        total_candidates = len(candidates)
        updated = 0
        filled_with = {}

        for m, opp_arch in candidates:
            desired = (opp_arch or "").strip()
            if not desired:
                continue
            if not args.apply:
                updated += 1
                filled_with[desired] = filled_with.get(desired, 0) + 1
                continue

            m.opponent_archetype = desired
            updated += 1
            filled_with[desired] = filled_with.get(desired, 0) + 1

        mode = "DRY-RUN" if args.dry_run else "APPLY"
        print(f"[{mode}] candidate rows with missing/unknown opponent_archetype: {total_candidates}")
        print(f"[{mode}] rows that would be filled from decks.archetype: {updated}")
        if filled_with:
            top = sorted(filled_with.items(), key=lambda x: x[1], reverse=True)[:10]
            print(f"[{mode}] top archetypes used for filling (up to 10): {top}")

        if args.apply:
            print("Done.")


if __name__ == "__main__":
    main()

