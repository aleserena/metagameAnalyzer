"""Event snapshots: an event as it was before a destructive action, restorable from Settings.

A snapshot is the event export (``build_event_export``, with player emails) plus the few things the
export does not carry (deck origins, hand-edited field lists), stored as JSON in ``event_snapshots``.
It is taken in the caller's session, so it commits or rolls back together with the action it guards.
Payloads contain player emails: never return them to anyone but an admin.
"""

import hashlib
import json
from collections.abc import Iterable
from datetime import timedelta

from api import db as _db
from api.db import DeckRow, EventRow, EventSnapshotRow, MatchupRow, PlayerEmailRow, PlayerRow
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
    # A fixed order, so an unchanged event always hashes the same whatever order the rows come back in.
    payload["decks"] = sorted(payload.get("decks") or [], key=lambda d: d.get("deck_id") or 0)
    payload["matchups"] = sorted(
        payload.get("matchups") or [],
        key=lambda m: (m.get("deck_id") or 0, m.get("round") if m.get("round") is not None else -1, m.get("id") or 0),
    )
    payload["players"] = sorted(payload.get("players") or [], key=lambda pl: pl.get("id") or 0)
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


def take_snapshot(session, event_id: str, reason: str, *, protect: Iterable[int] = ()) -> int | None:
    """Store the event as it is now. Returns the snapshot id, or None when the event does not exist.

    If the event is unchanged since its newest snapshot, that snapshot's id is returned and nothing
    is written (repeated re-scrapes must not fill the table or push out older snapshots).
    ``protect``: snapshot ids the retention rule must not delete while making room for this one.
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
    prune_snapshots(session, eid, protect=protect)
    return row.id


def prune_snapshots(session, event_id: str, *, protect: Iterable[int] = ()) -> int:
    """Keep the newest SNAPSHOT_KEEP_PER_EVENT snapshots of this event, none older than
    SNAPSHOT_MAX_AGE_DAYS; ids in ``protect`` are never deleted. Returns how many were deleted."""
    protected = set(protect)
    eid = _db._event_id_str(event_id)
    rows = (
        session.query(EventSnapshotRow.id, EventSnapshotRow.created_at)
        .filter(EventSnapshotRow.event_id == eid)
        .order_by(EventSnapshotRow.id.desc())
        .all()
    )
    cutoff = _db.utcnow_naive() - timedelta(days=SNAPSHOT_MAX_AGE_DAYS)
    doomed = [
        r.id
        for i, r in enumerate(rows)
        if (i >= SNAPSHOT_KEEP_PER_EVENT or r.created_at < cutoff) and r.id not in protected
    ]
    if doomed:
        session.query(EventSnapshotRow).filter(EventSnapshotRow.id.in_(doomed)).delete(synchronize_session=False)
    return len(doomed)


def list_snapshots(
    session, *, event_id: str | None = None, search: str | None = None, limit: int = 200
) -> list[dict]:
    """Newest first. Never includes the payload (it holds player emails).

    ``search`` narrows to snapshots whose event id equals it or whose event name contains it.
    """
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
    term = (search or "").strip()
    if term:
        # Literal match: % and _ in the search text must not act as wildcards.
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(
            (EventSnapshotRow.event_id == term) | EventSnapshotRow.event_name.ilike(f"%{escaped}%", escape="\\")
        )
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


def _restore_player(session, deck: dict, used_player_ids: set[int]) -> tuple[int, str]:
    """The player a restored deck belongs to: (player_id, display name).

    The snapshot's player id wins when that player still exists (a player renamed since keeps the
    deck, under the current name). Otherwise the player is found by name or created. One player
    cannot hold two decks in an event, so a second deck landing on the same player (the two were
    merged since) gets a clearly named placeholder instead of failing the restore.
    """
    name = (deck.get("player") or "").strip() or "(unknown)"
    pid = deck.get("player_id")
    row = session.get(PlayerRow, pid) if pid is not None else None
    if row is not None:
        pid, display = row.id, row.display_name or name
    else:
        pid, display = _db.resolve_name_to_player_id(session, name)
        if pid is None:
            pid, display = _db.get_or_create_player(session, name)
    if pid in used_player_ids:
        pid, display = _db.get_or_create_player(session, f"{name} (restored deck {deck['deck_id']})")
    used_player_ids.add(pid)
    return pid, display


def restore_snapshot(session, snapshot_id: int) -> dict:
    """Put an event back exactly as a snapshot recorded it: same event id, same deck ids, origins,
    matchups, hand-edited field lists and player emails.

    The event's current state is snapshotted first (``before_restore``), so a restore can be undone.
    Decks added to the event since are removed; snapshot decks that now sit in another event (after
    a merge) are moved back. Raises LookupError for an unknown snapshot. The caller reloads the
    in-memory decks after commit.
    """
    snapshot = session.get(EventSnapshotRow, snapshot_id)
    if snapshot is None:
        raise LookupError("Snapshot not found")
    payload = snapshot.payload or {}
    event = payload.get("event") or {}
    extras = payload.get("extras") or {}
    event_id = snapshot.event_id
    decks = [d for d in (payload.get("decks") or []) if d.get("deck_id") is not None]
    deck_ids = [int(d["deck_id"]) for d in decks]

    # Save what is about to be replaced: this event, and any other event that currently holds one of
    # the snapshot's decks (after a merge they live in the kept event, with later edits on them).
    # The snapshot being restored must survive the retention rule while we do so.
    safety_id = take_snapshot(session, event_id, REASON_BEFORE_RESTORE, protect={snapshot_id})
    other_event_ids: list[str] = []
    if deck_ids:
        other_event_ids = sorted(
            eid
            for (eid,) in session.query(DeckRow.event_id)
            .filter(DeckRow.deck_id.in_(deck_ids), DeckRow.event_id != event_id)
            .distinct()
        )
        for other_event_id in other_event_ids:
            take_snapshot(session, other_event_id, REASON_BEFORE_RESTORE)

    # Clear the way: the event's current decks, and the snapshot's decks wherever they are now.
    # Matchups go with their deck (ON DELETE CASCADE).
    session.query(DeckRow).filter(DeckRow.event_id == event_id).delete(synchronize_session=False)
    if deck_ids:
        session.query(DeckRow).filter(DeckRow.deck_id.in_(deck_ids)).delete(synchronize_session=False)
    session.flush()
    session.expire_all()

    row = _db.get_event(session, event_id)
    if row is None:
        row = EventRow(event_id=event_id)
        session.add(row)
    row.origin = event.get("origin") or _db.ORIGIN_MTGTOP8
    row.name = event.get("event_name") or ""
    row.store = event.get("store") or ""
    row.location = event.get("location") or ""
    row.date = event.get("date") or ""
    row.format_id = event.get("format_id") or ""
    row.player_count = int(event.get("player_count") or 0)
    # Snapshots taken before migration 020 have neither key: the event goes back to Swiss.
    row.structure = event.get("structure") or None
    row.bracket_size = event.get("bracket_size")
    row.manual_fields = list(extras.get("event_manual_fields") or []) or None
    session.flush()

    deck_origins = extras.get("deck_origins") or {}
    deck_manual = extras.get("deck_manual_fields") or {}
    used_player_ids: set[int] = set()
    deck_player: dict[int, tuple[int, str]] = {}
    for deck in decks:
        data = dict(deck)
        data["deck_id"] = int(deck["deck_id"])
        data["event_id"] = event_id
        data["player_id"], data["player"] = _restore_player(session, data, used_player_ids)
        deck_row = _db.dict_to_deck_row(data, origin=deck_origins.get(str(data["deck_id"])) or row.origin)
        deck_row.manual_fields = list(deck_manual.get(str(data["deck_id"])) or []) or None
        session.add(deck_row)
        deck_player[data["deck_id"]] = (data["player_id"], data["player"])
    session.flush()

    # Matchup rows exactly as stored: both sides are in the snapshot, so no inverse rows are generated.
    matchup_count = 0
    restored_ids = set(deck_player)
    for m in payload.get("matchups") or []:
        try:
            deck_id = int(m.get("deck_id"))
        except (TypeError, ValueError):
            continue
        if deck_id not in restored_ids:
            continue
        opp_deck_id = m.get("opponent_deck_id")
        opp_pid = m.get("opponent_player_id")
        opp_name = (m.get("opponent_player") or "").strip()
        if opp_deck_id is not None:
            if opp_deck_id in restored_ids:
                opp_pid, opp_name = deck_player[opp_deck_id]
            else:
                outside = session.get(DeckRow, opp_deck_id)
                if outside is None:
                    continue  # the opposing deck is gone for good
                # A deck in another event: trust its current player, not the id stored back then
                # (that player may have been merged away since).
                opp_pid, opp_name = outside.player_id, outside.player or opp_name
        elif opp_pid is not None and session.get(PlayerRow, opp_pid) is None:
            opp_pid = None
            if opp_name and opp_name not in ("Bye", "(drop)"):
                opp_pid, resolved = _db.resolve_name_to_player_id(session, opp_name)
                if opp_pid is None:
                    opp_pid, resolved = _db.get_or_create_player(session, opp_name)
                opp_name = resolved or opp_name
        session.add(
            MatchupRow(
                deck_id=deck_id,
                opponent_player_id=opp_pid,
                opponent_player=opp_name or "Bye",
                opponent_deck_id=opp_deck_id,
                opponent_archetype=m.get("opponent_archetype"),
                result=(m.get("result") or "loss").strip() or "loss",
                result_note=(m.get("result_note") or None),
                round=m.get("round"),
            )
        )
        matchup_count += 1

    # Emails are keyed by the name the player had in the snapshot. Give each to the player its deck
    # was restored to: looking the old name up again would recreate a player that was renamed since.
    snapshot_name_to_pid = {
        (d.get("player") or "").strip(): deck_player[int(d["deck_id"])][0] for d in decks
    }
    for name, email in (payload.get("player_emails") or {}).items():
        pid = snapshot_name_to_pid.get((name or "").strip())
        if pid is None or not (email or "").strip():
            continue
        email_row = session.get(PlayerEmailRow, pid)
        if email_row is None:
            session.add(PlayerEmailRow(player_id=pid, email=email.strip()))
        else:
            email_row.email = email.strip()
    session.flush()
    return {
        "event_id": event_id,
        "deck_count": len(decks),
        "matchup_count": matchup_count,
        "safety_snapshot_id": safety_id,
        "also_saved_event_ids": other_event_ids,
    }
