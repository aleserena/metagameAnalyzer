"""
Maintenance script to fix "(unknown)" archetypes in the matchups matrix.

Root cause observed:
- Some MatchupRow records have result="win|loss|draw" (so they are included in the matrix)
- but `opponent_deck_id` is NULL.
- When `opponent_deck_id` is NULL, `matchups.opponent_archetype` stays NULL/empty,
  and the matrix defaults it to "(unknown)".

Fix strategy:
- For MatchupRow rows where `opponent_deck_id` is NULL and `opponent_player_id` is present,
  determine the event of the "our" deck (via `decks.event_id` on `deck_id`).
- Resolve the opponent's deck in that event, in order:
  1. `decks.player_id == opponent_player_id` (primary).
  2. Else: exactly one deck in the event whose normalized `decks.player` matches normalized
     `matchups.opponent_player` (handles duplicate player rows / ID drift).
  3. Else: exactly one deck in the event whose normalized `decks.player` matches normalized
     `players.display_name` for `opponent_player_id` (handles short vs full name on the row).
- Then update `matchups.opponent_deck_id` and `opponent_archetype` when the opponent deck has an archetype.

Run:
  python3 -m scripts.fix_matchups_missing_opponent_deck_id --dry-run
  python3 -m scripts.fix_matchups_missing_opponent_deck_id --dry-run --verbose
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


def _norm_player_label(s: str | None) -> str:
    return _db._normalize_name_for_lookup(_db._front_face_name(s or ""))


def _decks_matching_norm_in_event(
    target_norm: str,
    my_deck_id: int,
    decks_in_event: list[tuple[int, int, str | None, str]],
) -> list[tuple[int, str | None]]:
    """Decks in the same event whose normalized `decks.player` equals target_norm (excludes my_deck_id)."""
    if not target_norm:
        return []
    matches: list[tuple[int, str | None]] = []
    seen: set[int] = set()
    for deck_id, _player_id, archetype, norm_player in decks_in_event:
        if deck_id == my_deck_id or deck_id in seen:
            continue
        if norm_player == target_norm:
            seen.add(deck_id)
            matches.append((deck_id, archetype))
    return matches


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, but do nothing")
    parser.add_argument("--apply", action="store_true", help="Apply the fix (writes to DB)")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print each matchup where no opponent deck exists for (event_id, opponent_player_id)",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify either --dry-run or --apply")

    _load_env()

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    with _db.session_scope() as session:
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
        deck_lookup: dict[tuple[str, int], tuple[int, str | None]] = {}
        opp_decks = (
            session.query(
                _db.DeckRow.event_id,
                _db.DeckRow.player_id,
                _db.DeckRow.deck_id,
                _db.DeckRow.archetype,
                _db.DeckRow.player,
            )
            .filter(_db.DeckRow.event_id.in_(event_ids))
            .all()
        )
        for d in opp_decks:
            deck_lookup[(d.event_id, d.player_id)] = (d.deck_id, d.archetype)

        # event_id -> list of (deck_id, player_id, archetype, norm_player) for name-based fallback
        decks_in_event_lists: dict[str, list[tuple[int, int, str | None, str]]] = {}
        for d in opp_decks:
            norm_p = _norm_player_label(d.player)
            decks_in_event_lists.setdefault(d.event_id, []).append(
                (d.deck_id, d.player_id, d.archetype, norm_p)
            )

        # event_id -> set of player_ids that have a deck in that event (for verbose hints)
        players_with_deck_by_event: dict[str, set[int]] = {}
        for d in opp_decks:
            players_with_deck_by_event.setdefault(d.event_id, set()).add(d.player_id)

        opp_player_ids = {r.opponent_player_id for r in need_rows if r.opponent_player_id is not None}
        display_by_player_id: dict[int, str] = {}
        if opp_player_ids:
            for prow in session.query(_db.PlayerRow).filter(_db.PlayerRow.id.in_(opp_player_ids)).all():
                display_by_player_id[prow.id] = prow.display_name or ""

        updated = 0
        updated_by_player_id = 0
        updated_by_matchup_name = 0
        updated_by_canonical_name = 0
        ambiguous_name = 0
        not_found = 0
        filled_arch_missing = 0

        for r in need_rows:
            event_id = my_event_by_deck_id.get(r.deck_id)
            if not event_id or r.opponent_player_id is None:
                continue
            key = (event_id, r.opponent_player_id)
            opp = deck_lookup.get(key)
            resolution = "player_id"
            decks_for_event = decks_in_event_lists.get(event_id, [])

            if not opp:
                norm_from_row = _norm_player_label(r.opponent_player)
                row_name_hits = _decks_matching_norm_in_event(norm_from_row, r.deck_id, decks_for_event)
                if len(row_name_hits) == 1:
                    opp = row_name_hits[0]
                    resolution = "matchup_opponent_name"
                elif len(row_name_hits) > 1:
                    ambiguous_name += 1
                    if args.verbose:
                        print(
                            f"  ambiguous matchup_id={r.id} event_id={event_id!r}: "
                            f"multiple decks match opponent_player={r.opponent_player!r}"
                        )
                    continue
                else:
                    canon = display_by_player_id.get(r.opponent_player_id, "")
                    norm_canon = _norm_player_label(canon)
                    canon_hits = _decks_matching_norm_in_event(norm_canon, r.deck_id, decks_for_event)
                    if len(canon_hits) == 1:
                        opp = canon_hits[0]
                        resolution = "player_display_name"
                    elif len(canon_hits) > 1:
                        ambiguous_name += 1
                        if args.verbose:
                            print(
                                f"  ambiguous matchup_id={r.id} event_id={event_id!r}: "
                                f"multiple decks match players.display_name id={r.opponent_player_id!r}"
                            )
                        continue
                    else:
                        not_found += 1
                        if args.verbose:
                            in_event = players_with_deck_by_event.get(event_id, set())
                            hint = (
                                f" ({len(in_event)} distinct player_ids have a deck in this event)"
                                if in_event
                                else " (no decks loaded for this event)"
                            )
                            print(
                                f"  not_found matchup_id={r.id} my_deck_id={r.deck_id} event_id={event_id!r} "
                                f"opponent_player_id={r.opponent_player_id} opponent_player={r.opponent_player!r}{hint}"
                            )
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
            if resolution == "player_id":
                updated_by_player_id += 1
            elif resolution == "matchup_opponent_name":
                updated_by_matchup_name += 1
            else:
                updated_by_canonical_name += 1

        mode = "DRY-RUN" if args.dry_run else "APPLY"
        print(f"[{mode}] would update: {updated}")
        print(
            f"[{mode}]   by (event, opponent_player_id): {updated_by_player_id}; "
            f"by matchup opponent name in event: {updated_by_matchup_name}; "
            f"by players.display_name in event: {updated_by_canonical_name}"
        )
        print(f"[{mode}] ambiguous (multiple decks matched same name): {ambiguous_name}")
        print(f"[{mode}] opponent deck not found for: {not_found}")
        print(f"[{mode}] opponent deck found but archetype missing/blank for: {filled_arch_missing}")
        if args.apply:
            print("Done.")


if __name__ == "__main__":
    main()

