import json
import logging
import secrets
import uuid
from datetime import timedelta

import requests
from fastapi import Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from src.mtgtop8.hadouken import HadoukenEvent, fetch_hadouken_event
from src.mtgtop8.normalize import (
    canonical_card_name_for_compare as _canonical_card_key,
)
from src.mtgtop8.scraper import event_display_name

from api.brackets import is_single_elimination, validate_structure
from api.dependencies import (
    current_actor,
    require_admin,
    require_admin_or_event_edit,
    require_database,
)
from api.formats import is_commander_format
from api.helpers import (
    _normalize_split_cards,
    _read_upload_json_bytes_async,
)
from api.schemas.events import (
    DECK_MERGE_FIELDS,
    EVENT_MERGE_FIELDS,
    CreateEventBody,
    DeckPairPreview,
    EventExportData,
    EventResponse,
    HadoukenApplyBody,
    HadoukenPreviewBody,
    MergeConflictItem,
    MergeEventsBody,
    MergePreviewResponse,
    UploadDecksBody,
)
from api.schemas.settings import (
    SendFeedbackLinkToPlayerBody,
)
from api.schemas.upload import CreateUploadLinksBody
from api.services import change_log
from api.services import hadouken as _hadouken
from api.services.event_export import build_event_export
from api.services.event_import import import_event_payload
from api.services.snapshots import REASON_DELETE, REASON_MERGE, take_snapshot
from api.state import (
    _events_from_decks,
    _get_event_by_id_from_decks,
    _invalidate_events_cache,
    _load_decks_from_db,
    _normalize_player,
    _resolve_deck_player,
    state,
)

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

