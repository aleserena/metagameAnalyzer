"""
Mark events as single elimination and renumber their matchup rounds from the decks' ranks.

Before single-elimination events existed, bracket games were typed into the Swiss/Top 8 editor and stored
with scrambled round numbers. In a knockout bracket every match is decided by its loser's rank: a 9-16
loser went out in the round of 16 (round 1 of a 16-player bracket), a 2 lost the final (round 4). This
script sets ``structure = 'single_elimination'`` and ``bracket_size`` and gives both sides of every match
that round.

It changes nothing for an event whose data contradicts the bracket (a match that is not one win and one
loss, a loser whose rank is not a bracket elimination, a deck with two matches in one round or more
matches than its rank allows) and lists the problems instead. Rows without an opponent in the event
(byes, drops) are left alone. A snapshot of the event is taken first (restore it from Settings → Event
snapshots) and a change-log entry is written after commit. Idempotent: a second run changes nothing.

After ``--apply``, restart the API or call ``POST /api/v1/analyze`` so a running process reloads.

Pass ``--db-env`` to choose the database. Without it the ambient ``DB_ENV`` decides, and ``.env`` sets
that to ``staging``. Every run prints the database it resolved to.

Examples:
  python3 -m scripts.renumber_single_elim_rounds --event-id 90844 --event-id 93708 --bracket-size 16 --dry-run --db-env staging
  python3 -m scripts.renumber_single_elim_rounds --event-id 90844 --event-id 93708 --bracket-size 16 --apply --db-env staging
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from api import db as _db
from api.brackets import STRUCTURE_SINGLE_ELIM, elimination_round, expected_matches_for_rank, validate_structure
from api.db import DeckRow, MatchupRow
from api.results import LOSS_RESULTS, WIN_RESULTS
from scripts._env import VALID_DB_ENVS, load_env


@dataclass
class RenumberPlan:
    changes: list[tuple[int, int | None, int]] = field(default_factory=list)  # (matchup_id, old_round, new_round)
    errors: list[str] = field(default_factory=list)


def _loser_of(row: MatchupRow, opponent_deck_id: int) -> int | None:
    """The deck that lost this match according to one side's row (None for a draw or anything else)."""
    if row.result in LOSS_RESULTS:
        return row.deck_id
    if row.result in WIN_RESULTS:
        return opponent_deck_id
    return None


def plan_renumber(session, event_id: str, bracket_size: int) -> RenumberPlan:
    """Work out the bracket round of every match in the event, without changing anything."""
    validate_structure(STRUCTURE_SINGLE_ELIM, bracket_size)
    eid = _db._event_id_str(event_id)
    decks = {d.deck_id: d for d in session.query(DeckRow).filter(DeckRow.event_id == eid)}
    deck_by_player = {d.player_id: d.deck_id for d in decks.values() if d.player_id is not None}
    rows = session.query(MatchupRow).filter(MatchupRow.deck_id.in_(list(decks))).order_by(MatchupRow.id).all()

    pairs: dict[frozenset, list[tuple[MatchupRow, int]]] = {}
    for row in rows:
        opp = row.opponent_deck_id if row.opponent_deck_id in decks else deck_by_player.get(row.opponent_player_id)
        if opp is None or opp == row.deck_id:
            continue  # bye, drop, or an opponent outside the event: left alone
        pairs.setdefault(frozenset((row.deck_id, opp)), []).append((row, opp))

    plan = RenumberPlan()
    target: dict[int, int] = {}
    for key, sides in pairs.items():
        a, b = sorted(key)
        label = f"{decks[a].player} vs {decks[b].player}"
        losers = {_loser_of(row, opp) for row, opp in sides}
        if len(sides) > 2 or len(losers) != 1 or None in losers:
            results = ", ".join(sorted(row.result for row, _ in sides))
            plan.errors.append(f"{label}: stored results ({results}) are not one win and one loss")
            continue
        loser = losers.pop()
        rnd = elimination_round(decks[loser].rank, bracket_size)
        if rnd is None:
            plan.errors.append(
                f"{label}: {decks[loser].player} lost but is ranked {decks[loser].rank!r}, "
                f"which is not a {bracket_size}-player bracket elimination"
            )
            continue
        for row, _ in sides:
            target[row.id] = rnd

    rounds_by_deck: dict[int, list[int]] = {}
    for row in rows:
        if row.id in target:
            rounds_by_deck.setdefault(row.deck_id, []).append(target[row.id])
    for deck_id, rounds in rounds_by_deck.items():
        deck = decks[deck_id]
        allowed = expected_matches_for_rank(deck.rank, bracket_size)
        if len(rounds) > allowed:
            plan.errors.append(f"{deck.player} (rank {deck.rank!r}) has {len(rounds)} matches; the rank allows {allowed}")
        if len(set(rounds)) != len(rounds):
            plan.errors.append(f"{deck.player} (rank {deck.rank!r}) would have two matches in one round: {sorted(rounds)}")

    plan.changes = [(row.id, row.round, target[row.id]) for row in rows if row.id in target and row.round != target[row.id]]
    return plan


