"""
Check whether saved matchup rows would appear in the archetype matchup matrix
(same rules as GET /api/v1/matchups/summary).

A row is "matrix-eligible" if it is not bye/drop and passes optional filters.
Among eligible rows, the matrix shows the cell for (your archetype -> opponent archetype)
only if that directional pair has at least ``matchups_min_matches`` aggregated matches
(settings key ``matchups_min_matches``, default 0).

Requires PostgreSQL (`DATABASE_URL`).

Examples:
  python3 -m scripts.validate_matchups_matrix_coverage
  python3 -m scripts.validate_matchups_matrix_coverage --format-id EDH
  python3 -m scripts.validate_matchups_matrix_coverage --event-id 82555 --json-out report.json
"""

from __future__ import annotations

import argparse
import json
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


def _matchup_result_to_canonical(result: str) -> str:
    r = (result or "").strip().lower()
    if r in ("bye", "drop"):
        return r
    if r in ("intentional_draw", "id"):
        return "intentional_draw"
    if r == "intentional_draw_win":
        return "win"
    if r == "intentional_draw_loss":
        return "loss"
    if r in ("2-1", "1-0"):
        return "win"
    if r in ("1-2", "0-1"):
        return "loss"
    if r in ("1-1", "0-0"):
        return "draw"
    if r in ("win", "loss", "draw"):
        return r
    return "draw"


def _is_intentional_draw_result(result: str) -> bool:
    r = (result or "").strip().lower()
    return r in ("intentional_draw", "intentional_draw_win", "intentional_draw_loss")


def _parse_deck_date(s: str) -> tuple[int, int, int] | None:
    if not s or not s.strip():
        return None
    parts = s.strip().split("/")
    if len(parts) != 3:
        return None
    try:
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        if year < 100:
            year += 2000 if year < 50 else 1900
        if 1 <= month <= 12 and 1 <= day <= 31:
            return (year, month, day)
    except (ValueError, IndexError):
        pass
    return None


def _date_in_range(deck_date_str: str, from_date: str | None, to_date: str | None) -> bool:
    if not from_date and not to_date:
        return True
    parsed = _parse_deck_date(deck_date_str)
    if not parsed:
        return True
    y, m, d = parsed
    if from_date:
        f = _parse_deck_date(from_date)
        if not f:
            try:
                from datetime import datetime as _dt

                _d = _dt.fromisoformat(from_date.replace("Z", "+00:00")[:10])
                f = (_d.year, _d.month, _d.day)
            except Exception:
                f = None
        if f and (y, m, d) < f:
            return False
    if to_date:
        t = _parse_deck_date(to_date)
        if not t:
            try:
                from datetime import datetime as _dt

                _d = _dt.fromisoformat(to_date.replace("Z", "+00:00")[:10])
                t = (_d.year, _d.month, _d.day)
            except Exception:
                t = None
        if t and (y, m, d) > t:
            return False
    return True


def _list_matchup_rows_with_ids(session) -> list[dict]:
    """Same shape as list_matchups_with_deck_info plus id, event_id on row (already on deck)."""
    rows = (
        session.query(_db.MatchupRow, _db.DeckRow)
        .join(_db.DeckRow, _db.MatchupRow.deck_id == _db.DeckRow.deck_id)
        .all()
    )
    out: list[dict] = []
    for m, d in rows:
        out.append(
            {
                "id": m.id,
                "deck_id": m.deck_id,
                "opponent_deck_id": m.opponent_deck_id,
                "archetype": (d.archetype or "").strip() or "(unknown)",
                "format_id": d.format_id or "",
                "event_id": d.event_id,
                "date": d.date or "",
                "opponent_archetype": (m.opponent_archetype or "").strip() or "(unknown)",
                "result": m.result or "loss",
                "result_note": m.result_note or "",
            }
        )
    return out


def _apply_query_filters(
    rows: list[dict],
    *,
    format_id: str | None,
    event_id_set: set[str] | None,
    date_from: str | None,
    date_to: str | None,
    archetype_set: set[str] | None,
) -> tuple[list[dict], list[dict]]:
    """Return (included, excluded_with_reason_meta)."""
    included: list[dict] = []
    excluded: list[dict] = []
    for r in rows:
        if format_id and (r.get("format_id") or "").strip().upper() != format_id.strip().upper():
            excluded.append({**r, "_exclude": "format_id"})
            continue
        if event_id_set is not None and (r.get("event_id") or "").strip() not in event_id_set:
            excluded.append({**r, "_exclude": "event_id"})
            continue
        if not _date_in_range(r.get("date") or "", date_from, date_to):
            excluded.append({**r, "_exclude": "date_range"})
            continue
        if archetype_set is not None:
            arch = (r.get("archetype") or "").strip()
            opp = (r.get("opponent_archetype") or "").strip()
            if arch.lower() not in archetype_set:
                excluded.append({**r, "_exclude": "archetype_filter"})
                continue
            if len(archetype_set) > 1 and opp.lower() not in archetype_set:
                excluded.append({**r, "_exclude": "archetype_filter_pair"})
                continue
        included.append(r)
    return included, excluded


