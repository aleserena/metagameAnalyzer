"""Date parsing shared by the models, the migration's twin and the filter helpers.

Dates are stored as DATE (``event_date``) and travel through the API as DD/MM/YY text. Input may be
DD/MM/YY (scraped) or DD/MM/YYYY; a two-digit year is always 20xx.
This module must not import from ``api``.
"""

from __future__ import annotations

from datetime import date


def parse_ddmmyy(s: str | None) -> date | None:
    """Parse DD/MM/YY or DD/MM/YYYY; ``None`` for anything else, impossible dates included."""
    if not s:
        return None
    parts = s.strip().split("/")
    if len(parts) != 3 or not all(p.isascii() and p.isdigit() for p in parts):
        return None
    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
    if len(parts[2]) <= 2:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def format_ddmmyy(d: date | None) -> str:
    """``DD/MM/YY``; ``""`` for ``None``. The inverse of :func:`parse_ddmmyy` for years 2000-2099."""
    if d is None:
        return ""
    return f"{d.day:02d}/{d.month:02d}/{d.year % 100:02d}"


def parse_bound(s: str | None) -> date | None:
    """A filter bound: DD/MM/YY(YY), else ISO ``YYYY-MM-DD`` (first 10 characters)."""
    parsed = parse_ddmmyy(s)
    if parsed is not None:
        return parsed
    if not s:
        return None
    try:
        return date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def in_range(deck_date: str, date_from: str | None, date_to: str | None) -> bool:
    """Inclusive range test. An unparseable deck date is in range; an unparseable bound is ignored."""
    d = parse_ddmmyy(deck_date)
    if d is None:
        return True
    start = parse_bound(date_from)
    if start is not None and d < start:
        return False
    end = parse_bound(date_to)
    if end is not None and d > end:
        return False
    return True


def sort_key(s: str | None) -> str:
    """``YYMMDD`` for a parseable date, else the input unchanged."""
    d = parse_ddmmyy(s)
    if d is None:
        return s  # type: ignore[return-value]
    return f"{d.year % 100:02d}{d.month:02d}{d.day:02d}"
