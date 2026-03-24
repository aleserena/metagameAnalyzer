#!/usr/bin/env python3
"""
Merge global `players` rows for blank-deck placeholders (Unnamed, Unnamed 9, …) into the real player
identified per event via the same result-path signature as `fix_unnamed_placeholder_matchups`.

`players.display_name` is unique globally, so one row like "Unnamed 9" may be referenced from many
events. This script only calls `merge_players` when **every** event that references that placeholder
resolves to the **same** canonical `player_id` (via signature → winning deck → deck.player_id).
If different events imply different real people (or signatures are missing), each skipped
placeholder is printed with a reason (no need for --verbose).

Placeholders with **no** deck and **no** matchup opponent reference (orphan rows) are **deleted**
on `--apply` (aliases and emails for that player id are removed first). Dry-run reports each as
"would delete".

Run from project root:

  python3 -m scripts.merge_unnamed_placeholder_players --dry-run
  python3 -m scripts.merge_unnamed_placeholder_players --dry-run --verbose
  python3 -m scripts.merge_unnamed_placeholder_players --apply

After --apply, restart the API / reload decks.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from api import db as _db
from scripts.fix_unnamed_placeholder_matchups import compute_placeholder_signature_maps


def _trim(s: str | None) -> str:
    return (s or "").strip()


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


def _db_refcounts_for_player(session, player_id: int) -> tuple[int, int]:
    """Counts of decks owned by player and matchups where they are the opponent."""
    n_decks = session.query(_db.DeckRow).filter(_db.DeckRow.player_id == player_id).count()
    n_opp = (
        session.query(_db.MatchupRow)
        .filter(_db.MatchupRow.opponent_player_id == player_id)
        .count()
    )
    return n_decks, n_opp


def _delete_orphan_placeholder_player(session, player_id: int) -> None:
    """Remove player_aliases, player_emails, and players row. Caller must ensure no decks/matchups."""
    session.query(_db.PlayerAliasRow).filter(_db.PlayerAliasRow.player_id == player_id).delete(
        synchronize_session=False
    )
    session.query(_db.PlayerEmailRow).filter(_db.PlayerEmailRow.player_id == player_id).delete(
        synchronize_session=False
    )
    row = _db.get_player_by_id(session, player_id)
    if row:
        session.delete(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge Unnamed* placeholder player rows into signature-resolved real players."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify either --dry-run or --apply")

    _load_env()

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    with _db.session_scope() as session:
        sm = compute_placeholder_signature_maps(session)
        if not sm.placeholder_ids:
            print("No placeholder players (Unnamed / Unnamed N); nothing to do.")
            return

        merged = 0
        deleted_unreferenced = 0
        skipped = 0

        for p_ph in sorted(sm.placeholder_ids):
            pr_ph = sm.player_by_id.get(p_ph)
            ph_name = (pr_ph.display_name if pr_ph else "") or f"id={p_ph}"

            events_for_ph: set[str] = {
                eid for (eid, pid) in sm.placeholder_event_pairs if pid == p_ph
            }
            events_for_ph |= {
                _trim(d.event_id)
                for d in sm.deck_rows.values()
                if d.player_id == p_ph
            }

            if not events_for_ph:
                nd, nm = _db_refcounts_for_player(session, p_ph)
                if nd or nm:
                    skipped += 1
                    print(
                        f"  skip placeholder {ph_name!r} (player_id={p_ph}): "
                        f"maps show no events but DB still has decks={nd}, matchups_as_opponent={nm}"
                    )
                    continue
                print(
                    f"  {'would delete' if args.dry_run else 'delete'} unreferenced placeholder "
                    f"{ph_name!r} (player_id={p_ph})"
                )
                if args.apply:
                    _delete_orphan_placeholder_player(session, p_ph)
                deleted_unreferenced += 1
                continue

            missing_sig: list[str] = []
            target_pids: list[int] = []
            for eid in sorted(events_for_ph):
                win_deck_id = sm.signature_resolve.get((eid, p_ph))
                if win_deck_id is None:
                    if (eid, p_ph) in sm.signature_ambiguous:
                        det = sm.signature_ambiguous_detail.get((eid, p_ph), "")
                        missing_sig.append(f"{eid!r} (ambiguous{': ' + det if det else ''})")
                    else:
                        missing_sig.append(f"{eid!r} (no signature match)")
                    continue
                deck = sm.deck_rows.get(win_deck_id)
                if not deck:
                    missing_sig.append(f"{eid!r} (winner deck {win_deck_id} missing)")
                    continue
                tp = deck.player_id
                if tp == p_ph:
                    missing_sig.append(f"{eid!r} (winner deck still has placeholder player_id)")
                    continue
                target_pids.append(tp)

            unique_targets = set(target_pids)

            if missing_sig:
                skipped += 1
                print(
                    f"  skip merge placeholder {ph_name!r} (player_id={p_ph}): "
                    f"incomplete signature in: {', '.join(missing_sig)}"
                )
                continue

            if len(unique_targets) != 1:
                skipped += 1
                labels = []
                for tid in sorted(unique_targets):
                    tr = sm.player_by_id.get(tid)
                    labels.append(f"{tid} ({(tr.display_name if tr else '') or '?'})")
                print(
                    f"  skip merge placeholder {ph_name!r} (player_id={p_ph}): "
                    f"events disagree on real player: {', '.join(labels)}"
                )
                continue

            to_pid = target_pids[0]
            to_row = sm.player_by_id.get(to_pid)
            display = (to_row.display_name if to_row else "").strip() or "(unknown)"

            if args.verbose or args.dry_run:
                print(
                    f"  {'would merge' if args.dry_run else 'merge'} "
                    f"{ph_name!r} (id={p_ph}) -> {display!r} (id={to_pid}) "
                    f"[{len(events_for_ph)} event(s)]"
                )

            if args.apply:
                _db.merge_players(session, from_player_id=p_ph, to_player_id=to_pid, canonical_name=display)
            merged += 1

        mode = "DRY-RUN" if args.dry_run else "APPLY"
        print(
            f"[{mode}] merged (or would merge): {merged}; "
            f"deleted unreferenced (or would): {deleted_unreferenced}; skipped: {skipped}"
        )
        if args.apply and (merged or deleted_unreferenced):
            print("Done. Restart the API or reload data.")


if __name__ == "__main__":
    main()
