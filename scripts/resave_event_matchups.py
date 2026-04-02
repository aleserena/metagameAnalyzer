"""
Re-save all matchups for each event through `upsert_matchups_for_deck` so stored rows
reflect current logic (player names, archetypes on inverse rows, etc.).

For each event, loads each deck's matchups, writes them back in deterministic `deck_id`
order, then compares a normalized snapshot before vs after. If nothing changed semantically,
the event is reported as unchanged (row IDs may still be reassigned).

Requires PostgreSQL (`DATABASE_URL`).

Examples:
  python3 -m scripts.resave_event_matchups --dry-run
  python3 -m scripts.resave_event_matchups --dry-run --quiet
  python3 -m scripts.resave_event_matchups --apply
  python3 -m scripts.resave_event_matchups --dry-run --event-id 82555
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from api import db as _db

ROW_KEYS = (
    "opponent_player_id",
    "opponent_player",
    "opponent_deck_id",
    "opponent_archetype",
    "result",
    "result_note",
    "round",
)


def _row_dict(t: tuple) -> dict:
    return {ROW_KEYS[i]: t[i] for i in range(len(ROW_KEYS))}


def _row_match_key(t: tuple) -> tuple:
    """(round, opponent_deck_id, opponent_player_id) — pair rows before/after resave."""
    return (t[6], t[2], t[0])


def _diff_deck_snapshots(
    before: tuple,
    after: tuple,
    *,
    max_field_changes: int = 200,
    max_stray_rows: int = 50,
) -> dict:
    """
    Compare two normalized snapshots (multiset of row tuples).
    Pairs rows with the same match key to emit field-level changes; leftover rows are removed/added.
    """
    c_rem = Counter(before) - Counter(after)
    c_add = Counter(after) - Counter(before)

    rem_by_key: dict[tuple, list[tuple]] = defaultdict(list)
    for t in c_rem.elements():
        rem_by_key[_row_match_key(t)].append(t)
    add_by_key: dict[tuple, list[tuple]] = defaultdict(list)
    for t in c_add.elements():
        add_by_key[_row_match_key(t)].append(t)

    field_changes: list[dict] = []
    stray_rem: list[tuple] = []
    stray_add: list[tuple] = []
    all_keys = set(rem_by_key) | set(add_by_key)

    for k in sorted(all_keys, key=lambda x: (x[0] is None, x[0] if x[0] is not None else -1, x[1] or 0, x[2] or 0)):
        rs = rem_by_key.get(k, [])
        as_ = add_by_key.get(k, [])
        m = min(len(rs), len(as_))
        for i in range(m):
            d1 = _row_dict(rs[i])
            d2 = _row_dict(as_[i])
            if d1 == d2:
                continue
            for fld in ROW_KEYS:
                if d1[fld] != d2[fld]:
                    field_changes.append(
                        {
                            "match_key": {
                                "round": k[0],
                                "opponent_deck_id": k[1],
                                "opponent_player_id": k[2],
                            },
                            "field": fld,
                            "before": d1[fld],
                            "after": d2[fld],
                        }
                    )
        stray_rem.extend(rs[m:])
        stray_add.extend(as_[m:])

    fc_trunc = len(field_changes) > max_field_changes
    field_changes = field_changes[:max_field_changes]
    return {
        "field_changes": field_changes,
        "field_changes_truncated": fc_trunc,
        "rows_removed": [_row_dict(t) for t in stray_rem[:max_stray_rows]],
        "rows_added": [_row_dict(t) for t in stray_add[:max_stray_rows]],
        "stray_removed_count": len(stray_rem),
        "stray_added_count": len(stray_add),
        "stray_truncated": len(stray_rem) > max_stray_rows or len(stray_add) > max_stray_rows,
    }


def _print_dry_run_event_details(ev: dict, *, max_print: int) -> None:
    """Human-readable field diffs for --dry-run (stdout)."""
    printed = 0

    def line(s: str) -> bool:
        nonlocal printed
        if printed >= max_print:
            return False
        print(s)
        printed += 1
        return True

    for d in ev.get("deck_diffs") or []:
        det = d.get("detail") or {}
        if not line(
            f"    deck {d['deck_id']} (rows {d['before_count']} -> {d['after_count']}):"
        ):
            print(f"      ... stopping after {max_print} lines (--max-print-lines)")
            return
        if det.get("field_changes_truncated"):
            line(
                "      (field_changes truncated in JSON; use --max-diff-fields)"
            )
        for fc in det.get("field_changes") or []:
            if not line(
                f"      round={fc['match_key']['round']} opp_deck="
                f"{fc['match_key']['opponent_deck_id']} opp_pid="
                f"{fc['match_key']['opponent_player_id']}"
            ):
                print(f"      ... stopping after {max_print} lines (--max-print-lines)")
                return
            if not line(f"        {fc['field']}: {fc['before']!r} -> {fc['after']!r}"):
                print(f"      ... stopping after {max_print} lines (--max-print-lines)")
                return

        sr = int(det.get("stray_removed_count") or 0)
        sa = int(det.get("stray_added_count") or 0)
        if sr or sa:
            if not line(f"      unmatched multiset rows: removed {sr}, added {sa}"):
                print(f"      ... stopping after {max_print} lines (--max-print-lines)")
                return
            for r in det.get("rows_removed") or []:
                if not line(f"        - removed {r}"):
                    print(f"      ... stopping after {max_print} lines (--max-print-lines)")
                    return
            for r in det.get("rows_added") or []:
                if not line(f"        + added {r}"):
                    print(f"      ... stopping after {max_print} lines (--max-print-lines)")
                    return
            if det.get("stray_truncated"):
                line("      (stray samples truncated; use --max-stray-rows)")


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


def _canonical_tuple(m: dict) -> tuple:
    """Stable, id-agnostic representation for comparison."""
    oa = m.get("opponent_archetype")
    if oa is not None and isinstance(oa, str) and not oa.strip():
        oa = None
    elif oa is not None:
        oa = str(oa).strip() or None
    rn = m.get("result_note")
    if rn is not None and str(rn).strip() == "":
        rn = None
    return (
        m.get("opponent_player_id"),
        (m.get("opponent_player") or "").strip(),
        m.get("opponent_deck_id"),
        oa,
        (m.get("result") or "").strip().lower(),
        rn,
        m.get("round"),
    )


def _deck_snapshot(session, deck_id: int) -> tuple:
    raw = _db.list_matchups_by_deck(session, deck_id)
    rows = [_canonical_tuple(m) for m in raw]
    rows.sort(
        key=lambda t: (
            t[6] is None,
            t[6] if t[6] is not None else -1,
            t[2] if t[2] is not None else -1,
            t[1],
        )
    )
    return tuple(rows)


def _event_snapshot_map(session, deck_ids: list[int]) -> dict[int, tuple]:
    """deck_id -> normalized matchup tuples for that deck's rows only."""
    return {did: _deck_snapshot(session, did) for did in deck_ids}