def _build_agg_like_api(filtered: list[dict]) -> tuple[dict, dict[str, str]]:
    """Mirror api.main.get_matchups_summary aggregation (bye/drop already stripped from filtered)."""
    canonical_archetype: dict[str, str] = {}
    for r in filtered:
        for raw in [(r.get("archetype") or "").strip(), (r.get("opponent_archetype") or "").strip()]:
            if raw and raw.lower() not in ("bye", "drop"):
                canonical_archetype.setdefault(raw.lower(), raw)

    def to_effective_wld(row: dict):
        raw = (row.get("result") or "loss").strip().lower()
        if raw == "intentional_draw":
            return (0, 0, 1)
        if raw == "intentional_draw_win":
            return (1, 0, 0)
        if raw == "intentional_draw_loss":
            return (0, 1, 0)
        canonical = _matchup_result_to_canonical(row.get("result") or "loss")
        if canonical == "win":
            return (1, 0, 0)
        if canonical == "loss":
            return (0, 1, 0)
        return (0, 0, 1)

    def norm_arch(name: str) -> str:
        return canonical_archetype.get((name or "").lower(), name or "(unknown)")

    def add_to_agg(arch: str, opp: str, wins: int, losses: int, draws: int, is_intentional_draw: bool, matches: int):
        arch, opp = norm_arch(arch), norm_arch(opp)
        for (a, o), (aw, al, ad) in [((arch, opp), (wins, losses, draws)), ((opp, arch), (losses, wins, draws))]:
            key = (a.lower(), o.lower())
            if key not in agg:
                agg[key] = {
                    "wins": 0,
                    "losses": 0,
                    "draws": 0,
                    "intentional_draws": 0,
                    "matches": 0,
                    "archetype": a,
                    "opponent_archetype": o,
                }
            agg[key]["wins"] += aw
            agg[key]["losses"] += al
            agg[key]["draws"] += ad
            if is_intentional_draw:
                agg[key]["intentional_draws"] += 1
            agg[key]["matches"] += matches

    agg: dict = {}
    paired_rows = [r for r in filtered if r.get("opponent_deck_id") is not None]
    unpaired_rows = [r for r in filtered if r.get("opponent_deck_id") is None]

    by_match: dict[tuple[int, int], list[dict]] = {}
    for r in paired_rows:
        key = tuple(sorted([r["deck_id"], r["opponent_deck_id"]]))
        by_match.setdefault(key, []).append(r)

    for _match_key, match_rows in by_match.items():
        d_a, d_b = _match_key
        from_ab = [r for r in match_rows if (r["deck_id"], r["opponent_deck_id"]) == (d_a, d_b)]
        from_ba = [r for r in match_rows if (r["deck_id"], r["opponent_deck_id"]) == (d_b, d_a)]
        from_ab.sort(key=lambda x: (x.get("round") or 0, x.get("deck_id")))
        from_ba.sort(key=lambda x: (x.get("round") or 0, x.get("deck_id")))
        n_paired = min(len(from_ab), len(from_ba))
        for i in range(n_paired):
            ra, rb = from_ab[i], from_ba[i]
            c1 = _matchup_result_to_canonical((ra.get("result") or "").strip())
            c2 = _matchup_result_to_canonical((rb.get("result") or "").strip())
            if (c1 == "win" and c2 == "loss") or (c1 == "loss" and c2 == "win") or (
                c1 in ("draw", "intentional_draw") and c2 in ("draw", "intentional_draw")
            ):
                row = ra
            else:
                row = ra
            arch = (row.get("archetype") or "(unknown)").strip()
            opp = (row.get("opponent_archetype") or "(unknown)").strip()
            wins, losses, draws = to_effective_wld(row)
            is_id = _is_intentional_draw_result(row.get("result") or "")
            add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)
        for i in range(n_paired, len(from_ab)):
            row = from_ab[i]
            arch = (row.get("archetype") or "(unknown)").strip()
            opp = (row.get("opponent_archetype") or "(unknown)").strip()
            wins, losses, draws = to_effective_wld(row)
            is_id = _is_intentional_draw_result(row.get("result") or "")
            add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)
        for i in range(n_paired, len(from_ba)):
            row = from_ba[i]
            arch = (row.get("archetype") or "(unknown)").strip()
            opp = (row.get("opponent_archetype") or "(unknown)").strip()
            wins, losses, draws = to_effective_wld(row)
            is_id = _is_intentional_draw_result(row.get("result") or "")
            add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)

    for r in unpaired_rows:
        arch = (r.get("archetype") or "(unknown)").strip()
        opp = (r.get("opponent_archetype") or "(unknown)").strip()
        wins, losses, draws = to_effective_wld(r)
        is_id = _is_intentional_draw_result(r.get("result") or "")
        add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)

    return agg, canonical_archetype


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format-id", default=None, help="Same as API format_id filter")
    parser.add_argument(
        "--event-id",
        action="append",
        dest="event_ids",
        metavar="ID",
        help="Limit to event(s); repeat flag",
    )
    parser.add_argument("--date-from", default=None, help="DD/MM/YY or ISO date")
    parser.add_argument("--date-to", default=None, help="DD/MM/YY or ISO date")
    parser.add_argument(
        "--archetype",
        action="append",
        dest="archetypes",
        metavar="NAME",
        help="Same as API archetype filter (repeat)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write full report JSON",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=30,
        metavar="N",
        help="Max matchup ids listed per issue category (default 30)",
    )
    args = parser.parse_args()

    _load_env()
    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    event_id_set = None
    if args.event_ids:
        event_id_set = {_db._event_id_str(x) for x in args.event_ids}
    archetype_set = None
    if args.archetypes:
        archetype_set = {x.strip().lower() for x in args.archetypes if (x or "").strip()}

    with _db.session_scope() as session:
        min_matches = _db.get_matchups_min_matches(session)
        raw_rows = _list_matchup_rows_with_ids(session)

    filtered, excluded_filters = _apply_query_filters(
        raw_rows,
        format_id=args.format_id,
        event_id_set=event_id_set,
        date_from=args.date_from,
        date_to=args.date_to,
        archetype_set=archetype_set,
    )

    bye_drop: list[dict] = []
    matrix_input: list[dict] = []
    for r in filtered:
        if (r.get("result") or "").strip().lower() in ("bye", "drop"):
            bye_drop.append(r)
        else:
            matrix_input.append(dict(r))

    agg, canonical_archetype = _build_agg_like_api(matrix_input)

    def norm_arch(name: str) -> str:
        return canonical_archetype.get((name or "").lower(), name or "(unknown)")

    hidden: list[dict] = []
    visible_n = 0
    for r in matrix_input:
        arch = norm_arch((r.get("archetype") or "(unknown)").strip())
        opp = norm_arch((r.get("opponent_archetype") or "(unknown)").strip())
        key = (arch.lower(), opp.lower())
        mcount = agg.get(key, {}).get("matches", 0)
        ok = mcount >= min_matches
        if ok:
            visible_n += 1
        else:
            hidden.append(
                {
                    "matchup_id": r["id"],
                    "deck_id": r["deck_id"],
                    "event_id": r.get("event_id"),
                    "directional_pair": [arch, opp],
                    "aggregated_matches_for_cell": mcount,
                    "min_matches": min_matches,
                }
            )

    report = {
        "min_matches_setting": min_matches,
        "totals": {
            "matchup_rows_in_db": len(raw_rows),
            "after_query_filters": len(filtered),
            "excluded_by_query_filters": len(excluded_filters),
            "bye_or_drop": len(bye_drop),
            "matrix_aggregation_rows": len(matrix_input),
            "eligible_rows_visible_directional": visible_n,
            "eligible_rows_hidden_below_min_matches": len(hidden),
        },
        "notes": [
            "Mirrors GET /api/v1/matchups/summary aggregation (paired/unpaired, add_to_agg).",
            "Visible = directional cell (your archetype -> opponent archetype) has matches >= min_matches.",
            "Bye/drop never appear in the matrix.",
        ],
        "hidden_examples": hidden[: args.max_examples],
        "bye_drop_ids_sample": [r["id"] for r in bye_drop[: args.max_examples]],
    }

    if len(hidden) > args.max_examples:
        report["hidden_examples_truncated"] = True

    print(json.dumps({"summary": report["totals"], "min_matches": min_matches}, indent=2))
    if hidden:
        print(
            f"Issue: {len(hidden)} matrix-eligible row(s) sit in archetype cells "
            f"with matches < min_matches ({min_matches}). "
            f"Showing up to {args.max_examples} matchup ids in hidden_examples (use --json-out)."
        )
    else:
        print("OK: every matrix-eligible row's directional archetype cell meets min_matches.")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.json_out}")


if __name__ == "__main__":
    main()
