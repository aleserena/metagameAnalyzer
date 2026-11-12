"""Event snapshots: an event as it was before a destructive action, restorable from Settings.

A snapshot is the event export (``build_event_export``, with player emails) plus the few things the
export does not carry (deck origins, hand-edited field lists), stored as JSON in ``event_snapshots``.
It is taken in the caller's session, so it commits or rolls back together with the action it guards.
Payloads contain player emails: never return them to anyone but an admin.
"""

import hashlib
import json
from datetime import timedelta

from api import db as _db
from api.db import DeckRow, EventSnapshotRow
from api.services.event_export import build_event_export
from sqlalchemy import func

SNAPSHOT_KEEP_PER_EVENT = 10
SNAPSHOT_MAX_AGE_DAYS = 90

# Why a snapshot was taken (``event_snapshots.reason``).
REASON_DELETE = "delete"
REASON_MERGE = "merge"
REASON_HADOUKEN = "hadouken"
REASON_CLEAR_DECKS = "clear_decks"
REASON_RESCRAPE = "rescrape"
REASON_BEFORE_RESTORE = "before_restore"


def _payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_payload(session, event_id: str) -> dict | None:
    """The JSON stored for ``event_id`` (None when the event does not exist)."""
    export = build_event_export(session, event_id, include_emails=True)
    if export is None:
        return None
    payload = export.model_dump(mode="json")
    eid = _db._event_id_str(event_id)
    deck_rows = session.query(DeckRow.deck_id, DeckRow.origin, DeckRow.manual_fields).filter(DeckRow.event_id == eid)
    deck_origins: dict[str, str] = {}
    deck_manual: dict[str, list] = {}
    for deck_id, origin, manual in deck_rows:
        deck_origins[str(deck_id)] = origin or _db.ORIGIN_MTGTOP8
        if manual:
            deck_manual[str(deck_id)] = list(manual)
    event_row = _db.get_event(session, eid)
    payload["extras"] = {
        "deck_origins": deck_origins,
        "deck_manual_fields": deck_manual,
        "event_manual_fields": list(event_row.manual_fields) if event_row and event_row.manual_fields else [],
    }
    return payload


def take_snapshot(session, event_id: str, reason: str) -> int | None:
    """Store the event as it is now. Returns the snapshot id, or None when the event does not exist.

    If the event is unchanged since its newest snapshot, that snapshot's id is returned and nothing
    is written (repeated re-scrapes must not fill the table or push out older snapshots).
    """
    session.flush()  # the export reads through queries: pending changes must be visible
    payload = build_payload(session, event_id)
    if payload is None:
        return None
    eid = _db._event_id_str(event_id)
    digest = _payload_hash(payload)
    newest = (
        session.query(EventSnapshotRow.id, EventSnapshotRow.payload_hash)
        .filter(EventSnapshotRow.event_id == eid)
        .order_by(EventSnapshotRow.id.desc())
        .first()
    )
    if newest is not None and newest.payload_hash == digest:
        return newest.id
    row = EventSnapshotRow(
        event_id=eid,
        event_name=(payload.get("event") or {}).get("event_name") or "",
        created_at=_db.utcnow_naive(),
        reason=reason,
        payload_hash=digest,
        payload=payload,
    )
    session.add(row)
    session.flush()
    prune_snapshots(session, eid)
    return row.id


def prune_snapshots(session, event_id: str) -> int:
    """Keep the newest SNAPSHOT_KEEP_PER_EVENT snapshots of this event, none older than
    SNAPSHOT_MAX_AGE_DAYS. Returns how many were deleted."""
    eid = _db._event_id_str(event_id)
    rows = (
        session.query(EventSnapshotRow.id, EventSnapshotRow.created_at)
        .filter(EventSnapshotRow.event_id == eid)
        .order_by(EventSnapshotRow.id.desc())
        .all()
    )
    cutoff = _db.utcnow_naive() - timedelta(days=SNAPSHOT_MAX_AGE_DAYS)
    doomed = [r.id for i, r in enumerate(rows) if i >= SNAPSHOT_KEEP_PER_EVENT or r.created_at < cutoff]
    if doomed:
        session.query(EventSnapshotRow).filter(EventSnapshotRow.id.in_(doomed)).delete(synchronize_session=False)
    return len(doomed)


def list_snapshots(session, *, event_id: str | None = None, limit: int = 200) -> list[dict]:
    """Newest first. Never includes the payload (it holds player emails)."""
    query = session.query(
        EventSnapshotRow.id,
        EventSnapshotRow.event_id,
        EventSnapshotRow.event_name,
        EventSnapshotRow.created_at,
        EventSnapshotRow.reason,
        func.jsonb_array_length(func.coalesce(EventSnapshotRow.payload["decks"], func.cast("[]", _db.JSONB))),
        func.jsonb_array_length(func.coalesce(EventSnapshotRow.payload["matchups"], func.cast("[]", _db.JSONB))),
    )
    if event_id:
        query = query.filter(EventSnapshotRow.event_id == _db._event_id_str(event_id))
    rows = query.order_by(EventSnapshotRow.id.desc()).limit(limit).all()
    return [
        {
            "id": sid,
            "event_id": eid,
            "event_name": name or "",
            "created_at": _db.iso_utc(created_at),
            "reason": reason,
            "deck_count": deck_count or 0,
            "matchup_count": matchup_count or 0,
        }
        for sid, eid, name, created_at, reason, deck_count, matchup_count in rows
    ]
