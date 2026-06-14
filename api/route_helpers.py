"""Helper functions shared by more than one router (pure; no app state)."""

import os

from fastapi import Request


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


def _parse_deck_date(s: str) -> tuple[int, int, int] | None:
    """Parse DD/MM/YY or DD/MM/YYYY to (year, month, day) for comparison. Returns None if invalid."""
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
