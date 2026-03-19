"""
Maintenance script to reduce "(unknown)" archetypes in the matchups matrix.

The matrix uses:
- deck archetype from `decks.archetype`
- opponent archetype from `matchups.opponent_archetype`

If `decks.archetype` is NULL/empty/"(unknown)", the matrix will show "(unknown)"
even when matchups contain the opponent archetype.

This script backfills `decks.archetype` from `matchups.opponent_archetype` by:
- finding decks where archetype is missing/unknown
- collecting non-unknown opponent_archetype values from matchups where that deck
  appears as `opponent_deck_id`
- if there is exactly one distinct (case-insensitive) archetype value, we copy it
  into `decks.archetype`.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
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


def _is_unknown(s: str | None) -> bool:
    t = (s or "").strip()
    if not t:
        return True
    return t.lower() == "(unknown)"


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

    with _db.session_scope() as session:
        from sqlalchemy import func, or_

        missing_deck_ids = [
            did
            for (did,) in session.query(_db.DeckRow.deck_id)
            .filter(
                or_(
                    _db.DeckRow.archetype.is_(None),
                    func.trim(_db.DeckRow.archetype) == "",
                    func.lower(func.trim(_db.DeckRow.archetype)) == "(unknown)",
                )
            )
            .all()
        ]

        print(f"Missing/unknown deck archetypes: {len(missing_deck_ids)}")
        if not missing_deck_ids:
            return

        # Count candidate opponent archetypes per opponent_deck_id.
        q = (
            session.query(_db.MatchupRow.opponent_deck_id, _db.MatchupRow.opponent_archetype, func.count())
            .filter(_db.MatchupRow.opponent_deck_id.in_(missing_deck_ids))
            .filter(
                or_(
                    _db.MatchupRow.opponent_archetype.isnot(None),
                    func.trim(_db.MatchupRow.opponent_archetype) != "",
                )
            )
            .group_by(_db.MatchupRow.opponent_deck_id, _db.MatchupRow.opponent_archetype)
        )

        # Python-side filtering/normalization so we can treat case-insensitive duplicates as one.
        counts: dict[int, dict[str, tuple[str, int]]] = defaultdict(dict)
        for did, opp_arch, cnt in q.all():
            if did is None:
                continue
            if _is_unknown(opp_arch):
                continue
            rep = (opp_arch or "").strip()
            key = rep.lower()
            # Keep representative spelling + highest count
            existing = counts[did].get(key)
            if existing is None or cnt > existing[1]:
                counts[did][key] = (rep, int(cnt))

        updated = 0
        skipped_multi = 0
        skipped_none = 0

        for did in missing_deck_ids:
            by_lower = counts.get(did) or {}
            distinct_lower = list(by_lower.keys())
            if not distinct_lower:
                skipped_none += 1
                continue
            if len(distinct_lower) != 1:
                skipped_multi += 1
                continue

            desired_rep, _cnt = by_lower[distinct_lower[0]]
            deck_row = session.query(_db.DeckRow).filter(_db.DeckRow.deck_id == did).first()
            if not deck_row:
                continue

            if _is_unknown(deck_row.archetype):
                if args.apply:
                    deck_row.archetype = desired_rep
                updated += 1

        mode = "DRY-RUN" if args.dry_run else "APPLY"
        print(f"[{mode}] decks that would be (or were) filled: {updated}")
        print(f"[{mode}] skipped (no candidate archetypes): {skipped_none}")
        print(f"[{mode}] skipped (multiple distinct archetypes found): {skipped_multi}")

        if args.apply:
            print("Done.")


if __name__ == "__main__":
    main()

