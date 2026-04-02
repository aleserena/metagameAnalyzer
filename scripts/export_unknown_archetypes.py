"""
Export all data related to "(unknown)" archetypes for manual review and fixes.

Covers:
- Decks where `decks.archetype` is NULL, empty, or "(unknown)" (case-insensitive)
- Matchups where `matchups.opponent_archetype` is missing/unknown (with context and
  optional suggested value from the opponent deck's `decks.archetype`)

Requires PostgreSQL (`DATABASE_URL`). Output is JSON (pretty-printed by default).

Optional deletion removes matchup rows where `opponent_archetype` is missing/unknown and/or the
row's deck has an unknown archetype, plus inverse mirror rows (see `--delete-matchups`).
Bye and drop rounds (`result` is bye or drop) are excluded from export lists and from deletion.

Examples:
  python3 -m scripts.export_unknown_archetypes
  python3 -m scripts.export_unknown_archetypes -o reports/unknown.json
  python3 -m scripts.export_unknown_archetypes --no-boards   # smaller file: drop main/side
  python3 -m scripts.export_unknown_archetypes --delete-matchups --dry-run
  python3 -m scripts.export_unknown_archetypes --delete-matchups --apply --no-export
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from api import db as _db
from src.mtgtop8.config import BASE_URL


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


def _is_unknown(s: str | None) -> bool:
    t = (s or "").strip()
    if not t:
        return True
    return t.lower() == "(unknown)"


def _mtgtop8_deck_url(event_id: str, deck_id: int, format_id: str) -> str | None:
    eid = (event_id or "").strip()
    if not eid or not str(eid).isdigit():
        return None
    fid = (format_id or "").strip() or "EDH"
    return f"{BASE_URL}/event?e={eid}&d={deck_id}&f={fid}"


def _matchup_to_dict(m: _db.MatchupRow) -> dict:
    return {
        "id": m.id,
        "deck_id": m.deck_id,
        "opponent_player_id": m.opponent_player_id,
        "opponent_player": m.opponent_player,
        "opponent_deck_id": m.opponent_deck_id,
        "opponent_archetype": m.opponent_archetype,
        "result": m.result,
        "result_note": m.result_note,
        "round": m.round,
    }


def _strip_boards(d: dict) -> dict:
    out = dict(d)
    out["mainboard"] = f"<{len(out.get('mainboard') or [])} cards>"
    out["sideboard"] = f"<{len(out.get('sideboard') or [])} cards>"
    return out


def _filter_matchup_opponent_archetype_unknown(or_, func, MatchupRow):
    """SQLAlchemy filter: matchups.opponent_archetype is NULL, empty, or (unknown)."""
    return or_(
        MatchupRow.opponent_archetype.is_(None),
        func.trim(MatchupRow.opponent_archetype) == "",
        func.lower(func.trim(MatchupRow.opponent_archetype)) == "(unknown)",
    )


def _filter_deck_archetype_unknown(or_, func, DeckRow):
    """SQLAlchemy filter: decks.archetype is NULL, empty, or (unknown)."""
    return or_(
        DeckRow.archetype.is_(None),
        func.trim(DeckRow.archetype) == "",
        func.lower(func.trim(DeckRow.archetype)) == "(unknown)",
    )


def _filter_exclude_bye_and_drop(or_, func, and_, MatchupRow):
    """Exclude bye/drop rounds (result is bye or drop, case-insensitive)."""
    r = func.lower(func.trim(MatchupRow.result))
    return or_(
        MatchupRow.result.is_(None),
        and_(r != "bye", r != "drop"),
    )


def _find_inverse_matchup(session, m: _db.MatchupRow) -> _db.MatchupRow | None:
    """Opposite-direction row created by upsert_matchups_for_deck (same round)."""
    if m.opponent_deck_id is None:
        return None
    r = (m.result or "").strip().lower()
    if r in ("bye", "drop"):
        return None
    q = session.query(_db.MatchupRow).filter(
        _db.MatchupRow.deck_id == m.opponent_deck_id,
        _db.MatchupRow.opponent_deck_id == m.deck_id,
    )
    if m.round is None:
        q = q.filter(_db.MatchupRow.round.is_(None))
    else:
        q = q.filter(_db.MatchupRow.round == m.round)
    return q.first()


def _collect_matchup_ids_to_delete(session, or_, func, and_, DeckRow, MatchupRow) -> set[int]:
    """Rows where opponent_archetype is missing/unknown OR the row's deck has unknown archetype; plus inverse rows."""
    q = (
        session.query(MatchupRow)
        .join(DeckRow, MatchupRow.deck_id == DeckRow.deck_id)
        .filter(
            and_(
                _filter_exclude_bye_and_drop(or_, func, and_, MatchupRow),
                or_(
                    _filter_matchup_opponent_archetype_unknown(or_, func, MatchupRow),
                    _filter_deck_archetype_unknown(or_, func, DeckRow),
                ),
            )
        )
    )
    primary = q.all()
    ids: set[int] = set()
    for row in primary:
        ids.add(row.id)
        inv = _find_inverse_matchup(session, row)
        if inv is not None:
            ids.add(inv.id)
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write JSON here (default: unknown_archetypes_<timestamp>.json in cwd)",
    )
    parser.add_argument(
        "--no-boards",
        action="store_true",
        help="Omit mainboard/sideboard (counts only) to reduce file size",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Minified JSON (no indentation)",
    )
    parser.add_argument(
        "--delete-matchups",
        action="store_true",
        help=(
            "Delete matchup rows where opponent_archetype is missing/unknown OR the row's deck "
            "has unknown archetype; also removes inverse mirror rows when present. "
            "Bye/drop rounds are never selected. Requires --dry-run or --apply."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --delete-matchups: print how many rows would be deleted (no DB writes)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="With --delete-matchups: perform the deletion",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Do not write the JSON report file",
    )
    args = parser.parse_args()

    if args.delete_matchups and not args.dry_run and not args.apply:
        parser.error("--delete-matchups requires --dry-run or --apply")
    if (args.dry_run or args.apply) and not args.delete_matchups:
        parser.error("--dry-run and --apply are only valid with --delete-matchups")

    _load_env()

    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    from sqlalchemy import and_, func, or_
    from sqlalchemy.orm import aliased

    OppDeck = aliased(_db.DeckRow)

    export_at = datetime.now(timezone.utc).isoformat()
    delete_summary: dict | None = None

    with _db.session_scope() as session:
        # --- Decks with unknown archetype ---
        unk_deck_rows = (
            session.query(_db.DeckRow, _db.EventRow, _db.PlayerRow.display_name)
            .outerjoin(_db.EventRow, _db.DeckRow.event_id == _db.EventRow.event_id)
            .outerjoin(_db.PlayerRow, _db.DeckRow.player_id == _db.PlayerRow.id)
            .filter(_filter_deck_archetype_unknown(or_, func, _db.DeckRow))
            .order_by(_db.DeckRow.event_id, _db.DeckRow.deck_id)
            .all()
        )

        decks_unknown: list[dict] = []

        for drow, ev, pname in unk_deck_rows:
            deck_d = _db.deck_row_to_dict(drow, pname)
            if args.no_boards:
                deck_d = _strip_boards(deck_d)

            ev_d = None
            if ev:
                ev_d = {
                    "event_id": ev.event_id,
                    "origin": ev.origin,
                    "format_id": ev.format_id,
                    "name": ev.name,
                    "store": ev.store,
                    "location": ev.location,
                    "date": ev.date,
                    "player_count": ev.player_count,
                }

            as_player = (
                session.query(_db.MatchupRow)
                .filter(
                    _db.MatchupRow.deck_id == drow.deck_id,
                    _filter_exclude_bye_and_drop(or_, func, and_, _db.MatchupRow),
                )
                .all()
            )
            as_opp = (
                session.query(_db.MatchupRow)
                .filter(
                    _db.MatchupRow.opponent_deck_id == drow.deck_id,
                    _filter_exclude_bye_and_drop(or_, func, and_, _db.MatchupRow),
                )
                .all()
            )

            eid = str(drow.event_id)
            decks_unknown.append(
                {
                    "event_id": eid,
                    "deck": deck_d,
                    "event": ev_d,
                    "mtgtop8_deck_url": _mtgtop8_deck_url(eid, drow.deck_id, drow.format_id or ""),
                    "matchups_where_this_deck_played": [_matchup_to_dict(m) for m in as_player],
                    "matchups_where_this_deck_was_opponent": [_matchup_to_dict(m) for m in as_opp],
                }
            )

        # --- Matchups with unknown opponent archetype (may include rows already covered above) ---
        mu_rows = (
            session.query(_db.MatchupRow, _db.DeckRow, OppDeck)
            .join(_db.DeckRow, _db.MatchupRow.deck_id == _db.DeckRow.deck_id)
            .outerjoin(OppDeck, _db.MatchupRow.opponent_deck_id == OppDeck.deck_id)
            .filter(
                and_(
                    _filter_exclude_bye_and_drop(or_, func, and_, _db.MatchupRow),
                    _filter_matchup_opponent_archetype_unknown(or_, func, _db.MatchupRow),
                )
            )
            .order_by(_db.MatchupRow.deck_id, _db.MatchupRow.id)
            .all()
        )

        matchups_unknown_opp: list[dict] = []
        for m, deck_row, opp_deck in mu_rows:
            opp_arch = (opp_deck.archetype if opp_deck else None) or ""
            suggested = None
            if opp_arch.strip() and not _is_unknown(opp_arch):
                suggested = opp_arch.strip()

            deck_summary = _db.deck_row_to_dict(deck_row)
            if args.no_boards:
                deck_summary = _strip_boards(deck_summary)

            opp_summary = None
            if opp_deck:
                opp_summary = _db.deck_row_to_dict(opp_deck)
                if args.no_boards:
                    opp_summary = _strip_boards(opp_summary)

            eid = str(deck_row.event_id)
            opp_eid = str(opp_deck.event_id) if opp_deck else None
            matchups_unknown_opp.append(
                {
                    "event_id": eid,
                    "opponent_event_id": opp_eid,
                    "matchup": _matchup_to_dict(m),
                    "deck_archetype": (deck_row.archetype or "").strip() or "(unknown)",
                    "suggested_opponent_archetype_from_opponent_deck": suggested,
                    "deck": deck_summary,
                    "opponent_deck": opp_summary,
                    "mtgtop8_opponent_deck_url": _mtgtop8_deck_url(
                        str(opp_deck.event_id), opp_deck.deck_id, opp_deck.format_id or ""
                    )
                    if opp_deck
                    else None,
                }
            )

        # --- Optional: delete matchup rows (export built above uses DB state before delete) ---
        if args.delete_matchups:
            delete_ids = _collect_matchup_ids_to_delete(
                session, or_, func, and_, _db.DeckRow, _db.MatchupRow
            )
            mode = "dry_run" if args.dry_run else "applied"
            sample = sorted(delete_ids)[:40]
            delete_summary = {
                "mode": mode,
                "criteria": (
                    "matchups.opponent_archetype is NULL/empty/(unknown) OR decks.archetype "
                    "(for matchups.deck_id) is NULL/empty/(unknown); includes inverse mirror rows; "
                    "excludes result=bye/drop"
                ),
                "matchup_row_ids_count": len(delete_ids),
                "matchup_row_ids_sample": sample,
            }
            if args.apply and delete_ids:
                CHUNK = 5000
                ids_list = list(delete_ids)
                deleted_total = 0
                for i in range(0, len(ids_list), CHUNK):
                    part = ids_list[i : i + CHUNK]
                    deleted_total += (
                        session.query(_db.MatchupRow)
                        .filter(_db.MatchupRow.id.in_(part))
                        .delete(synchronize_session=False)
                    )
                delete_summary["rows_deleted"] = deleted_total
            elif args.apply:
                delete_summary["rows_deleted"] = 0

            label = "DRY-RUN" if args.dry_run else "APPLY"
            print(f"[{label}] matchups to delete (including inverse rows): {len(delete_ids)}")
            if sample:
                print(f"[{label}] id sample (up to 40): {sample}")

    out_path = args.output
    if out_path is None:
        ts = re.sub(r"[^\d]", "", datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
        out_path = Path.cwd() / f"unknown_archetypes_{ts}.json"

    summary: dict = {
        "decks_with_unknown_archetype": len(decks_unknown),
        "matchup_rows_with_unknown_opponent_archetype": len(matchups_unknown_opp),
    }
    if delete_summary is not None:
        summary["matchup_delete"] = delete_summary

    payload = {
        "exported_at_utc": export_at,
        "summary": summary,
        "decks_with_unknown_archetype": decks_unknown,
        "matchups_with_unknown_opponent_archetype": matchups_unknown_opp,
        "notes": [
            "Use scripts.fix_matchup_unknown_archetypes to backfill opponent_archetype from opponent deck rows when possible.",
            "Use scripts.fix_deck_unknown_archetypes_from_matchups to infer deck archetype from matchup labels when unambiguous.",
            "For remaining decks, set archetype via the app or DB after checking mtgtop8_deck_url / deck lists.",
            "matchup_delete (when using --delete-matchups): removes rows where opponent_archetype is missing/unknown OR the row deck's archetype is unknown, plus paired inverse rows; bye/drop rounds are excluded.",
        ],
    }

    indent = None if args.compact else 2
    if not args.no_export:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print("Skipped JSON export (--no-export)")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
