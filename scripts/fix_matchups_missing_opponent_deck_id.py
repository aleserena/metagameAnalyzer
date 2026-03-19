"""
Maintenance script to fix "(unknown)" archetypes in the matchups matrix.

Root cause observed:
- Some MatchupRow records have result="win|loss|draw" (so they are included in the matrix)
- but `opponent_deck_id` is NULL.
- When `opponent_deck_id` is NULL, `matchups.opponent_archetype` stays NULL/empty,
  and the matrix defaults it to "(unknown)".

Fix strategy:
- For MatchupRow rows where `opponent_deck_id` is NULL and `opponent_player_id` is present,
  determine the event of the "our" deck (via `decks.event_id` on `deck_id`)
-  then find the opponent deck in the same event by matching `decks.player_id == opponent_player_id`
-  and update:
    - matchups.opponent_deck_id
    - matchups.opponent_archetype (copied from the opponent deck's decks.archetype when available)

Run:
  python3 -m scripts.fix_matchups_missing_opponent_deck_id --dry-run
  python3 -m scripts.fix_matchups_missing_opponent_deck_id --apply
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


def _trim(s: str | None) -> str:
    return (s or "").strip()


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
        from sqlalchemy import func

        # Rows that can be fixed by finding the opponent deck in the same event.
        need_rows = (
            session.query(
                _db.MatchupRow.id,
                _db.MatchupRow.deck_id,
                _db.MatchupRow.opponent_player_id,
                _db.MatchupRow.opponent_player,
                _db.MatchupRow.result,
                _db.MatchupRow.round,
                _db.MatchupRow.opponent_deck_id,
                _db.MatchupRow.opponent_archetype,
            )
            .filter(_db.MatchupRow.opponent_deck_id.is_(None))
            .filter(_db.MatchupRow.opponent_player_id.isnot(None))
            .all()
        )

        print(f"Matchup rows needing fix (opponent_deck_id is NULL but opponent_player_id set): {len(need_rows)}")
        if not need_rows:
            return

        my_deck_ids = {r.deck_id for r in need_rows if r.deck_id is not None}
        my_decks = session.query(_db.DeckRow.deck_id, _db.DeckRow.event_id).filter(_db.DeckRow.deck_id.in_(my_deck_ids)).all()
        my_event_by_deck_id = {d.deck_id: d.event_id for d in my_decks}

        event_ids = {my_event_by_deck_id.get(did) for did in my_deck_ids if my_event_by_deck_id.get(did) is not None}

        # Opponent deck lookup within each event: (event_id, player_id) -> (deck_id, archetype)
        deck_lookup = {}
        opp_decks = (
            session.query(_db.DeckRow.event_id, _db.DeckRow.player_id, _db.DeckRow.deck_id, _db.DeckRow.archetype)
            .filter(_db.DeckRow.event_id.in_(event_ids))
            .all()
        )
        for d in opp_decks:
            deck_lookup[(d.event_id, d.player_id)] = (d.deck_id, d.archetype)

        updated = 0
        not_found = 0
        filled_arch_missing = 0

        for r in need_rows:
            event_id = my_event_by_deck_id.get(r.deck_id)
            if not event_id or r.opponent_player_id is None:
                continue
            key = (event_id, r.opponent_player_id)
            opp = deck_lookup.get(key)
            if not opp:
                not_found += 1
                continue
            opp_deck_id, opp_arch = opp

            desired_arch = _trim(opp_arch)
            if not desired_arch:
                filled_arch_missing += 1

            if args.apply:
                m = session.query(_db.MatchupRow).filter(_db.MatchupRow.id == r.id).first()
                if not m:
                    continue
                m.opponent_deck_id = opp_deck_id
                if desired_arch:
                    m.opponent_archetype = desired_arch
            updated += 1

        mode = "DRY-RUN" if args.dry_run else "APPLY"
        print(f"[{mode}] would update: {updated}")
        print(f"[{mode}] opponent deck not found for: {not_found}")
        print(f"[{mode}] opponent deck found but archetype missing/blank for: {filled_arch_missing}")
        if args.apply:
            print("Done.")


if __name__ == "__main__":
    main()