from api.route_helpers import (
    _upload_link_base_url,
    find_matchup_discrepancies,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _compute_events_list() -> list[dict]:
    """Build the events list (from DB or from state.decks). Used by list_events with caching."""
    if state.database_available():
        try:
            with _db.session_scope() as session:
                rows = _db.get_all_events(session)
            # Rows are already in canonical event dict shape via db.event_row_to_dict
            return rows
        except Exception as e:
            logger.exception("Failed to list events from DB: %s", e)
    return _events_from_decks(state.decks)


@router.get("/api/v1/events", response_model=dict)
def list_events():
    """List unique events from current data (from DB events table when DB used, else from decks). Cached until events/decks change."""
    if state.events_cache is not None:
        return {"events": [EventResponse(**e) for e in state.events_cache]}
    state.events_cache = _compute_events_list()
    return {"events": [EventResponse(**e) for e in state.events_cache]}


@router.post("/api/v1/events", dependencies=[Depends(require_admin), Depends(require_database)], response_model=EventResponse)
def create_event(body: CreateEventBody):
    """Create a new event (admin-only). Manual events get IDs in a separate namespace from MTGTop8."""
    if not body.player_count or body.player_count < 1:
        raise HTTPException(status_code=400, detail="Number of players is required and must be at least 1")
    try:
        structure, bracket_size = validate_structure(body.structure, body.bracket_size)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        with _db.session_scope() as session:
            row = _db.create_event(
                session,
                event_name=body.event_name.strip() or "Unnamed",
                date=body.date.strip() or "",
                format_id=body.format_id.strip() or "EDH",
                origin=_db.ORIGIN_MANUAL,
                event_id=body.event_id,
                player_count=body.player_count,
                store=(body.store or "").strip(),
                location=(body.location or "").strip(),
                structure=structure,
                bracket_size=bracket_size,
            )
            _invalidate_events_cache()
            created = EventResponse(**_db.event_row_to_dict(row))
        change_log.log(change_log.ADMIN, "event.create", f"Created event {created.event_name!r}", event_id=created.event_id)
        return created
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Create event failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create event")


@router.get("/api/v1/events/event-ids-with-discrepancies", dependencies=[Depends(require_admin), Depends(require_database)])
def get_event_ids_with_discrepancies():
    """Return event_ids that have at least one matchup discrepancy (admin)."""
    with _db.session_scope() as session:
        rows = _db.list_all_matchups_with_event_id(session)
    by_event: dict[str, list[dict]] = {}
    for r in rows:
        eid = (r.get("event_id") or "").strip()
        if not eid:
            continue
        by_event.setdefault(eid, []).append(r)
    event_ids_with_discrepancies: list[str] = [
        eid for eid, event_rows in by_event.items() if find_matchup_discrepancies(event_rows)
    ]
    return {"event_ids": event_ids_with_discrepancies}


@router.get("/api/v1/events/event-ids-with-missing-decks", dependencies=[Depends(require_admin), Depends(require_database)])
def get_event_ids_with_missing_decks():
    """Return event_ids where deck count < player_count (admin)."""
    with _db.session_scope() as session:
        event_ids = _db.list_event_ids_with_missing_decks(session)
    return {"event_ids": event_ids}


@router.get("/api/v1/events/event-ids-with-missing-matchups", dependencies=[Depends(require_admin), Depends(require_database)])
def get_event_ids_with_missing_matchups():
    """Return event_ids where every deck has the expected matchups (admin). Events NOT in this list have missing matchups."""
    with _db.session_scope() as session:
        event_ids = _db.list_event_ids_with_complete_matchups(session)
    return {"event_ids": event_ids}


def _event_row_to_merge_dict(row) -> dict:
    """Event row to dict keyed by EVENT_MERGE_FIELDS (name -> event_name)."""
    return {
        "event_name": row.name or "",
        "store": row.store or "",
        "location": row.location or "",
        "date": row.date or "",
        "format_id": row.format_id or "",
        "player_count": row.player_count or 0,
    }


def _merge_structure(keep_row, remove_row) -> tuple[str, int | None]:
    """Structure of the merged event: a single-elimination side wins (keep first), else Swiss."""
    for row in (keep_row, remove_row):
        if is_single_elimination(row.structure) and row.bracket_size:
            return row.structure, row.bracket_size
    return validate_structure(None, None)


def _normalize_board_for_compare(board: list) -> list[tuple[str, int]]:
    """Normalize mainboard/sideboard to comparable (canonical_card, total_qty) list.
    Double-faced cards are keyed by front face so 'Norman Osborn' and 'Norman Osborn // Green Goblin' match."""
    if not board or not isinstance(board, list):
        return []
    by_canonical: dict[str, int] = {}
    for entry in board:
        if isinstance(entry, dict):
            card = (entry.get("card") or "").strip()
            qty = int(entry.get("qty", 1)) if entry.get("qty") is not None else 1
            if card:
                key = _canonical_card_key(card)
                by_canonical[key] = by_canonical.get(key, 0) + qty
    out = sorted(by_canonical.items(), key=lambda x: (x[0].lower(), x[1]))
    return out


def _boards_content_equal(board_a: list, board_b: list) -> bool:
    """True if both boards have the same cards and quantities (order ignored)."""
    return _normalize_board_for_compare(board_a) == _normalize_board_for_compare(board_b)


def _format_commanders_archetype(deck: dict) -> str:
    """Display archetype only for EDH merge conflict (commanders not shown)."""
    arch = (deck.get("archetype") or "").strip()
    if arch:
        return arch
    cmd = deck.get("commanders") or []
    if cmd:
        return ", ".join(cmd)  # fallback if no archetype
    return "—"


def _deck_merge_conflicts(deck_keep: dict, deck_remove: dict) -> list[MergeConflictItem]:
    """Compare two deck dicts on DECK_MERGE_FIELDS. Only add conflict when both have data and values differ (prefer non-empty).
    For EDH, commanders and archetype are a single combined field."""
    conflicts = []
    is_edh_keep = is_commander_format(deck_keep.get("format_id"))
    is_edh_remove = is_commander_format(deck_remove.get("format_id"))
    is_edh_both = is_edh_keep and is_edh_remove

    for field in DECK_MERGE_FIELDS:
        if is_edh_both and field in ("commanders", "archetype"):
            continue  # handled below as commanders_archetype
        v_keep = deck_keep.get(field)
        v_remove = deck_remove.get(field)
        if field == "player_count":
            v_keep = 0 if v_keep is None else int(v_keep)
            v_remove = 0 if v_remove is None else int(v_remove)
        has_keep = (v_keep not in (None, "", [])) if field != "player_count" else (v_keep is not None and v_keep != 0)
        has_remove = (v_remove not in (None, "", [])) if field != "player_count" else (v_remove is not None and v_remove != 0)
        if not has_keep or not has_remove:
            continue  # prefer the one with data; no conflict to show
        if field in ("commanders", "mainboard", "sideboard"):
            if field == "commanders":
                if v_keep != v_remove:
                    conflicts.append(MergeConflictItem(field=field, value_keep=v_keep, value_remove=v_remove))
            else:
                # mainboard/sideboard: compare content (same cards and qty = no conflict)
                if not _boards_content_equal(v_keep if isinstance(v_keep, list) else [], v_remove if isinstance(v_remove, list) else []):
                    conflicts.append(MergeConflictItem(field=field, value_keep=v_keep, value_remove=v_remove))
        else:
            s_keep = (v_keep or "").strip() if isinstance(v_keep, str) else (v_keep if v_keep is not None else "")
            s_remove = (v_remove or "").strip() if isinstance(v_remove, str) else (v_remove if v_remove is not None else "")
            if s_keep != s_remove:
                conflicts.append(MergeConflictItem(field=field, value_keep=v_keep, value_remove=v_remove))

    # EDH: single combined commanders_archetype conflict when either commanders or archetype differs
    # Archetype is a commander card; treat double-faced same as front face (e.g. Norman Osborn === Norman Osborn // Green Goblin)
    if is_edh_both:
        cmd_keep = deck_keep.get("commanders") or []
        arch_keep = (deck_keep.get("archetype") or "").strip()
        cmd_remove = deck_remove.get("commanders") or []
        arch_remove = (deck_remove.get("archetype") or "").strip()
        has_keep = bool(cmd_keep or arch_keep)
        has_remove = bool(cmd_remove or arch_remove)
        if has_keep and has_remove:
            # Compare as sets of canonical card names (front face, case-insensitive); include archetype as a commander
            set_keep = {_canonical_card_key(c) for c in cmd_keep if (c or "").strip()}
            if arch_keep:
                set_keep.add(_canonical_card_key(arch_keep))
            set_remove = {_canonical_card_key(c) for c in cmd_remove if (c or "").strip()}
            if arch_remove:
                set_remove.add(_canonical_card_key(arch_remove))
            if set_keep != set_remove:
                conflicts.append(
                    MergeConflictItem(
                        field="commanders_archetype",
                        value_keep=_format_commanders_archetype(deck_keep),
                        value_remove=_format_commanders_archetype(deck_remove),
                    )
                )
    return conflicts


@router.get(
    "/api/v1/events/merge-preview",
    dependencies=[Depends(require_admin), Depends(require_database)],
    response_model=MergePreviewResponse,
)
def merge_preview(
    event_id_a: str = Query(..., alias="event_id_a"),
    event_id_b: str = Query(..., alias="event_id_b"),
    manual_pairs: str | None = Query(None, alias="manual_pairs", description="Comma-separated keep_id-remove_id for manual deck pairs to include conflict preview"),
):
    """Preview merging two events. Cannot merge two MTGTop8 events. Prefer MTGTop8 data when merging manual + MTGTop8.
    Optional manual_pairs=deck_id_keep-deck_id_remove,... includes those pairs in deck_pairs with same validations as auto-paired."""
    with _db.session_scope() as session:
        row_a = _db.get_event(session, event_id_a)
        row_b = _db.get_event(session, event_id_b)
    if not row_a:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id_a}")
    if not row_b:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id_b}")
    if row_a.event_id == row_b.event_id:
        raise HTTPException(status_code=400, detail="Cannot merge an event with itself")

    origin_a = row_a.origin or _db.ORIGIN_MTGTOP8
    origin_b = row_b.origin or _db.ORIGIN_MTGTOP8
    if origin_a == _db.ORIGIN_MTGTOP8 and origin_b == _db.ORIGIN_MTGTOP8:
        return MergePreviewResponse(
            can_merge=False,
            error="Cannot merge two events imported from MTGTop8.",
            event_a=_db.event_row_to_dict(row_a),
            event_b=_db.event_row_to_dict(row_b),
            conflicts=[],
            merged_preview={},
            keep_event_id="",
            remove_event_id="",
        )

    # Determine which event to keep: prefer MTGTop8; if both manual, keep A remove B
    if origin_a == _db.ORIGIN_MTGTOP8 and origin_b == _db.ORIGIN_MANUAL:
        keep, remove = row_a, row_b
    elif origin_a == _db.ORIGIN_MANUAL and origin_b == _db.ORIGIN_MTGTOP8:
        keep, remove = row_b, row_a
    else:
        keep, remove = row_a, row_b

    d_keep = _event_row_to_merge_dict(keep)
    d_remove = _event_row_to_merge_dict(remove)
    merged = {}
    conflicts = []
    for field in EVENT_MERGE_FIELDS:
        v_keep = d_keep.get(field)
        v_remove = d_remove.get(field)
        # Normalize empty
        if field == "player_count":
            v_keep = 0 if v_keep is None else int(v_keep)
            v_remove = 0 if v_remove is None else int(v_remove)
        else:
            v_keep = (v_keep or "").strip() if isinstance(v_keep, str) else (v_keep or "")
            v_remove = (v_remove or "").strip() if isinstance(v_remove, str) else (v_remove or "")
        has_keep = (v_keep != "" and v_keep is not None) if field != "player_count" else (v_keep is not None and v_keep != 0)
        has_remove = (v_remove != "" and v_remove is not None) if field != "player_count" else (v_remove is not None and v_remove != 0)
        if not has_keep and has_remove:
            merged[field] = v_remove
        elif has_keep and not has_remove:
            merged[field] = v_keep
        elif has_keep and has_remove:
            if v_keep == v_remove:
                merged[field] = v_keep
            else:
                merged[field] = v_keep  # default: prefer keep (MTGTop8 when mixed)
                conflicts.append(MergeConflictItem(field=field, value_keep=v_keep, value_remove=v_remove))
        else:
            merged[field] = v_keep if field != "player_count" else 0

    # Full merged_preview for API (include event_id of kept event)
    merged_preview = {
        "event_id": keep.event_id,
        "event_name": merged["event_name"],
        "store": merged["store"],
        "location": merged["location"],
        "date": merged["date"],
        "format_id": merged["format_id"],
        "player_count": merged["player_count"],
    }
    merged_preview["structure"], merged_preview["bracket_size"] = _merge_structure(keep, remove)

    # Player/deck pairing: same player_id in both events -> merge decks
    deck_pairs: list[DeckPairPreview] = []
    decks_keep_only: list[dict] = []
    decks_remove_only: list[dict] = []
    with _db.session_scope() as session:
        decks_keep = _db.get_decks_by_event(session, keep.event_id)
        decks_remove = _db.get_decks_by_event(session, remove.event_id)
        keep_by_player_id: dict[int, dict] = {}
        for d in decks_keep:
            pid = d.get("player_id")
            if pid is not None:
                keep_by_player_id[pid] = d
        paired_keep_ids: set[int] = set()
        paired_remove_ids: set[int] = set()
        for d in decks_remove:
            pid = d.get("player_id")
            if pid is not None and pid in keep_by_player_id:
                k = keep_by_player_id[pid]
                paired_keep_ids.add(k["deck_id"])
                paired_remove_ids.add(d["deck_id"])
                pair_conflicts = _deck_merge_conflicts(k, d)
                # Add matchups conflict only when both have matchup data and counts differ (effective = as deck + as opponent)
                n_keep = _db.count_effective_matchups_for_deck(session, k["deck_id"])
                n_remove = _db.count_effective_matchups_for_deck(session, d["deck_id"])
                if n_keep > 0 and n_remove > 0 and n_keep != n_remove:
                    pair_conflicts.append(
                        MergeConflictItem(
                            field="matchups",
                            value_keep=f"{n_keep} matchups",
                            value_remove=f"{n_remove} matchups",
                        )
                    )
                deck_pairs.append(DeckPairPreview(deck_keep=k, deck_remove=d, conflicts=pair_conflicts))
        # Manual pairs: same validations (deck, rank, matchups, etc.) as auto-paired
        if manual_pairs and manual_pairs.strip():
            keep_by_id = {d["deck_id"]: d for d in decks_keep}
            remove_by_id = {d["deck_id"]: d for d in decks_remove}
            for part in manual_pairs.strip().split(","):
                part = part.strip()
                if "-" not in part:
                    continue
                a, b = part.split("-", 1)
                try:
                    keep_id = int(a.strip())
                    remove_id = int(b.strip())
                except ValueError:
                    continue
                k = keep_by_id.get(keep_id)
                d = remove_by_id.get(remove_id)
                if not k or not d:
                    continue
                pair_conflicts = _deck_merge_conflicts(k, d)
                n_keep = _db.count_effective_matchups_for_deck(session, k["deck_id"])
                n_remove = _db.count_effective_matchups_for_deck(session, d["deck_id"])
                if n_keep > 0 and n_remove > 0 and n_keep != n_remove:
                    pair_conflicts.append(
                        MergeConflictItem(
                            field="matchups",
                            value_keep=f"{n_keep} matchups",
                            value_remove=f"{n_remove} matchups",
                        )
                    )
                deck_pairs.append(DeckPairPreview(deck_keep=k, deck_remove=d, conflicts=pair_conflicts))
        decks_keep_only = [d for d in decks_keep if d["deck_id"] not in paired_keep_ids]
        decks_remove_only = [d for d in decks_remove if d["deck_id"] not in paired_remove_ids]

    return MergePreviewResponse(
        can_merge=True,
        event_a=_db.event_row_to_dict(row_a),
        event_b=_db.event_row_to_dict(row_b),
        conflicts=conflicts,
        merged_preview=merged_preview,
        keep_event_id=keep.event_id,
        remove_event_id=remove.event_id,
        deck_pairs=deck_pairs,
        decks_keep_only=decks_keep_only,
        decks_remove_only=decks_remove_only,
    )