def _matchups_for_upsert(rows: list[dict]) -> list[dict]:
    """Shape expected by upsert_matchups_for_deck (no id)."""
    out: list[dict] = []
    for m in rows:
        rn = m.get("result_note")
        if rn is not None and str(rn).strip() == "":
            rn = None
        out.append(
            {
                "opponent_player_id": m.get("opponent_player_id"),
                "opponent_player": (m.get("opponent_player") or "").strip(),
                "opponent_deck_id": m.get("opponent_deck_id"),
                "opponent_archetype": m.get("opponent_archetype"),
                "result": (m.get("result") or "").strip(),
                "result_note": rn,
                "round": m.get("round"),
            }
        )
    return out


def _deck_ids_for_event(session, event_id: str) -> list[int]:
    eid = _db._event_id_str(event_id)
    return sorted(
        r[0] for r in session.query(_db.DeckRow.deck_id).filter(_db.DeckRow.event_id == eid).all()
    )


def _all_event_ids(session) -> list[str]:
    return [
        _db._event_id_str(r[0])
        for r in session.query(_db.EventRow.event_id)
        .order_by(_db.EventRow.date.desc(), _db.EventRow.event_id)
        .all()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Re-save in a transaction and roll back; report which events would change",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit re-saved matchups per event",
    )
    parser.add_argument(
        "--event-id",
        action="append",
        dest="event_ids",
        metavar="ID",
        help="Only process this event (repeat for multiple). Default: all events",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write a JSON summary to this path",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="With --dry-run: only print summary lines, not per-field diffs",
    )
    parser.add_argument(
        "--max-diff-fields",
        type=int,
        default=500,
        metavar="N",
        help="Max field-level changes to store per deck (default 500)",
    )
    parser.add_argument(
        "--max-stray-rows",
        type=int,
        default=50,
        metavar="N",
        help="Max unmatched removed/added rows to store per deck (default 50)",
    )
    parser.add_argument(
        "--max-print-lines",
        type=int,
        default=150,
        metavar="N",
        help="Max stdout lines of detail for --dry-run (default 150)",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify either --dry-run or --apply")
    if args.dry_run and args.apply:
        parser.error("Use only one of --dry-run or --apply")

    _load_env()

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    factory = _db.get_session_factory_cached()
    if factory is None:
        raise RuntimeError("Database session factory unavailable")

    report: dict = {"mode": "dry_run" if args.dry_run else "apply", "events": []}

    with factory() as session:
        event_ids = args.event_ids if args.event_ids else _all_event_ids(session)

    for eid in event_ids:
        eid = _db._event_id_str(eid)
        session = factory()
        try:
            deck_ids = _deck_ids_for_event(session, eid)
            if not deck_ids:
                report["events"].append(
                    {
                        "event_id": eid,
                        "deck_count": 0,
                        "skipped": True,
                        "reason": "no decks",
                    }
                )
                session.rollback()
                continue

            before = _event_snapshot_map(session, deck_ids)

            for deck_id in deck_ids:
                loaded = _db.list_matchups_by_deck(session, deck_id)
                items = _matchups_for_upsert(loaded)
                _db.upsert_matchups_for_deck(session, deck_id, items)

            after = _event_snapshot_map(session, deck_ids)
            unchanged = before == after

            ev = {
                "event_id": eid,
                "deck_count": len(deck_ids),
                "unchanged": unchanged,
            }
            if not unchanged:
                diffs = []
                for did in sorted(deck_ids):
                    b = before[did]
                    a = after[did]
                    if b != a:
                        detail = _diff_deck_snapshots(
                            b,
                            a,
                            max_field_changes=args.max_diff_fields,
                            max_stray_rows=args.max_stray_rows,
                        )
                        diffs.append(
                            {
                                "deck_id": did,
                                "before_count": len(b),
                                "after_count": len(a),
                                "detail": detail,
                            }
                        )
                ev["deck_diffs"] = diffs
            report["events"].append(ev)

            if args.dry_run:
                session.rollback()
            else:
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    changed = [e for e in report["events"] if not e.get("skipped") and not e.get("unchanged", True)]
    unchanged_n = len([e for e in report["events"] if not e.get("skipped") and e.get("unchanged")])

    print(json.dumps({"summary": {"events_total": len(report["events"]), "unchanged": unchanged_n, "would_change_or_changed": len(changed)}}, indent=2))
    for e in report["events"]:
        if e.get("skipped"):
            print(f"[{e['event_id']}] skipped: {e.get('reason')}")
        else:
            tag = "OK no change" if e.get("unchanged") else "CHANGED"
            print(f"[{e['event_id']}] decks={e['deck_count']} {tag}")
            if not e.get("unchanged") and e.get("deck_diffs"):
                if args.dry_run and not args.quiet:
                    print("  Would change:")
                    _print_dry_run_event_details(e, max_print=args.max_print_lines)
                else:
                    for d in e["deck_diffs"]:
                        print(
                            f"    deck {d['deck_id']}: rows {d['before_count']} -> {d['after_count']}"
                        )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.json_out}")


if __name__ == "__main__":
    main()
