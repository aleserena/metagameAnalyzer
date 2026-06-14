"""Pure helper functions used across API routes (no shared mutable state).

Date/rank/sort/filter utilities, card-name normalization, and request helpers.
For the in-memory deck list and caches see api.state; for auth see api.dependencies.
"""

import unicodedata
from datetime import date
from pathlib import Path

from fastapi import HTTPException, UploadFile
from src.mtgtop8.normalize import normalize_card_name as _normalize_card_name

from api.config import DATA_DIR, MAX_UPLOAD_JSON_BYTES

try:
    from api import db as _db
except ImportError:
    _db = None


def _normalize_search(s: str) -> str:
    """Lowercase and strip accents for relaxed substring matching."""
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


async def _read_upload_json_bytes_async(upload: UploadFile) -> bytes:
    content = await upload.read(MAX_UPLOAD_JSON_BYTES + 1)
    if len(content) > MAX_UPLOAD_JSON_BYTES:
        raise HTTPException(status_code=413, detail="Upload too large")
    return content


def _resolve_load_path_under_data_dir(raw: str) -> Path:
    """Resolve a relative path under DATA_DIR; reject absolute paths and path traversal."""
    if raw is None or not str(raw).strip():
        raise HTTPException(status_code=400, detail="Invalid path")
    rel = Path(str(raw).strip())
    if rel.is_absolute():
        raise HTTPException(status_code=400, detail="path must be relative to DATA_DIR")
    base = DATA_DIR.resolve()
    resolved = (base / rel).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="path must stay under DATA_DIR") from None
    return resolved


def _event_from_deck_dict(d: dict) -> dict:
    """Build a normalized event dict from a deck dict."""
    return {
        "event_id": d.get("event_id"),
        "event_name": d.get("event_name", ""),
        "store": "",
        "location": "",
        "date": d.get("date", ""),
        "format_id": d.get("format_id", ""),
        "player_count": d.get("player_count", 0),
        "origin": d.get("origin", "mtgtop8"),
    }


def _normalize_split_cards(decks: list[dict]) -> list[dict]:
    """Normalize card names in deck dicts (including split cards); archetype/commanders to front-face."""
    for d in decks:
        for section in ("mainboard", "sideboard"):
            cards = d.get(section, [])
            for card in cards:
                if isinstance(card, dict) and "card" in card:
                    card["card"] = _normalize_card_name(card["card"])
        if _db is not None:
            a = d.get("archetype")
            if a is not None and str(a).strip():
                nd = _db.normalize_archetype_display(str(a))
                if nd:
                    d["archetype"] = nd
            cmd = d.get("commanders")
            if isinstance(cmd, list):
                d["commanders"] = _db.normalize_commanders_list(cmd)
    return decks


def _normalize_card_entry(entry) -> dict | None:
    """Normalize a single card entry from dict or Pydantic model into {qty, card}."""
    if entry is None:
        return None
    if isinstance(entry, dict):
        qty = int(entry.get("qty", 1) or 1)
        raw = str(entry.get("card", ""))
    else:
        qty = int(getattr(entry, "qty", 1) or 1)
        raw = getattr(entry, "card", "") or ""
    name = _normalize_card_name(raw)
    if not name:
        return None
    return {"qty": qty, "card": name}


def _build_board(entries) -> list[dict]:
    """Normalize a list of card entries into [{qty, card}, ...], dropping empty names."""
    board: list[dict] = []
    for e in entries or []:
        normalized = _normalize_card_entry(e)
        if normalized:
            board.append(normalized)
    return board


def _normalize_commanders(commanders) -> list[str]:
    """Normalize a commanders list to normalized card-name strings."""
    if not commanders:
        return []
    return [_normalize_card_name(c) for c in commanders if _normalize_card_name(c)]


_RANK_ORDER = {"1": 0, "2": 1, "3-4": 2, "5-8": 3, "9-16": 4, "17-32": 5, "33-64": 6, "65-128": 7}


def _rank_sort_value(rank_str: str) -> int:
    """Return a numeric value for ordering ranks (1, 2, 3, ..., 12, ...). Uses lower bound for ranges like 3-4."""
    r = (rank_str or "").strip()
    if not r:
        return 999
    part = r.split("-")[0].strip()
    if not part.isdigit():
        return 999
    n = int(part)
    return n if 1 <= n <= 128 else 999


