"""Helper functions shared by more than one router (pure; no app state)."""

import os
from collections.abc import Callable

from fastapi import Request

from api.dates import in_range as _date_in_range  # noqa: F401  (re-exported for routers)
from api.results import invert_result


def _upload_link_base_url(request: Request) -> str:
    """Base URL for upload links (e.g. https://app.example.com)."""
    base = os.getenv("PUBLIC_APP_URL", "").strip()
    if base:
        return base.rstrip("/")
    return str(request.base_url).rstrip("/")


def _matchup_result_to_canonical(result: str) -> str:
    """Map result string to canonical win/loss/draw/intentional_draw/bye/drop for consistency check."""
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
    """True if result is any intentional-draw variant (stored as distinct state; used as win/loss/draw in calcs)."""
    r = (result or "").strip().lower()
    return r in ("intentional_draw", "intentional_draw_win", "intentional_draw_loss")


def _matchup_result_consistent(result_a: str, result_b: str) -> bool:
    """True if the pair is consistent: one win + one loss, or both draw/intentional_draw. Bye/drop have no pair."""
    a = _matchup_result_to_canonical(result_a)
    b = _matchup_result_to_canonical(result_b)
    if a in ("bye", "drop") or b in ("bye", "drop"):
        return True
    if a in ("draw", "intentional_draw") and b in ("draw", "intentional_draw"):
        return True
    if (a == "win" and b == "loss") or (a == "loss" and b == "win"):
        return True
    return False


def find_matchup_discrepancies(rows: list[dict]) -> list[tuple[dict, dict]]:
    """Find inconsistent match pairs.

    Rows (keys deck_id, opponent_deck_id, result, round) are grouped by (sorted deck pair, round).
    For every group of exactly two rows whose results disagree, returns
    (row_from_lower_deck_id, row_from_higher_deck_id).
    """
    groups: dict[tuple[int, int, int | None], list[dict]] = {}
    for r in rows:
        if r.get("opponent_deck_id") is None:
            continue
        lo, hi = sorted([r["deck_id"], r["opponent_deck_id"]])
        groups.setdefault((lo, hi, r.get("round")), []).append(r)
    found: list[tuple[dict, dict]] = []
    for (lo, hi, _rnd), group in groups.items():
        if len(group) != 2:
            continue
        from_lo = next((m for m in group if m["deck_id"] == lo), None)
        from_hi = next((m for m in group if m["deck_id"] == hi), None)
        if from_lo is None or from_hi is None:
            continue
        if not _matchup_result_consistent(from_lo.get("result") or "", from_hi.get("result") or ""):
            found.append((from_lo, from_hi))
    return found


def opponent_report_to_prefill(report: dict, normalize_player: Callable[[str], str]) -> dict | None:
    """Invert a matchup an opponent reported against this player into a form prefill row.

    Returns None when the reporting player is missing/unknown.
    """
    res = (report.get("result") or "").strip().lower()
    inv_result = invert_result(res)
    if inv_result not in ("win", "loss", "intentional_draw_win", "intentional_draw_loss"):
        inv_result = "draw"
    reporting_player = normalize_player((report.get("reporting_player") or "").strip())
    if not reporting_player or reporting_player == "(unknown)":
        return None
    return {
        "opponent_player": reporting_player,
        "result": inv_result,
        "intentional_draw": _is_intentional_draw_result(res),
        "round": report.get("round"),
    }