def apply_renumber(session, event_id: str, bracket_size: int, plan: RenumberPlan) -> int:
    """Snapshot the event, mark it single elimination and write the planned rounds. Returns rows changed.

    Raises ValueError (changing nothing) when the plan has errors. The caller commits."""
    from api.services.snapshots import REASON_RENUMBER_ROUNDS, take_snapshot

    if plan.errors:
        raise ValueError(f"Event {event_id}: not renumbered, the data contradicts the bracket: " + "; ".join(plan.errors))
    eid = _db._event_id_str(event_id)
    take_snapshot(session, eid, REASON_RENUMBER_ROUNDS)
    structure, size = validate_structure(STRUCTURE_SINGLE_ELIM, bracket_size)
    _db.update_event(session, eid, structure=structure, bracket_size=size)
    for matchup_id, _old, new in plan.changes:
        session.get(MatchupRow, matchup_id).round = new
    session.flush()
    return len(plan.changes)


def main() -> None:
    from api.services import change_log

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--event-id", action="append", required=True, help="Event to fix; repeat for several.")
    parser.add_argument("--bracket-size", type=int, required=True, help="Players in the bracket (2, 4, 8 ... 128).")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--db-env",
        choices=VALID_DB_ENVS,
        help="Which database to target. Overrides DB_ENV; .env defaults it to staging.",
    )
    args = parser.parse_args()
    if args.dry_run == args.apply:
        parser.error("Specify exactly one of --dry-run or --apply")
    try:
        validate_structure(STRUCTURE_SINGLE_ELIM, args.bracket_size)
    except ValueError as e:
        parser.error(str(e))

    target = load_env(args.db_env)
    print(f"target database: {target}")
    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")
    factory = _db.get_session_factory_cached()
    if factory is None:
        raise RuntimeError("Database session factory unavailable")

    for event_id in args.event_id:
        session = factory()
        try:
            if _db.get_event(session, event_id) is None:
                print(f"\nevent {event_id}: not found, skipped")
                continue
            plan = plan_renumber(session, event_id, args.bracket_size)
            print(f"\nevent {event_id}: {len(plan.changes)} rows to renumber")
            for matchup_id, old, new in plan.changes:
                row = session.get(MatchupRow, matchup_id)
                print(f"  matchup {matchup_id}: deck {row.deck_id} vs {row.opponent_player!r} ({row.result}) round {old} -> {new}")
            for err in plan.errors:
                print(f"  PROBLEM: {err}")
            if plan.errors:
                print("  Nothing changed for this event.")
                session.rollback()
                continue
            if args.dry_run:
                session.rollback()
                print("  Dry run: nothing was saved.")
                continue
            n = apply_renumber(session, event_id, args.bracket_size, plan)
            session.commit()
            change_log.log(
                change_log.ADMIN,
                "event.renumber_rounds",
                f"Marked as single elimination ({args.bracket_size}-player bracket); renumbered {n} matchup rounds",
                event_id=event_id,
            )
            print(f"  Done: {n} rows renumbered.")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


if __name__ == "__main__":
    main()
