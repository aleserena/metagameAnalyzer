"""
Fix matchups that still point at placeholder "Unnamed" / "Unnamed N" players after decks were renamed.

Blank decks are created with player names like "Unnamed" or "Unnamed 2" (see add_blank_deck_to_event).
After the real player is saved on that deck, `decks.player_id` and `decks.player` update, but other
decks' matchup rows may still have `opponent_player_id` on the shared global placeholder player row
and missing `opponent_deck_id`. That skews the player matchup matrix.

Because `players.display_name` is unique globally, the same placeholder row can appear in multiple
events — we must not merge those players in one shot. Resolution is scoped per event.

For each broken matchup we try, in order:
1. **Symmetric row** — same event and round: another deck reports `opponent_deck_id` = us, or
   `opponent_player_id` = our deck's player_id.
2. **Same deck + same placeholder opponent + same round** — another matchup row for that deck in
   this event/round already has `opponent_deck_id` set (same pairing); use that deck if unique.
3. **Same deck + same placeholder opponent** (any round) — among all rows for that deck vs this
   placeholder id in the event, if every non-null `opponent_deck_id` agrees on one deck, use it.
4. **Event + placeholder consensus** — among all matchups in the event with this `opponent_player_id`,
   if every non-null `opponent_deck_id` is the same deck, use it (one unnamed slot per event).
5. **Result-path signature** — all matchups in the event that reference this unnamed slot (by
   `opponent_player_id` or by the same `Unnamed` / `Unnamed9` label on `opponent_player`). Build
   the placeholder’s Swiss line: for each reporter deck, inverted result (e.g. Ivan won → unnamed
   lost). Match **Gustavo Videla**’s deck by: **(a)** every `(round, opponent_deck_id)` edge on the
   placeholder side appears on his rows with the same result (**subset**, so extra rounds on his
   deck are OK); **(b)** if that ties multiple decks, narrow by multiset of `(opponent_deck_id,
   result)` ignoring round; **(c)** if (a) finds nobody, **(c)** alone can win if unique. Opponent
   deck on each row is taken from `opponent_deck_id` or, if missing, the only deck in the event for
   `opponent_player_id`.

Run:
  python3 -m scripts.fix_unnamed_placeholder_matchups --dry-run
  python3 -m scripts.fix_unnamed_placeholder_matchups --dry-run --verbose
  python3 -m scripts.fix_unnamed_placeholder_matchups --apply

Delete (same scope as fix: opponent is Unnamed / Unnamed N by id or label; not bye/drop):
  python3 -m scripts.fix_unnamed_placeholder_matchups --dry-run --delete-placeholder-matchups
  python3 -m scripts.fix_unnamed_placeholder_matchups --apply --delete-placeholder-matchups --verbose

When deleting, inverse rows stored on the opponent’s deck (if any) are not removed automatically.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from api import db as _db

# Matches "Unnamed", "Unnamed 9", "Unnamed9", etc. (blank-deck placeholders)
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


def _unnamed_label_key(name: str | None) -> str | None:
    """Stable slot id for 'Unnamed' / 'Unnamed 9' / 'Unnamed9' so text and player row line up."""
    raw = (name or "").strip()
    if not is_placeholder_display_name(raw):
        return None
    compact = re.sub(r"\s+", "", raw.lower())
    if compact == "unnamed":
        return "0"
    if compact.startswith("unnamed") and compact[len("unnamed") :].isdigit():
        return compact[len("unnamed") :]
    return None


def _trim(s: str | None) -> str:
    return (s or "").strip()


def _multiplicity(values: list[int]) -> tuple[int | None, bool]:
    """Return (single value if exactly one distinct, is_ambiguous if more than one distinct)."""
    seen: list[int] = []
    for v in values:
        if v not in seen:
            seen.append(v)
    if len(seen) == 1:
        return seen[0], False
    if len(seen) > 1:
        return None, True
    return None, False


def _norm_result(r: str) -> str:
    return (r or "").strip().lower()


def _edge_result_bucket(r: str) -> str:
    """Collapse score-style results so reporter 'win' and opponent '1-2' match across sides."""
    x = _norm_result(r)
    if x in ("win", "2-1", "2-0", "1-0"):
        return "win"
    if x in ("loss", "1-2", "0-2", "0-1"):
        return "loss"
    if x == "intentional_draw_win":
        return "intentional_draw_win"
    if x == "intentional_draw_loss":
        return "intentional_draw_loss"
    if x in ("draw", "intentional_draw"):
        return x
    return x


def _sig_from_rows_vs_placeholder(rows_vs_ph: list[_db.MatchupRow]) -> dict[tuple[int | None, int], str] | None:
    """Map (round, reporter_deck_id) -> result from the placeholder player's POV (inverted)."""
    sig: dict[tuple[int | None, int], str] = {}
    for m in rows_vs_ph:
        res = _norm_result(m.result)
        if res in ("bye", "drop"):
            continue
        key = (m.round, m.deck_id)
        val = _edge_result_bucket(_db._invert_matchup_result(m.result))
        if key in sig and sig[key] != val:
            return None
        sig[key] = val
    return sig if sig else None