@router.get("/api/v1/events/{event_id}", response_model=EventResponse)
def get_event_by_id(event_id: str):
    """Get a single event by ID. Returns 404 if not found."""
    if state.database_available():
        try:
            with _db.session_scope() as session:
                row = _db.get_event(session, event_id)
                if row:
                    return EventResponse(**_db.event_row_to_dict(row))
        except Exception as e:
            logger.exception("Failed to get event: %s", e)
    # Fallback: find from state.decks
    ev = _get_event_by_id_from_decks(event_id)
    if ev:
        return EventResponse(**ev)
    raise HTTPException(status_code=404, detail="Event not found")


@router.get("/api/v1/events/{event_id}/export")
def export_event(event_id: str, role: str = Depends(require_admin_or_event_edit)):
    """Export an event and all related data as JSON. Player emails are admin-only."""
    payload: EventExportData | None = None

    if state.database_available():
        try:
            with _db.session_scope() as session:
                payload = build_event_export(session, event_id, include_emails=(role == "admin"))
        except Exception as e:
            logger.exception("Failed to export event from database: %s", e)
            raise HTTPException(status_code=500, detail="Failed to export event")
        if payload is None:
            raise HTTPException(status_code=404, detail="Event not found")
    else:
        ev = _get_event_by_id_from_decks(event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        payload = EventExportData(
            schema_version=1,
            event=EventResponse(**ev),
            decks=[d for d in state.decks if str(d.get("event_id")) == str(event_id)],
            matchups=[],
            player_emails={},
            players=[],
        )

    filename = f"event-{payload.event.event_id}.json"
    return JSONResponse(
        content=payload.model_dump(),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/api/v1/events/{event_id}", dependencies=[Depends(require_admin_or_event_edit), Depends(require_database)])
def update_event_endpoint(
    event_id: str,
    actor: str = Depends(current_actor),
    event_name: str | None = Query(None),
    date: str | None = Query(None),
    format_id: str | None = Query(None),
    player_count: int | None = Query(None),
    store: str | None = Query(None),
    location: str | None = Query(None),
    structure: str | None = Query(None, description="'swiss' | 'single_elimination'"),
    bracket_size: int | None = Query(None, description="Bracket players (single elimination): 2, 4, 8 ... 128"),
):
    """Update event metadata (admin-only)."""
    try:
        with _db.session_scope() as session:
            new_structure = new_bracket_size = None
            if structure is not None or bracket_size is not None:
                current = _db.get_event(session, event_id)
                if current is None:
                    raise HTTPException(status_code=404, detail="Event not found")
                try:
                    new_structure, new_bracket_size = validate_structure(
                        structure if structure is not None else current.structure,
                        bracket_size if bracket_size is not None else current.bracket_size,
                    )
                except ValueError as e:
                    raise HTTPException(status_code=422, detail=str(e))
            # A hand edit: details whose value changes are remembered, so a forced re-scrape leaves them alone.
            ok = _db.update_event(
                session,
                event_id,
                event_name=event_name,
                date=date,
                format_id=format_id,
                player_count=player_count,
                store=store,
                location=location,
                structure=new_structure,
                bracket_size=new_bracket_size,
                manual_fields=_db.EVENT_MANUAL_FIELDS,
            )
        if not ok:
            raise HTTPException(status_code=404, detail="Event not found")
        _load_decks_from_db()
        _invalidate_events_cache()
        change_log.log(actor, "event.update", "Edited event details", event_id=event_id)
        return {"event_id": event_id, "message": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Update event failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update event")


@router.delete("/api/v1/events/{event_id}", dependencies=[Depends(require_admin), Depends(require_database)])
def delete_event_endpoint(event_id: str):
    """Delete an event and all its decks (admin-only)."""
    try:
        with _db.session_scope() as session:
            # Same transaction as the delete: no snapshot, no delete.
            take_snapshot(session, event_id, REASON_DELETE)
            ok = _db.delete_event(session, event_id, delete_decks=True)
        if not ok:
            raise HTTPException(status_code=404, detail="Event not found")
        _load_decks_from_db()
        _invalidate_events_cache()
        change_log.log(change_log.ADMIN, "event.delete", "Deleted event and its decks", event_id=event_id)
        return {"event_id": event_id, "message": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Delete event failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete event")


@router.post(
    "/api/v1/events/import",
    dependencies=[Depends(require_admin), Depends(require_database)],
)
def import_event(body: EventExportData):
    """Import a new manual event (and all decks/matchups/emails) from an exported JSON payload."""
    if body.schema_version != 1:
        raise HTTPException(status_code=400, detail=f"Unsupported schema_version: {body.schema_version}")
    if not state.database_available():
        raise HTTPException(status_code=503, detail="Database is required for importing events")

    try:
        with _db.session_scope() as session:
            try:
                result = import_event_payload(session, body)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        _load_decks_from_db()
        _invalidate_events_cache()
        change_log.log(
            change_log.ADMIN,
            "event.import",
            f"Imported event from file with {result['deck_count']} deck(s)",
            event_id=result["event_id"],
        )
        return {"event_id": result["event_id"], "message": "imported", "deck_count": result["deck_count"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Import event failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to import event")


def _resolve_merge_pairs(decks_keep: list[dict], decks_remove: list[dict], player_merges: list) -> list[tuple[int, int]]:
    """Pair decks for an event merge: same player first, then manual pairs.

    Raises ValueError naming the deck when a manual pair references a deck outside
    its event or reuses a deck already paired.
    """
    keep_by_player_id = {d["player_id"]: d for d in decks_keep if d.get("player_id") is not None}
    keep_ids = {d["deck_id"] for d in decks_keep}
    remove_ids = {d["deck_id"] for d in decks_remove}
    pairs: list[tuple[int, int]] = []
    used_keep: set[int] = set()
    used_remove: set[int] = set()
    for d in decks_remove:
        pid = d.get("player_id")
        if pid is not None and pid in keep_by_player_id:
            k = keep_by_player_id[pid]
            pairs.append((k["deck_id"], d["deck_id"]))
            used_keep.add(k["deck_id"])
            used_remove.add(d["deck_id"])
    auto_remove = set(used_remove)
    for pm in player_merges:
        if pm.deck_id_remove in auto_remove:
            continue
        if pm.deck_id_keep not in keep_ids:
            raise ValueError(f"Deck {pm.deck_id_keep} to keep is not in the kept event")
        if pm.deck_id_remove not in remove_ids:
            raise ValueError(f"Deck {pm.deck_id_remove} to remove is not in the removed event")
        if pm.deck_id_keep in used_keep:
            raise ValueError(f"Deck {pm.deck_id_keep} to keep is paired more than once")
        if pm.deck_id_remove in used_remove:
            raise ValueError(f"Deck {pm.deck_id_remove} to remove is paired more than once")
        pairs.append((pm.deck_id_keep, pm.deck_id_remove))
        used_keep.add(pm.deck_id_keep)
        used_remove.add(pm.deck_id_remove)
    return pairs


@router.post(
    "/api/v1/events/merge",
    dependencies=[Depends(require_admin), Depends(require_database)],
)
def merge_events(body: MergeEventsBody):
    """Merge two events: move all decks and links to the kept event, update kept event with resolved data, delete the removed event."""
    with _db.session_scope() as session:
        keep_row = _db.get_event(session, body.event_id_keep)
        remove_row = _db.get_event(session, body.event_id_remove)
    if not keep_row:
        raise HTTPException(status_code=404, detail=f"Event not found: {body.event_id_keep!r}")
    if not remove_row:
        raise HTTPException(status_code=404, detail=f"Event not found: {body.event_id_remove!r}")
    if keep_row.event_id == remove_row.event_id:
        raise HTTPException(status_code=400, detail="Cannot merge an event with itself")
    origin_keep = keep_row.origin or _db.ORIGIN_MTGTOP8
    origin_remove = remove_row.origin or _db.ORIGIN_MANUAL
    if origin_keep == _db.ORIGIN_MTGTOP8 and origin_remove == _db.ORIGIN_MTGTOP8:
        raise HTTPException(status_code=400, detail="Cannot merge two events imported from MTGTop8.")

    # Build merged same as preview (prefer keep, fill missing from remove), then apply resolutions
    d_keep = _event_row_to_merge_dict(keep_row)
    d_remove = _event_row_to_merge_dict(remove_row)
    merged = {}
    for field in EVENT_MERGE_FIELDS:
        v_keep = d_keep.get(field)
        v_remove = d_remove.get(field)
        if field == "player_count":
            v_keep = 0 if v_keep is None else int(v_keep)
            v_remove = 0 if v_remove is None else int(v_remove)
        has_keep = (v_keep not in (None, "")) if field != "player_count" else (v_keep is not None and v_keep != 0)
        has_remove = (v_remove not in (None, "")) if field != "player_count" else (v_remove is not None and v_remove != 0)
        if not has_keep and has_remove:
            merged[field] = v_remove
        elif has_keep and not has_remove:
            merged[field] = v_keep
        elif has_keep and has_remove:
            merged[field] = v_keep if body.resolutions.get(field) != "remove" else v_remove
        else:
            merged[field] = v_keep if field != "player_count" else 0
    event_name = merged.get("event_name") or ""
    date = merged.get("date") or ""
    merged_structure, merged_bracket_size = _merge_structure(keep_row, remove_row)
    try:
        with _db.session_scope() as session:
            decks_keep = _db.get_decks_by_event(session, keep_row.event_id)
            decks_remove = _db.get_decks_by_event(session, remove_row.event_id)
        try:
            all_pairs = _resolve_merge_pairs(decks_keep, decks_remove, body.player_merges)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        paired_remove_ids = {r for _, r in all_pairs}
        deck_keep_by_id = {d["deck_id"]: d for d in decks_keep}
        deck_remove_by_id = {d["deck_id"]: d for d in decks_remove}

        with _db.session_scope() as session:
            # Both events as they were, in the same transaction as the merge.
            take_snapshot(session, keep_row.event_id, REASON_MERGE)
            take_snapshot(session, remove_row.event_id, REASON_MERGE)
            for (deck_id_keep, deck_id_remove) in all_pairs:
                d_keep = deck_keep_by_id.get(deck_id_keep)
                d_remove = deck_remove_by_id.get(deck_id_remove)
                if not d_keep or not d_remove:
                    continue
                key = f"{deck_id_keep}-{deck_id_remove}"
                res = body.deck_resolutions.get(key, {})
                merged_deck = dict(d_keep)
                merged_deck["event_id"] = keep_row.event_id
                merged_deck["event_name"] = event_name
                merged_deck["date"] = date
                # EDH: apply commanders_archetype resolution to both commanders and archetype
                if res.get("commanders_archetype") == "remove":
                    merged_deck["commanders"] = d_remove.get("commanders") or []
                    merged_deck["archetype"] = d_remove.get("archetype") or ""
                elif res.get("commanders_archetype") == "keep":
                    merged_deck["commanders"] = d_keep.get("commanders") or []
                    merged_deck["archetype"] = d_keep.get("archetype") or ""
                for field in DECK_MERGE_FIELDS:
                    if field in ("commanders", "archetype") and "commanders_archetype" in res:
                        continue  # already set above
                    choice = res.get(field)
                    v_keep = d_keep.get(field)
                    v_remove = d_remove.get(field)
                    if choice == "remove":
                        merged_deck[field] = v_remove if field != "player_count" else (v_remove if v_remove is not None else 0)
                        if field in ("commanders", "mainboard", "sideboard") and merged_deck[field] is None:
                            merged_deck[field] = []
                    else:
                        has_keep = (v_keep not in (None, "", [])) if field != "player_count" else (v_keep is not None)
                        merged_deck[field] = v_keep if has_keep else v_remove
                        if merged_deck[field] is None:
                            merged_deck[field] = [] if field in ("commanders", "mainboard", "sideboard") else (0 if field == "player_count" else "")
                _db.upsert_deck(session, merged_deck, origin=keep_row.origin or _db.ORIGIN_MTGTOP8)
                matchups_choice = res.get("matchups")
                if matchups_choice == "keep":
                    # Keep only kept deck's matchups; remove deck's matchups are dropped when we delete it
                    pass
                elif matchups_choice == "remove":
                    # Use only removed deck's matchups: delete keep's, then reassign remove's to keep
                    _db.delete_matchups_for_deck(session, deck_id_keep)
                    _db.reassign_matchups_to_deck(session, deck_id_remove, deck_id_keep)
                else:
                    # Merge both (default)
                    _db.reassign_matchups_to_deck(session, deck_id_remove, deck_id_keep)
                _db.delete_deck(session, deck_id_remove)

            unpaired_remove_ids = [d["deck_id"] for d in decks_remove if d["deck_id"] not in paired_remove_ids]
            for deck_id in unpaired_remove_ids:
                _db.update_deck_event(session, deck_id, keep_row.event_id, event_name, date)

            _db.update_event(
                session,
                keep_row.event_id,
                event_name=event_name,
                date=date,
                format_id=merged.get("format_id"),
                player_count=merged.get("player_count"),
                store=merged.get("store"),
                location=merged.get("location"),
                structure=merged_structure,
                bracket_size=merged_bracket_size,
            )
            _db.reassign_upload_links_to_event(session, remove_row.event_id, keep_row.event_id)
            _db.delete_event(session, remove_row.event_id, delete_decks=False)
        _load_decks_from_db()
        _invalidate_events_cache()
        decks_merged = len(all_pairs)
        decks_moved = len(unpaired_remove_ids)
        change_log.log(
            change_log.ADMIN,
            "event.merge",
            f"Merged event {remove_row.event_id} into this one ({decks_merged} deck(s) merged, {decks_moved} moved)",
            event_id=keep_row.event_id,
        )
        return {
            "message": "Events merged.",
            "keep_event_id": keep_row.event_id,
            "remove_event_id": remove_row.event_id,
            "decks_merged": decks_merged,
            "decks_moved": decks_moved,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Merge events failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to merge events.")


@router.post("/api/v1/events/{event_id}/decks", dependencies=[Depends(require_admin), Depends(require_database)])
async def upload_decks_to_event(
    event_id: str,
    body: UploadDecksBody | None = None,
    file: UploadFile | None = File(None),
):
    """Upload decks to an existing event (admin-only). Decks are assigned this event_id and event_name/date from the event."""
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        event_name = event_display_name(ev.name, ev.store or "", ev.location or "")
        date, format_id = ev.date, ev.format_id
    if file:
        content = await _read_upload_json_bytes_async(file)
        try:
            raw = json.loads(content.decode("utf-8"))
            decks = raw if isinstance(raw, list) else raw.get("decks", [])
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    elif body and body.decks is not None:
        decks = body.decks
    else:
        raise HTTPException(status_code=400, detail="Provide JSON body with 'decks' or file upload")
    decks = _normalize_split_cards(decks)
    try:
        out = []
        with _db.session_scope() as session:
            # Allocate IDs in the inserting transaction (advisory lock held until commit); consecutive
            # because sessions do not autoflush between allocations.
            next_id = _db.next_manual_deck_id(session)
            for d in decks:
                d = dict(d)
                d["event_id"] = event_id
                d["event_name"] = event_name
                d["date"] = date
                d["format_id"] = format_id
                if "deck_id" not in d or d.get("deck_id") is None:
                    d["deck_id"] = next_id
                    next_id += 1
                out.append(d)
            for d in out:
                _resolve_deck_player(session, d)
                _db.upsert_deck(session, d, origin=_db.ORIGIN_MANUAL)
        _load_decks_from_db()
        change_log.log(change_log.ADMIN, "deck.create", f"Uploaded {len(out)} deck(s) from a file", event_id=event_id)
        return {"event_id": event_id, "loaded": len(out), "message": f"Uploaded {len(out)} decks"}
    except Exception as e:
        logger.exception("Upload decks to event failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to upload decks")


@router.post("/api/v1/events/{event_id}/decks/add", dependencies=[Depends(require_admin_or_event_edit), Depends(require_database)])
def add_blank_deck_to_event(event_id: str, actor: str = Depends(current_actor)):
    """Add one blank deck to an event (admin-only). One deck per player per event; placeholder player used if blank."""
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        eid = _db._event_id_str(event_id)
        existing = session.query(_db.DeckRow).filter(_db.DeckRow.event_id == eid).all()
        player_count = getattr(ev, "player_count", None)
        if player_count is not None and player_count > 0 and len(existing) >= player_count:
            raise HTTPException(
                status_code=400,
                detail=f"Event allows at most {player_count} deck(s). It already has {len(existing)}.",
            )
        # One deck per player_id per event. Placeholder names like "Unnamed" can resolve via aliases
        # or normalized lookup to a player who already has a deck here — pick a name whose resolved
        # player_id is not yet in this event.
        existing_player_ids = {d.player_id for d in existing}
        for n in range(5000):
            player_try = "Unnamed" if n == 0 else f"Unnamed {n}"
            tmp = {"player": player_try}
            _resolve_deck_player(session, tmp)
            if tmp["player_id"] not in existing_player_ids:
                break
        else:
            tmp = {"player": f"Unnamed_{uuid.uuid4().hex[:10]}"}
            _resolve_deck_player(session, tmp)
        event_name = event_display_name(ev.name, ev.store or "", ev.location or "")
        deck_id = _db.next_manual_deck_id(session)
        blank = {
            "deck_id": deck_id,
            "event_id": event_id,
            "event_name": event_name,
            "date": ev.date,
            "format_id": ev.format_id,
            "name": "Unnamed",
            "player": tmp["player"],
            "player_id": tmp["player_id"],
            "rank": "",
            "player_count": 0,
            "commanders": [],
            "mainboard": [],
            "sideboard": [],
        }
        _db.upsert_deck(session, blank, origin=_db.ORIGIN_MANUAL)
    _load_decks_from_db()
    change_log.log(actor, "deck.create", "Added a blank deck", event_id=event_id, deck_id=deck_id)
    return {"event_id": event_id, "deck_id": deck_id, "message": "Deck added"}


def _fetch_hadouken_or_error(url: str) -> HadoukenEvent:
    try:
        hev = fetch_hadouken_event(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except requests.RequestException as e:
        logger.warning("Hadouken fetch failed for %s: %s", url, e)
        raise HTTPException(status_code=502, detail="Could not download the Hadouken page")
    if not hev.standings:
        raise HTTPException(status_code=400, detail="No standings found on the Hadouken page")
    return hev


@router.post("/api/v1/events/{event_id}/hadouken/preview", dependencies=[Depends(require_admin), Depends(require_database)])
def preview_hadouken_import(event_id: str, body: HadoukenPreviewBody):
    """Preview completing this event with players and round results from a Hadouken league page (read-only)."""
    hev = _fetch_hadouken_or_error(body.url)
    try:
        with _db.session_scope() as session:
            return _hadouken.build_preview(session, event_id, hev)
    except LookupError:
        raise HTTPException(status_code=404, detail="Event not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/events/{event_id}/hadouken/apply", dependencies=[Depends(require_admin), Depends(require_database)])
def apply_hadouken_import(event_id: str, body: HadoukenApplyBody):
    """Create missing decks and import all round results from a Hadouken league page into this event."""
    hev = _fetch_hadouken_or_error(body.url)
    try:
        with _db.session_scope() as session:
            result = _hadouken.apply_import(
                session,
                event_id,
                hev,
                body.player_map,
                {name: edit.model_dump() for name, edit in body.standings.items()},
            )
    except LookupError:
        raise HTTPException(status_code=404, detail="Event not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _load_decks_from_db()
    _invalidate_events_cache()
    change_log.log(
        change_log.ADMIN,
        "event.hadouken",
        f"Hadouken import: {result.get('decks_created', 0)} deck(s) created, {result.get('matches_imported', 0)} match(es)",
        event_id=event_id,
    )
    return result


@router.post("/api/v1/events/{event_id}/upload-links", dependencies=[Depends(require_admin), Depends(require_database)])
def create_upload_links(event_id: str, request: Request, body: CreateUploadLinksBody | None = None):
    """Create one or more one-time upload links for an event (admin-only). Pass deck_id to create a link that updates that deck."""
    body = body or CreateUploadLinksBody()
    expires_at = None  # None -> db.create_upload_link applies DEFAULT_LINK_EXPIRY_DAYS
    if body.expires_in_days is not None and body.expires_in_days > 0:
        expires_at = _db.utcnow_naive() + timedelta(days=body.expires_in_days)
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        base_url = _upload_link_base_url(request)
        links = []
        if body.type == "event_edit":
            # One-time link to edit event and decks (no delete event, no new links)
            _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_EVENT_EDIT)
            token = secrets.token_urlsafe(32)
            row = _db.create_upload_link(
                session, token, event_id, expires_at=expires_at, link_type=_db.LINK_TYPE_EVENT_EDIT
            )
            links.append({
                "token": token,
                "url": f"{base_url}/events/{event_id}?token={token}",
                "expires_at": _db.iso_utc(row.expires_at),
            })
        elif body.type == "feedback" and body.deck_id is not None:
            # One-time feedback link for this deck (Event page). Form submits to POST /api/upload/{token}/feedback
            deck_row = session.query(_db.DeckRow).filter(
                _db.DeckRow.deck_id == body.deck_id,
                _db.DeckRow.event_id == _db._event_id_str(event_id),
            ).first()
            if not deck_row:
                raise HTTPException(status_code=404, detail="Deck not found in this event")
            _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_FEEDBACK, deck_id=body.deck_id)
            token = secrets.token_urlsafe(32)
            row = _db.create_upload_link(
                session, token, event_id, expires_at=expires_at, deck_id=body.deck_id, link_type=_db.LINK_TYPE_FEEDBACK
            )
            links.append({
                "token": token,
                "url": f"{base_url}/upload/{token}",
                "expires_at": _db.iso_utc(row.expires_at),
                "deck_id": body.deck_id,
            })
        elif body.deck_id is not None:
            # One-time link to update an existing deck
            deck_row = session.query(_db.DeckRow).filter(
                _db.DeckRow.deck_id == body.deck_id,
                _db.DeckRow.event_id == _db._event_id_str(event_id),
            ).first()
            if not deck_row:
                raise HTTPException(status_code=404, detail="Deck not found in this event")
            _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_DECK_UPDATE, deck_id=body.deck_id)
            token = secrets.token_urlsafe(32)
            row = _db.create_upload_link(session, token, event_id, expires_at=expires_at, deck_id=body.deck_id)
            links.append({
                "token": token,
                "url": f"{base_url}/upload/{token}",
                "expires_at": _db.iso_utc(row.expires_at),
                "deck_id": body.deck_id,
            })
        else:
            count = max(1, min(body.count, 50))
            for _ in range(count):
                token = secrets.token_urlsafe(32)
                row = _db.create_upload_link(session, token, event_id, expires_at=expires_at)
                links.append({
                    "token": token,
                    "url": f"{base_url}/upload/{token}",
                    "expires_at": _db.iso_utc(row.expires_at),
                })
        return {"links": links}


def _event_decks_for_mail(session, event_id: str) -> list:
    """All deck rows of an event (used by the bulk link-email endpoints)."""
    return session.query(_db.DeckRow).filter(_db.DeckRow.event_id == _db._event_id_str(event_id)).all()


def _send_queued_emails(queued: list[tuple[str, str, str, str]], send_email, log_label: str) -> tuple[int, list[str]]:
    """Send (player_name, address, subject, body) emails; return (sent count, failed player names).

    Called after the link-creating transaction has committed, so a provider failure
    never rolls back links that may already have been emailed.
    """
    sent = 0
    failed: list[str] = []
    for player_name, addr, subject, body in queued:
        try:
            send_email(addr, subject, body)
            sent += 1
        except Exception:
            logger.exception("%s failed for %s", log_label, player_name)
            failed.append(player_name)
    return sent, failed


@router.post("/api/v1/events/{event_id}/send-missing-deck-links", dependencies=[Depends(require_admin), Depends(require_database)])
def send_missing_deck_links(event_id: str, request: Request):
    """Email one-time deck links to players with missing (empty) decks. Uses DB-stored emails only. 503 if email not configured."""
    try:
        from api import email as _email
    except ImportError:
        raise HTTPException(status_code=503, detail="Email not configured")
    if not _email.is_email_configured():
        raise HTTPException(
            status_code=503,
            detail="Email not configured: set Brevo SMTP (SMTP_HOST, SMTP_USER, SMTP_PASSWORD) or Brevo API (BREVO_API_KEY + SMTP_FROM). See .env.example.",
        )
    base_url = _upload_link_base_url(request)
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        decks = _event_decks_for_mail(session, event_id)
        # Group decks missing a list by player_id so emails can be batched in one
        # query (resolving by display name does a per-name full-table scan).
        missing_by_pid: dict[int, list] = {}
        for d in decks:
            main = getattr(d, "mainboard", None) or []
            if not (isinstance(main, list) and len(main) > 0):
                pid = getattr(d, "player_id", None)
                if pid is None:
                    continue
                missing_by_pid.setdefault(pid, []).append(d)
        if not missing_by_pid:
            return {"sent": 0, "failed": []}
        email_map = _db.get_emails_for_player_ids(session, list(missing_by_pid))
        queued: list[tuple[str, str, str, str]] = []
        for pid, addr in email_map.items():
            deck_list = missing_by_pid.get(pid, [])
            if not deck_list or not addr:
                continue
            player_name = (deck_list[0].player or "").strip() or str(pid)
            links_for_player = []
            for deck_row in deck_list:
                _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_DECK_UPDATE, deck_id=deck_row.deck_id)
                token = secrets.token_urlsafe(32)
                _db.create_upload_link(
                    session, token, event_id, deck_id=deck_row.deck_id, link_type=_db.LINK_TYPE_DECK_UPDATE
                )
                links_for_player.append(f"{base_url}/upload/{token}")
            event_name = event_display_name(ev.name or "", getattr(ev, "store", "") or "", getattr(ev, "location", "") or "")
            subject = f"Deck upload link: {event_name}"
            body = f"Please submit your deck list for {event_name}.\n\nUse this link (one-time):\n\n" + "\n".join(links_for_player)
            queued.append((player_name, addr, subject, body))
    sent, failed = _send_queued_emails(queued, _email.send_email, "Send missing-deck email")
    return {"sent": sent, "failed": failed}


@router.post("/api/v1/events/{event_id}/send-feedback-links", dependencies=[Depends(require_admin), Depends(require_database)])
def send_feedback_links(event_id: str, request: Request):
    """Email one feedback link per deck to each player (DB-stored emails only). 503 if email not configured."""
    try:
        from api import email as _email
    except ImportError:
        raise HTTPException(status_code=503, detail="Email not configured")
    if not _email.is_email_configured():
        raise HTTPException(
            status_code=503,
            detail="Email not configured: set Brevo SMTP (SMTP_HOST, SMTP_USER, SMTP_PASSWORD) or Brevo API (BREVO_API_KEY + SMTP_FROM). See .env.example.",
        )
    base_url = _upload_link_base_url(request)
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        decks = _event_decks_for_mail(session, event_id)
        if not decks:
            return {"sent": 0, "failed": []}
        # Batch email lookup by player_id (name resolution does a per-name full-table scan).
        player_ids = list({getattr(d, "player_id", None) for d in decks} - {None})
        email_map = _db.get_emails_for_player_ids(session, player_ids)
        queued: list[tuple[str, str, str, str]] = []
        for deck_row in decks:
            pid = getattr(deck_row, "player_id", None)
            addr = email_map.get(pid) if pid is not None else None
            if not addr:
                continue
            _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_FEEDBACK, deck_id=deck_row.deck_id)
            token = secrets.token_urlsafe(32)
            _db.create_upload_link(
                session, token, event_id, deck_id=deck_row.deck_id, link_type=_db.LINK_TYPE_FEEDBACK
            )
            event_name = event_display_name(ev.name or "", getattr(ev, "store", "") or "", getattr(ev, "location", "") or "")
            subject = f"Event feedback: {event_name}"
            body = f"Please submit your match results for {event_name}.\n\nLink (one-time): {base_url}/upload/{token}"
            player_name = (deck_row.player or "").strip() or str(pid)
            queued.append((player_name, addr, subject, body))
    sent, failed = _send_queued_emails(queued, _email.send_email, "Send feedback email")
    return {"sent": sent, "failed": failed}


@router.post("/api/v1/events/{event_id}/send-feedback-link-to-player", dependencies=[Depends(require_admin), Depends(require_database)])
def send_feedback_link_to_player(event_id: str, request: Request, body: SendFeedbackLinkToPlayerBody):
    """Email one feedback link to a single player for this event. Invalidates any previous feedback link for that player's deck. 503 if email not configured."""
    try:
        from api import email as _email
    except ImportError:
        raise HTTPException(status_code=503, detail="Email not configured")
    if not _email.is_email_configured():
        raise HTTPException(
            status_code=503,
            detail="Email not configured: set Brevo SMTP (SMTP_HOST, SMTP_USER, SMTP_PASSWORD) or Brevo API (BREVO_API_KEY + SMTP_FROM). See .env.example.",
        )
    player = (body.player or "").strip()
    if not player:
        raise HTTPException(status_code=400, detail="player is required")
    canonical = _normalize_player(player)
    base_url = _upload_link_base_url(request)
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        deck_row = _db.get_deck_by_event_and_player(session, event_id, canonical)
        if not deck_row:
            raise HTTPException(status_code=404, detail="No deck for this player in this event")
        addr = _db.get_player_email(session, canonical)
        if not addr or not addr.strip():
            raise HTTPException(status_code=400, detail="No email set for this player. Set email on the player's page first.")
        _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_FEEDBACK, deck_id=deck_row.deck_id)
        token = secrets.token_urlsafe(32)
        _db.create_upload_link(
            session, token, event_id, deck_id=deck_row.deck_id, link_type=_db.LINK_TYPE_FEEDBACK
        )
        event_name = event_display_name(ev.name or "", getattr(ev, "store", "") or "", getattr(ev, "location", "") or "")
        subject = f"Event feedback: {event_name}"
        body_text = f"Please submit your match results for {event_name}.\n\nLink (one-time): {base_url}/upload/{token}"
    try:
        _email.send_email(addr, subject, body_text)
    except Exception as e:
        logger.exception("Send feedback email failed for %s", canonical)
        raise HTTPException(status_code=500, detail="Failed to send email") from e
    return {"sent": 1}


@router.get("/api/v1/events/{event_id}/missing-matchups", dependencies=[Depends(require_admin), Depends(require_database)])
def get_missing_matchups(event_id: str):
    """List players (decks) in this event that have fewer matchups than expected (admin).
    Expected = number of decks in event minus one."""
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        missing = _db.list_missing_matchups_for_event(session, event_id)
    return {"missing": missing}


@router.get("/api/v1/events/{event_id}/matchup-discrepancies", dependencies=[Depends(require_admin), Depends(require_database)])
def get_matchup_discrepancies(event_id: str):
    """List matchup pairs where both players reported and results disagree (admin)."""
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        rows = _db.list_matchups_for_event(session, event_id)
        discrepancies = []
        for from_a, from_b in find_matchup_discrepancies(rows):
            discrepancies.append({
                "deck_id_a": from_a["deck_id"],
                "deck_id_b": from_b["deck_id"],
                "matchup_a": from_a,
                "matchup_b": from_b,
                "result_a": from_a["result"],
                "result_b": from_b["result"],
            })
        deck_ids = set()
        for d in discrepancies:
            deck_ids.add(d["deck_id_a"])
            deck_ids.add(d["deck_id_b"])
        player_by_deck = {}
        if deck_ids:
            rows = session.query(_db.DeckRow).filter(_db.DeckRow.deck_id.in_(deck_ids)).all()
            for r in rows:
                player_by_deck[r.deck_id] = (r.player or "").strip() or "(unknown)"
        for d in discrepancies:
            d["player_a"] = player_by_deck.get(d["deck_id_a"], "(unknown)")
            d["player_b"] = player_by_deck.get(d["deck_id_b"], "(unknown)")
        return {"discrepancies": discrepancies}
