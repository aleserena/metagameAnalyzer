"""
Persist dual-faced normalization for commander archetypes in PostgreSQL.

Rewrites ``decks.archetype``, each string in ``decks.commanders``, and
``matchups.opponent_archetype`` using the same rules as the API
(:func:`api.db.normalize_archetype_display`):

- ``Name / Other`` -> ``Name // Other`` (spacing), then
- ``Front // Back`` -> ``Front`` only

**Does not** change ``mainboard`` / ``sideboard`` card names (split cards like
``Fire // Ice`` must stay full names in deck lists).

After --apply, reload the API so in-memory caches refresh.

Examples:
  python3 -m scripts.normalize_dual_faced_archetypes_in_db --dry-run
  python3 -m scripts.normalize_dual_faced_archetypes_in_db --apply
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


def _norm_arch(s: str | None) -> str | None:
    return _db.normalize_archetype_display(s)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")
    if args.dry_run and args.apply:
        parser.error("Use only one of --dry-run or --apply")

    _load_env()
    if not _db.is_database_available():
        raise RuntimeError("Database not configured (DATABASE_URL unset or invalid).")

    report: dict = {
        "decks_archetype_changed": 0,
        "decks_commanders_changed": 0,
        "matchups_opponent_archetype_changed": 0,
        "deck_ids_archetype_sample": [],
        "deck_ids_commanders_sample": [],
        "matchup_ids_sample": [],
    }

    with _db.session_scope() as session:
        for row in session.query(_db.DeckRow).all():
            changed_arch = False
            a = row.archetype
            if a is not None and str(a).strip():
                na = _norm_arch(str(a))
                if na != a:
                    changed_arch = True
                    if args.apply:
                        row.archetype = na
            if changed_arch:
                report["decks_archetype_changed"] += 1
                if len(report["deck_ids_archetype_sample"]) < 25:
                    report["deck_ids_archetype_sample"].append(row.deck_id)

            cmd = row.commanders if isinstance(row.commanders, list) else []
            new_cmd: list[str] = []
            cmd_changed = False
            for c in cmd:
                if not c:
                    continue
                sc = str(c)
                nc = _norm_arch(sc) or sc
                if nc != sc:
                    cmd_changed = True
                new_cmd.append(nc)
            if cmd_changed:
                report["decks_commanders_changed"] += 1
                if len(report["deck_ids_commanders_sample"]) < 25:
                    report["deck_ids_commanders_sample"].append(row.deck_id)
                if args.apply:
                    row.commanders = new_cmd

        for m in session.query(_db.MatchupRow).all():
            oa = m.opponent_archetype
            if oa is None or not str(oa).strip():
                continue
            noa = _norm_arch(str(oa))
            if noa != oa:
                report["matchups_opponent_archetype_changed"] += 1
                if len(report["matchup_ids_sample"]) < 25:
                    report["matchup_ids_sample"].append(m.id)
                if args.apply:
                    m.opponent_archetype = noa

    report["mode"] = "apply" if args.apply else "dry_run"
    print(json.dumps(report, indent=2))
    if args.apply:
        print("Committed. Restart the API if it caches deck lists.")


if __name__ == "__main__":
    main()