def _effective_opponent_deck_id(
    m: _db.MatchupRow,
    event_id: str,
    decks_for_player_in_event: dict[tuple[str, int], list[int]],
) -> int | None:
    if m.opponent_deck_id is not None:
        return m.opponent_deck_id
    if m.opponent_player_id is None:
        return None
    cands = decks_for_player_in_event.get((event_id, m.opponent_player_id), [])
    if len(cands) == 1:
        return cands[0]
    return None


def _sig_from_deck_own_rows(
    rows: list[_db.MatchupRow],
    event_id: str,
    decks_for_player_in_event: dict[tuple[str, int], list[int]],
) -> dict[tuple[int | None, int], str] | None:
    """Map (round, opponent_deck_id) -> this deck's reported result. Skips rows without resolvable opponent deck."""
    sig: dict[tuple[int | None, int], str] = {}
    for m in rows:
        res = _norm_result(m.result)
        if res in ("bye", "drop"):
            continue
        od = _effective_opponent_deck_id(m, event_id, decks_for_player_in_event)
        if od is None:
            continue
        key = (m.round, od)
        val = _edge_result_bucket(m.result)
        if key in sig and sig[key] != val:
            return None
        sig[key] = val
    return sig if sig else None


def _sig_ph_subset_of_deck(
    sig_ph: dict[tuple[int | None, int], str],
    sig_deck: dict[tuple[int | None, int], str],
) -> bool:
    """True if every (round, opponent) outcome for the placeholder is present on the deck (extra deck rows OK)."""
    for k, v in sig_ph.items():
        if sig_deck.get(k) != v:
            return False
    return True


def _edge_bag_vs_placeholder(rows_vs_ph: list[_db.MatchupRow]) -> Counter[tuple[int, str]]:
    """Multiset (reporter_deck_id, result from placeholder POV) — ignores round (handles NULL/mismatched rounds)."""
    c: Counter[tuple[int, str]] = Counter()
    for m in rows_vs_ph:
        res = _norm_result(m.result)
        if res in ("bye", "drop"):
            continue
        c[(m.deck_id, _edge_result_bucket(_db._invert_matchup_result(m.result)))] += 1
    return c


def _edge_bag_for_deck(
    rows: list[_db.MatchupRow],
    event_id: str,
    decks_for_player_in_event: dict[tuple[str, int], list[int]],
) -> Counter[tuple[int, str]]:
    """Multiset (opponent_deck_id, this deck's result) for non-bye/drop rows with resolvable opponent deck."""
    c: Counter[tuple[int, str]] = Counter()
    for m in rows:
        res = _norm_result(m.result)
        if res in ("bye", "drop"):
            continue
        od = _effective_opponent_deck_id(m, event_id, decks_for_player_in_event)
        if od is None:
            continue
        c[(od, _edge_result_bucket(m.result))] += 1
    return c


def _counter_subset(small: Counter, big: Counter) -> bool:
    for k, n in small.items():
        if big[k] < n:
            return False
    return True


