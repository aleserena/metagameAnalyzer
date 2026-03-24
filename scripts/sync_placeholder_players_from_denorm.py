#!/usr/bin/env python3
"""
Align Unnamed* placeholder ``players`` rows with names already stored on decks/matchups.

For each player whose ``display_name`` matches ``Unnamed`` / ``Unnamed7`` / ``Unnamed 7``, etc.,
collect non-placeholder strings from:

- ``decks.player`` where ``player_id`` is that placeholder
- ``matchups.opponent_player`` where ``opponent_player_id`` is that placeholder

If one clear winner emerges (no tie for the most frequent distinct string), then:

- If ``resolve_name_to_player_id`` finds another row for that name → ``merge_players`` into it
  (old placeholder name is registered as an alias on the target).
- Otherwise → rename the placeholder row’s ``display_name``, refresh denormalized deck/matchup text,
  and register the old Unnamed* string as an alias for the same id.

Run from project root:

  python3 -m scripts.sync_placeholder_players_from_denorm --dry-run
  python3 -m scripts.sync_placeholder_players_from_denorm --dry-run -v
  python3 -m scripts.sync_placeholder_players_from_denorm --apply

After ``--apply``, restart the API / reload decks.
"""

from __future__ import annotations

import argparse
from collections import Counter
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


def _skip_denorm_label(s: str) -> bool:
    t = (s or "").strip()
    if not t or t == "(unknown)":
        return True
    if t.lower() in ("bye", "(drop)"):
        return True
    return _db._is_unnamed_placeholder_display(t)


def _collect_name_votes(session, placeholder_id: int) -> list[str]:
    votes: list[str] = []
    for d in session.query(_db.DeckRow).filter(_db.DeckRow.player_id == placeholder_id).all():
        s = (d.player or "").strip()
        if not _skip_denorm_label(s):
            votes.append(s)
    for m in session.query(_db.MatchupRow).filter(_db.MatchupRow.opponent_player_id == placeholder_id).all():
        s = (m.opponent_player or "").strip()
        if not _skip_denorm_label(s):
            votes.append(s)
    return votes


def _pick_winner(votes: list[str]) -> tuple[str | None, str]:
    """Return (chosen_name, reason_if_skipped). reason empty when chosen is set."""
    if not votes:
        return None, "no non-placeholder names on decks/matchups"
    ctr = Counter(votes)
    top_count = ctr.most_common(1)[0][1]
    winners = sorted(name for name, n in ctr.items() if n == top_count)
    if len(winners) > 1:
        return None, f"tie between distinct names ({', '.join(repr(w) for w in winners)})"
    return winners[0], ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rename or merge Unnamed* players using deck/matchup denormalized names."
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

    renamed = 0
    merged = 0
    skipped = 0

    with _db.session_scope() as session:
        placeholders = [
            p
            for p in session.query(_db.PlayerRow).order_by(_db.PlayerRow.id).all()
            if _db._is_unnamed_placeholder_display(p.display_name or "")
        ]

        if not placeholders:
            print("No Unnamed* placeholder player rows; nothing to do.")
            return

        for p in placeholders:
            pid = p.id
            old_display = (p.display_name or "").strip()
            votes = _collect_name_votes(session, pid)
            chosen, skip_reason = _pick_winner(votes)

            if args.verbose and votes:
                print(f"  id={pid} {old_display!r} votes: {dict(Counter(votes))}")

            if chosen is None:
                skipped += 1
                print(f"  skip id={pid} {old_display!r}: {skip_reason}")
                continue

            to_id, resolved_display = _db.resolve_name_to_player_id(session, chosen)
            resolved_display = (resolved_display or chosen).strip() or chosen

            if to_id is not None and to_id != pid:
                tgt = _db.get_player_by_id(session, to_id)
                tgt_name = (tgt.display_name if tgt else "") or resolved_display
                print(
                    f"  {'would merge' if args.dry_run else 'merge'} id={pid} {old_display!r} -> "
                    f"id={to_id} {tgt_name!r} (from denorm {chosen!r})"
                )
                if args.apply:
                    _db.merge_players(
                        session,
                        from_player_id=pid,
                        to_player_id=to_id,
                        canonical_name=tgt_name,
                    )
                    _db.set_player_alias_by_id(session, old_display, to_id)
                merged += 1
                continue

            # Rename this row in place (no other player claims this name).
            print(
                f"  {'would rename' if args.dry_run else 'rename'} id={pid} "
                f"{old_display!r} -> {chosen!r} (denorm consensus)"
            )
            if args.apply:
                p.display_name = chosen
                for d in session.query(_db.DeckRow).filter(_db.DeckRow.player_id == pid).all():
                    d.player = chosen
                for m in session.query(_db.MatchupRow).filter(_db.MatchupRow.opponent_player_id == pid).all():
                    m.opponent_player = chosen
                if old_display and old_display != chosen:
                    _db.set_player_alias_by_id(session, old_display, pid)
            renamed += 1

    mode = "DRY-RUN" if args.dry_run else "APPLY"
    print(f"[{mode}] renamed (or would): {renamed}; merged (or would): {merged}; skipped: {skipped}")
    if args.apply and (renamed or merged):
        print("Done. Restart the API or reload data.")


if __name__ == "__main__":
    main()
