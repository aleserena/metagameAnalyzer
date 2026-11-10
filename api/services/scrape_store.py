"""Persist scraped decks without ever deleting rows (match results hang off deck ids)."""

from api import db as _db
from api.state import _resolve_deck_player
from sqlalchemy.exc import IntegrityError
from src.mtgtop8.scraper import parse_event_display


def _ensure_event(session, sample: dict, *, refresh: bool) -> None:
    eid = sample["event_id"]
    raw_name = sample.get("event_name", "")
    name, store, location = parse_event_display(raw_name)
    existing = _db.get_event(session, eid)
    if existing is None:
        _db.create_event(
            session,
            event_name=name or raw_name or "Unnamed",
            date=sample.get("date", ""),
            format_id=sample.get("format_id", ""),
            origin=_db.ORIGIN_MTGTOP8,
            event_id=eid,
            player_count=int(sample.get("player_count", 0) or 0),
            store=store,
            location=location,
        )
    elif refresh:
        _db.update_event(
            session,
            eid,
            event_name=name or raw_name or existing.name,
            date=sample.get("date", existing.date),
            format_id=sample.get("format_id", existing.format_id),
            # Keep the larger count: it may have been completed from another source (e.g. Hadouken)
            player_count=max(int(sample.get("player_count", 0) or 0), existing.player_count or 0),
            store=store or existing.store,
            location=location or existing.location,
        )


def persist_scraped_decks(session, deck_dicts: list[dict], *, refresh_events: bool) -> dict:
    """Upsert scraped decks by deck_id. Never deletes. A deck that violates a constraint
    is recorded in ``failed`` and skipped; the others are still saved."""
    seen_events: set[str] = set()
    for d in deck_dicts:
        ev_id = d.get("event_id")
        if ev_id is None or str(ev_id) in seen_events:
            continue
        seen_events.add(str(ev_id))
        _ensure_event(session, d, refresh=refresh_events)

    saved = 0
    failed: list[dict] = []
    for d in deck_dicts:
        try:
            with session.begin_nested():
                _resolve_deck_player(session, d)
                _db.upsert_deck(session, d, origin=_db.ORIGIN_MTGTOP8)
                session.flush()
            saved += 1
        except IntegrityError as e:
            failed.append(
                {"deck_id": d.get("deck_id"), "event_id": str(d.get("event_id")), "error": str(e.orig or e)}
            )
    return {"decks_saved": saved, "events": len(seen_events), "failed": failed}