def _parse_date_sortkey(date_str: str) -> str:
    """Convert DD/MM/YY to YYMMDD for sorting."""
    parts = date_str.split("/")
    if len(parts) == 3:
        return parts[2] + parts[1] + parts[0]
    return date_str


def _date_yymmdd_to_parts(key: str) -> tuple[int, int, int] | None:
    """Convert a YYMMDD sort key to (yy, mm, dd) ints, or None if invalid."""
    if not key or not key.isdigit() or len(key) != 6:
        return None
    return int(key[0:2]), int(key[2:4]), int(key[4:6])


def _yymmdd_to_ordinal(key: str) -> int | None:
    """Convert a YYMMDD key to a day-ordinal (for day arithmetic).

    Uses 2000 + yy heuristic matching the rest of the codebase, which treats
    DD/MM/YY dates as 21st-century years.
    """
    parts = _date_yymmdd_to_parts(key)
    if not parts:
        return None
    yy, mm, dd = parts
    try:
        return date(2000 + yy, mm, dd).toordinal()
    except ValueError:
        return None


def _yymmdd_to_display(key: str) -> str | None:
    """Convert a YYMMDD sort key back to DD/MM/YY display format."""
    parts = _date_yymmdd_to_parts(key)
    if not parts:
        return None
    yy, mm, dd = parts
    return f"{dd:02d}/{mm:02d}/{yy:02d}"


def _window_summary_from_dicts(deck_dicts: list[dict]) -> dict:
    """Summarize a window: deck_count, event_count, date_from, date_to."""
    if not deck_dicts:
        return {"deck_count": 0, "event_count": 0, "date_from": None, "date_to": None}
    keys = [_parse_date_sortkey(d.get("date", "") or "") for d in deck_dicts]
    valid = [k for k in keys if k.isdigit() and len(k) == 6]
    date_from = _yymmdd_to_display(min(valid)) if valid else None
    date_to = _yymmdd_to_display(max(valid)) if valid else None
    events = {str(d.get("event_id")) for d in deck_dicts if d.get("event_id") is not None}
    return {
        "deck_count": len(deck_dicts),
        "event_count": len(events),
        "date_from": date_from,
        "date_to": date_to,
    }


def _deck_sort_key(d: dict) -> tuple:
    """Sort by date descending, then rank ascending (1, 2, ..., 12, ...)."""
    date_key = _parse_date_sortkey(d.get("date", ""))
    rank_val = _rank_sort_value(d.get("rank", ""))
    return (-int(date_key) if date_key.isdigit() else 0, rank_val)


def _date_in_range(date_str: str, date_from: str | None, date_to: str | None) -> bool:
    """Check if DD/MM/YY date_str is within [date_from, date_to] (inclusive)."""
    key = _parse_date_sortkey(date_str)
    if not key.isdigit():
        return True
    key_int = int(key)
    if date_from:
        from_key = _parse_date_sortkey(date_from)
        if from_key.isdigit() and key_int < int(from_key):
            return False
    if date_to:
        to_key = _parse_date_sortkey(date_to)
        if to_key.isdigit() and key_int > int(to_key):
            return False
    return True


def _filter_decks_by_date(decks: list[dict], date_from: str | None, date_to: str | None) -> list[dict]:
    """Filter decks by date range."""
    if not date_from and not date_to:
        return decks
    return [d for d in decks if _date_in_range(d.get("date", ""), date_from, date_to)]


def _parse_event_id_filter(event_id: str | None, event_ids: str | None) -> set[str] | None:
    """Return a set of event IDs to filter by, or None for no event filter."""
    if event_ids:
        ids = {x.strip() for x in event_ids.split(",") if x.strip()}
        return ids or None
    if event_id is not None:
        return {str(event_id)}
    return None


def _filter_decks_for_query(
    decks: list[dict],
    event_id: str | None,
    event_ids: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[dict]:
    """Filter decks by event_id/event_ids and (optionally) date range.

    Behavior matches legacy endpoints:
    - If event_ids or event_id is provided, filter by those event IDs and ignore date_from/date_to.
    - Otherwise, apply date range filtering only.
    """
    id_set = _parse_event_id_filter(event_id, event_ids)
    if id_set is not None:
        return [d for d in decks if str(d.get("event_id")) in id_set]
    return _filter_decks_by_date(decks, date_from, date_to)
