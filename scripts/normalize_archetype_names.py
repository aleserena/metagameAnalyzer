"""
Normalize duplicate archetype spellings in ``decks.archetype`` and ``matchups.opponent_archetype``.

Default: merge ``Azusa, Lost But Seeking`` (capital B) into the official card name
``Azusa, Lost but Seeking`` so matrix/list stats aggregate under one label.

Requires PostgreSQL (``DATABASE_URL``).

Examples:
  python3 -m scripts.normalize_archetype_names --dry-run
  python3 -m scripts.normalize_archetype_names --apply
  python3 -m scripts.normalize_archetype_names --dry-run --to "Azusa, Lost But Seeking" --from "Azusa, Lost but Seeking"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from api import db as _db
from sqlalchemy import func, or_

# Official English card name uses lowercase "but" (see Gatherer / Scryfall).
DEFAULT_CANONICAL = "Azusa, Lost but Seeking"
DEFAULT_FROM_VARIANTS = ("Azusa, Lost But Seeking",)


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--to",
        default=DEFAULT_CANONICAL,
        help=f"Canonical archetype string after update (default: {DEFAULT_CANONICAL!r})",
    )
    parser.add_argument(
        "--from",
        dest="from_variants",
        action="append",
        metavar="STRING",
        help="Spelling to replace (repeatable). Default: Azusa with capital B in But",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")
    if args.dry_run and args.apply:
        parser.error("Use only one of --dry-run or --apply")

    _load_env()
    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    canonical = (args.to or "").strip()
    if not canonical:
        raise SystemExit("--to must be non-empty")

    raw_from = args.from_variants if args.from_variants else list(DEFAULT_FROM_VARIANTS)
    variants = sorted({(v or "").strip() for v in raw_from if (v or "").strip()})
    variants = [v for v in variants if v != canonical]
    if not variants:
        print(json.dumps({"message": "Nothing to do: no --from variants differ from --to", "to": canonical}))
        return

    report: dict = {
        "canonical": canonical,
        "from_variants": variants,
        "decks_updated": 0,
        "matchups_updated": 0,
        "deck_ids_sample": [],
        "matchup_ids_sample": [],
    }

    trim_deck = func.trim(_db.DeckRow.archetype)
    trim_m = func.trim(_db.MatchupRow.opponent_archetype)
    deck_cond = or_(*[trim_deck == v for v in variants])
    matchup_cond = or_(*[trim_m == v for v in variants])

    with _db.session_scope() as session:
        deck_rows = session.query(_db.DeckRow).filter(deck_cond).all()
        matchup_rows = session.query(_db.MatchupRow).filter(matchup_cond).all()

        report["decks_found"] = len(deck_rows)
        report["matchups_found"] = len(matchup_rows)
        report["deck_ids_sample"] = [r.deck_id for r in deck_rows[:30]]
        report["matchup_ids_sample"] = [r.id for r in matchup_rows[:30]]

        if args.apply:
            for r in deck_rows:
                r.archetype = canonical
            for r in matchup_rows:
                r.opponent_archetype = canonical
            report["decks_updated"] = len(deck_rows)
            report["matchups_updated"] = len(matchup_rows)
        else:
            report["decks_updated"] = len(deck_rows)
            report["matchups_updated"] = len(matchup_rows)

    mode = "apply" if args.apply else "dry_run"
    report["mode"] = mode
    print(json.dumps(report, indent=2))
    if args.apply:
        print("Committed. Restart the API if it caches archetype lists.")


if __name__ == "__main__":
    main()