@dataclass
class PlaceholderSignatureMaps:
    """Precomputed maps for resolving blank-deck placeholders to real decks (see module docstring)."""

    rows: list[Any]
    placeholder_ids: set[int]
    deck_rows: dict[int, _db.DeckRow]
    player_by_id: dict[int, _db.PlayerRow]
    by_event_round_opp_deck: dict[tuple[str, int, int], list[int]]
    by_event_round_opp_pid: dict[tuple[str, int, int], list[int]]
    sibling_by_round: dict[tuple[str, int, int, int | None], list[int]]
    sibling_by_deck_opp: dict[tuple[str, int, int], list[int]]
    event_placeholder_decks: dict[tuple[str, int], list[int]]
    matchups_by_reporter: dict[int, list]
    placeholder_id_for_row: Callable[[_db.MatchupRow], int | None]
    signature_resolve: dict[tuple[str, int], int]
    signature_ambiguous: set[tuple[str, int]]
    signature_ambiguous_detail: dict[tuple[str, int], str]
    placeholder_event_pairs: set[tuple[str, int]]


def compute_placeholder_signature_maps(session: Any) -> PlaceholderSignatureMaps:
    """Load matchups/decks/players and compute per-(event_id, placeholder_player_id) identity deck_id."""
    placeholder_ids = {
        p.id
        for p in session.query(_db.PlayerRow).all()
        if is_placeholder_display_name(p.display_name)
    }
    if not placeholder_ids:
        return PlaceholderSignatureMaps(
            rows=[],
            placeholder_ids=set(),
            deck_rows={},
            player_by_id={},
            by_event_round_opp_deck=defaultdict(list),
            by_event_round_opp_pid=defaultdict(list),
            sibling_by_round=defaultdict(list),
            sibling_by_deck_opp=defaultdict(list),
            event_placeholder_decks=defaultdict(list),
            matchups_by_reporter=defaultdict(list),
            placeholder_id_for_row=lambda m: None,
            signature_resolve={},
            signature_ambiguous=set(),
            signature_ambiguous_detail={},
            placeholder_event_pairs=set(),
        )

    rows = (
        session.query(_db.MatchupRow, _db.DeckRow.event_id, _db.DeckRow.player_id)
        .join(_db.DeckRow, _db.MatchupRow.deck_id == _db.DeckRow.deck_id)
        .all()
    )

    by_event_round_opp_deck: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    by_event_round_opp_pid: dict[tuple[str, int, int], list[int]] = defaultdict(list)

    for m, event_id, _my_pid in rows:
        r = m.round
        if r is None:
            continue
        eid = _trim(event_id)
        if m.opponent_deck_id is not None:
            by_event_round_opp_deck[(eid, r, m.opponent_deck_id)].append(m.deck_id)
        if m.opponent_player_id is not None:
            by_event_round_opp_pid[(eid, r, m.opponent_player_id)].append(m.deck_id)

    sibling_by_round: dict[tuple[str, int, int, int | None], list[int]] = defaultdict(list)
    sibling_by_deck_opp: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    event_placeholder_decks: dict[tuple[str, int], list[int]] = defaultdict(list)

    for m, event_id, _ in rows:
        eid = _trim(event_id)
        opid = m.opponent_player_id
        if opid is None or opid not in placeholder_ids:
            continue
        od = m.opponent_deck_id
        if od is None:
            continue
        sibling_by_round[(eid, m.deck_id, opid, m.round)].append(od)
        sibling_by_deck_opp[(eid, m.deck_id, opid)].append(od)
        event_placeholder_decks[(eid, opid)].append(od)

    deck_rows = {d.deck_id: d for d in session.query(_db.DeckRow).all()}
    player_by_id = {p.id: p for p in session.query(_db.PlayerRow).all()}

    def _deck_label(bid: int) -> str:
        d = deck_rows.get(bid)
        if not d:
            return str(bid)
        pb = player_by_id.get(d.player_id)
        nm = (pb.display_name if pb else None) or _trim(d.player) or "?"
        return f"{bid} ({nm})"

    def _format_deck_list(ids: list[int]) -> str:
        return ", ".join(_deck_label(b) for b in ids)

    def placeholder_id_for_row(m: _db.MatchupRow) -> int | None:
        if m.opponent_player_id is not None and m.opponent_player_id in placeholder_ids:
            return m.opponent_player_id
        km = _unnamed_label_key(m.opponent_player)
        if km is None:
            return None
        for pid in placeholder_ids:
            pr = player_by_id.get(pid)
            if pr and _unnamed_label_key((pr.display_name or "")) == km:
                return pid
        return None

    decks_for_player_in_event: dict[tuple[str, int], list[int]] = defaultdict(list)
    for bid, d in deck_rows.items():
        decks_for_player_in_event[(_trim(d.event_id), d.player_id)].append(bid)

    matchups_by_reporter: dict[int, list] = defaultdict(list)
    for m, _, _ in rows:
        matchups_by_reporter[m.deck_id].append(m)

    placeholder_event_pairs: set[tuple[str, int]] = set()
    for m, event_id, _ in rows:
        pid = placeholder_id_for_row(m)
        if pid is not None:
            placeholder_event_pairs.add((_trim(event_id), pid))

    signature_resolve: dict[tuple[str, int], int] = {}
    signature_ambiguous: set[tuple[str, int]] = set()
    signature_ambiguous_detail: dict[tuple[str, int], str] = {}
    for eid, p_ph in sorted(placeholder_event_pairs):
        pr_slot = player_by_id.get(p_ph)
        display_ph = (pr_slot.display_name or "").strip() if pr_slot else ""
        slot_key = _unnamed_label_key(display_ph) if display_ph else None

        rows_vs_ph: list[_db.MatchupRow] = []
        for m, ev, _ in rows:
            if _trim(ev) != eid:
                continue
            if m.opponent_player_id == p_ph:
                rows_vs_ph.append(m)
            elif slot_key is not None and _unnamed_label_key(m.opponent_player) == slot_key:
                rows_vs_ph.append(m)

        sig_ph = _sig_from_rows_vs_placeholder(rows_vs_ph)
        bag_ph = _edge_bag_vs_placeholder(rows_vs_ph)
        if not bag_ph:
            continue
        if sig_ph is None:
            continue

        def _non_placeholder_decks_in_event() -> list[int]:
            out: list[int] = []
            for bid, d in deck_rows.items():
                if _trim(d.event_id) != eid:
                    continue
                p_b = player_by_id.get(d.player_id)
                display_b = (p_b.display_name if p_b else None) or _trim(d.player) or ""
                if is_placeholder_display_name(display_b):
                    continue
                out.append(bid)
            return out

        non_ph = _non_placeholder_decks_in_event()

        def _bag_ok(bid: int) -> bool:
            bag_b = _edge_bag_for_deck(
                matchups_by_reporter[bid], eid, decks_for_player_in_event
            )
            return _counter_subset(bag_ph, bag_b)

        strict: list[int] = []
        for bid in non_ph:
            sig_b = _sig_from_deck_own_rows(
                matchups_by_reporter[bid], eid, decks_for_player_in_event
            )
            if sig_b is None:
                continue
            if _sig_ph_subset_of_deck(sig_ph, sig_b):
                strict.append(bid)

        winner: int | None = None
        if len(strict) == 1:
            winner = strict[0]
        elif len(strict) > 1:
            narrowed = [b for b in strict if _bag_ok(b)]
            if len(narrowed) == 1:
                winner = narrowed[0]
            else:
                signature_ambiguous.add((eid, p_ph))
                signature_ambiguous_detail[(eid, p_ph)] = (
                    f"strict subset: {_format_deck_list(strict)} "
                    f"({len(strict)} decks); after bag filter: {_format_deck_list(narrowed)} "
                    f"({len(narrowed)} decks, need exactly 1)"
                )
        else:
            bag_cand = [b for b in non_ph if _bag_ok(b)]
            if len(bag_cand) == 1:
                winner = bag_cand[0]
            elif len(bag_cand) > 1:
                signature_ambiguous.add((eid, p_ph))
                signature_ambiguous_detail[(eid, p_ph)] = (
                    f"bag subset: {_format_deck_list(bag_cand)} ({len(bag_cand)} decks)"
                )

        if winner is not None:
            signature_resolve[(eid, p_ph)] = winner

    return PlaceholderSignatureMaps(
        rows=rows,
        placeholder_ids=placeholder_ids,
        deck_rows=deck_rows,
        player_by_id=player_by_id,
        by_event_round_opp_deck=by_event_round_opp_deck,
        by_event_round_opp_pid=by_event_round_opp_pid,
        sibling_by_round=sibling_by_round,
        sibling_by_deck_opp=sibling_by_deck_opp,
        event_placeholder_decks=event_placeholder_decks,
        matchups_by_reporter=matchups_by_reporter,
        placeholder_id_for_row=placeholder_id_for_row,
        signature_resolve=signature_resolve,
        signature_ambiguous=signature_ambiguous,
        signature_ambiguous_detail=signature_ambiguous_detail,
        placeholder_event_pairs=placeholder_event_pairs,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, but do nothing")
    parser.add_argument("--apply", action="store_true", help="Apply the fix (writes to DB)")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print each matchup fix, skip, delete, or ambiguous reason",
    )
    parser.add_argument(
        "--delete-placeholder-matchups",
        action="store_true",
        help=(
            "Remove matchups whose opponent is a blank-deck placeholder (Unnamed / Unnamed N), "
            "same rows this script would try to fix. Does not run repair logic. Use with --dry-run or --apply."
        ),
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify either --dry-run or --apply")

    _load_env()

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    with _db.session_scope() as session:
        sm = compute_placeholder_signature_maps(session)
        if not sm.placeholder_ids:
            print("No placeholder players (Unnamed / Unnamed N) in players table; nothing to do.")
            return

        rows = sm.rows
        placeholder_ids = sm.placeholder_ids
        deck_rows = sm.deck_rows
        player_by_id = sm.player_by_id
        by_event_round_opp_deck = sm.by_event_round_opp_deck
        by_event_round_opp_pid = sm.by_event_round_opp_pid
        sibling_by_round = sm.sibling_by_round
        sibling_by_deck_opp = sm.sibling_by_deck_opp
        event_placeholder_decks = sm.event_placeholder_decks
        placeholder_id_for_row = sm.placeholder_id_for_row
        signature_resolve = sm.signature_resolve
        signature_ambiguous = sm.signature_ambiguous
        signature_ambiguous_detail = sm.signature_ambiguous_detail

        print(f"Placeholder player ids (Unnamed*): {len(placeholder_ids)}")

        def _deck_label(bid: int) -> str:
            d = deck_rows.get(bid)
            if not d:
                return str(bid)
            pb = player_by_id.get(d.player_id)
            nm = (pb.display_name if pb else None) or _trim(d.player) or "?"
            return f"{bid} ({nm})"

        def _player_label(pid: int) -> str:
            pr = player_by_id.get(pid)
            nm = (pr.display_name if pr else "") or "?"
            return f"{pid} ({nm})"

        def _format_deck_list(ids: list[int]) -> str:
            return ", ".join(_deck_label(b) for b in ids)

        print(
            f"Signature matches (event+placeholder -> one real deck): {len(signature_resolve)}; "
            f"ambiguous: {len(signature_ambiguous)}"
        )

        to_fix: list[_db.MatchupRow] = []
        for m, _eid, _ in rows:
            res = (m.result or "").strip().lower()
            if res in ("bye", "drop"):
                continue
            if placeholder_id_for_row(m) is None:
                continue
            to_fix.append(m)

        print(f"Matchups with placeholder opponent_player_id: {len(to_fix)}")

        if args.delete_placeholder_matchups:
            if args.dry_run:
                print(f"[DRY-RUN] --delete-placeholder-matchups: would delete {len(to_fix)} matchup row(s)")
            else:
                print(f"[APPLY] --delete-placeholder-matchups: deleting {len(to_fix)} matchup row(s)")
            if args.verbose and to_fix:
                for m in to_fix:
                    p_ph = placeholder_id_for_row(m)
                    pr = player_by_id.get(p_ph) if p_ph is not None else None
                    ph_disp = (pr.display_name if pr else "") or "?"
                    print(
                        f"  delete matchup_id={m.id} reporter={_deck_label(m.deck_id)} "
                        f"round={m.round} result={m.result!r} "
                        f"opponent_player={m.opponent_player!r} placeholder_player_id={p_ph} ({ph_disp!r})"
                    )
            if args.apply:
                for m in to_fix:
                    session.delete(m)
                print("Done (matchups deleted).")
            return

        updated = 0
        updated_symmetric = 0
        updated_sibling_round = 0
        updated_sibling_deck = 0
        updated_event_consensus = 0
        updated_signature = 0
        skipped_no_round = 0
        skipped_no_partner = 0
        ambiguous = 0
        skipped_target_still_placeholder = 0
        unchanged = 0

        for m in to_fix:
            deck_a = deck_rows.get(m.deck_id)
            if not deck_a:
                continue
            event_id = _trim(deck_a.event_id)
            my_pid = deck_a.player_id
            R = m.round
            p_ph = placeholder_id_for_row(m)
            if p_ph is None:
                continue

            b_deck_id: int | None = None
            how: Literal["symmetric", "sibling_round", "sibling_deck", "event", "signature", ""] = ""

            if R is not None:
                key_deck = (event_id, R, m.deck_id)
                c_deck = by_event_round_opp_deck.get(key_deck, [])
                uniq_deck = list(dict.fromkeys(c_deck))
                if len(uniq_deck) == 1:
                    b_deck_id = uniq_deck[0]
                    how = "symmetric"
                elif len(uniq_deck) > 1:
                    ambiguous += 1
                    if args.verbose:
                        print(
                            f"  ambiguous matchup_id={m.id} reporter={_deck_label(m.deck_id)} round={R}: "
                            f"multiple decks claim opponent_deck_id={m.deck_id} "
                            f"({_format_deck_list(uniq_deck)})"
                        )
                    continue
                else:
                    key_pid = (event_id, R, my_pid)
                    c_pid = by_event_round_opp_pid.get(key_pid, [])
                    uniq_pid = list(dict.fromkeys(c_pid))
                    if len(uniq_pid) == 1:
                        b_deck_id = uniq_pid[0]
                        how = "symmetric"
                    elif len(uniq_pid) > 1:
                        ambiguous += 1
                        if args.verbose:
                            print(
                                f"  ambiguous matchup_id={m.id} reporter={_deck_label(m.deck_id)} round={R}: "
                                f"multiple decks claim they faced {_player_label(my_pid)}: "
                                f"{_format_deck_list(uniq_pid)}"
                            )
                        continue

            if b_deck_id is None and R is not None:
                vals = sibling_by_round.get((event_id, m.deck_id, p_ph, R), [])
                u, amb = _multiplicity(vals)
                if amb:
                    ambiguous += 1
                    if args.verbose:
                        uq = list(dict.fromkeys(vals))
                        print(
                            f"  ambiguous matchup_id={m.id} reporter={_deck_label(m.deck_id)} "
                            f"round={R} placeholder_player_id={p_ph}: "
                            f"conflicting opponent_deck_id among sibling rows: {_format_deck_list(uq)}"
                        )
                    continue
                if u is not None:
                    b_deck_id = u
                    how = "sibling_round"

            if b_deck_id is None:
                vals = sibling_by_deck_opp.get((event_id, m.deck_id, p_ph), [])
                u, amb = _multiplicity(vals)
                if amb:
                    ambiguous += 1
                    if args.verbose:
                        uq = list(dict.fromkeys(vals))
                        print(
                            f"  ambiguous matchup_id={m.id} reporter={_deck_label(m.deck_id)} "
                            f"placeholder_player_id={p_ph}: "
                            f"same deck+placeholder, conflicting opponent_deck_id: {_format_deck_list(uq)}"
                        )
                    continue
                if u is not None:
                    b_deck_id = u
                    how = "sibling_deck"

            if b_deck_id is None:
                vals = event_placeholder_decks.get((event_id, p_ph), [])
                u, amb = _multiplicity(vals)
                if amb:
                    ambiguous += 1
                    if args.verbose:
                        uq = list(dict.fromkeys(vals))
                        print(
                            f"  ambiguous matchup_id={m.id} reporter={_deck_label(m.deck_id)} "
                            f"event_id={event_id!r} placeholder_player_id={p_ph}: "
                            f"event-wide conflicting opponent_deck_id: {_format_deck_list(uq)}"
                        )
                    continue
                if u is not None:
                    b_deck_id = u
                    how = "event"

            if b_deck_id is None:
                if (event_id, p_ph) in signature_ambiguous:
                    ambiguous += 1
                    if args.verbose:
                        det = signature_ambiguous_detail.get((event_id, p_ph), "")
                        pr = player_by_id.get(p_ph)
                        ph_name = (pr.display_name if pr else "") or "?"
                        print(
                            f"  ambiguous_signature matchup_id={m.id} "
                            f"reporter={_deck_label(m.deck_id)} round={R} "
                            f"event_id={event_id!r} placeholder={ph_name!r} player_id={p_ph}"
                            + (f": {det}" if det else "")
                        )
                    continue
                sid = signature_resolve.get((event_id, p_ph))
                if sid is not None:
                    b_deck_id = sid
                    how = "signature"

            if b_deck_id is None:
                if R is None:
                    skipped_no_round += 1
                    if args.verbose:
                        print(f"  skip matchup_id={m.id}: round is NULL and no event consensus")
                else:
                    skipped_no_partner += 1
                    if args.verbose:
                        print(
                            f"  no_partner matchup_id={m.id} deck_id={m.deck_id} "
                            f"event_id={event_id!r} round={R}"
                        )
                continue

            deck_b = deck_rows.get(b_deck_id)
            if not deck_b:
                skipped_no_partner += 1
                continue

            p_b = player_by_id.get(deck_b.player_id)
            display_b = (p_b.display_name if p_b else None) or _trim(deck_b.player) or "(unknown)"
            arch_b = _trim(deck_b.archetype)

            if is_placeholder_display_name(display_b):
                skipped_target_still_placeholder += 1
                if args.verbose:
                    print(
                        f"  target_still_unnamed matchup_id={m.id} -> opponent deck_id={b_deck_id} "
                        f"player={display_b!r} (rename that deck's player in the app first)"
                    )
                continue

            want_deck_id = b_deck_id
            want_pid = deck_b.player_id
            want_name = display_b
            want_arch = arch_b if arch_b else None

            if (
                m.opponent_deck_id == want_deck_id
                and m.opponent_player_id == want_pid
                and _trim(m.opponent_player) == want_name
            ):
                unchanged += 1
                continue

            if args.verbose:
                print(
                    f"  fix matchup_id={m.id} reporter_deck={m.deck_id} round={R} via {how} -> "
                    f"opponent_deck_id={want_deck_id} opponent_player_id={want_pid} "
                    f"opponent_player={want_name!r}"
                )

            if args.apply:
                m.opponent_deck_id = want_deck_id
                m.opponent_player_id = want_pid
                m.opponent_player = want_name
                if want_arch:
                    m.opponent_archetype = want_arch
            updated += 1
            if how == "symmetric":
                updated_symmetric += 1
            elif how == "sibling_round":
                updated_sibling_round += 1
            elif how == "sibling_deck":
                updated_sibling_deck += 1
            elif how == "event":
                updated_event_consensus += 1
            elif how == "signature":
                updated_signature += 1

        mode = "DRY-RUN" if args.dry_run else "APPLY"
        print(f"[{mode}] rows to update: {updated}")
        print(
            f"[{mode}]   via symmetric (inverse in round): {updated_symmetric}; "
            f"same deck+opponent+round: {updated_sibling_round}; "
            f"same deck+opponent (event): {updated_sibling_deck}; "
            f"event+placeholder consensus: {updated_event_consensus}; "
            f"result-path signature: {updated_signature}"
        )
        print(f"[{mode}] unchanged (already correct): {unchanged}")
        print(f"[{mode}] skipped — round NULL and no resolution: {skipped_no_round}")
        print(f"[{mode}] skipped — no partner / consensus: {skipped_no_partner}")
        print(f"[{mode}] skipped — ambiguous multiple opponent decks: {ambiguous}")
        print(f"[{mode}] skipped — opponent deck still Unnamed*: {skipped_target_still_placeholder}")
        if args.apply:
            print("Done.")


if __name__ == "__main__":
    main()
