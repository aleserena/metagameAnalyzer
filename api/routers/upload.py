import json
import logging
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from fastapi.responses import Response
from src.mtgtop8.scraper import event_display_name

from api.dependencies import (
    require_database,
)
from api.helpers import (
    _build_board,
    _normalize_commanders,
    _normalize_split_cards,
)
from api.schemas.decks import DeckListBody, SubmitDeckBody
from api.schemas.upload import EventFeedbackBody
from api.state import (
    _get_deck_by_id,
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
    _is_intentional_draw_result,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_validated_upload_link(
    session,
    token: str,
    *,
    expected_link_type: str | None = None,
    forbid_event_edit: bool = False,
    require_deck: bool = False,
    missing_deck_detail: str = "Feedback link has no deck",
    mark_used: bool = False,
):
    """Load and validate a one-time upload link and its event.

    Common checks:
    - Link exists and matches expected_link_type (if provided)
    - Optionally forbid event-edit links (for regular upload endpoints)
    - Optionally require an attached deck_id
    - Not already used and not expired
    - Associated event still exists
    """
    row = _db.get_upload_link(session, token)
    if not row:
        raise HTTPException(status_code=404, detail="Link not found or invalid")

    link_type = getattr(row, "link_type", _db.LINK_TYPE_DECK_UPLOAD)

    if forbid_event_edit and link_type == _db.LINK_TYPE_EVENT_EDIT:
        raise HTTPException(status_code=404, detail="Use event edit link on the event page")

    if expected_link_type and link_type != expected_link_type:
        if expected_link_type == _db.LINK_TYPE_EVENT_EDIT:
            detail = "Not an event edit link"
        elif expected_link_type == _db.LINK_TYPE_FEEDBACK:
            detail = "Not a feedback link"
        else:
            detail = "Invalid link type"
        raise HTTPException(status_code=404, detail=detail)

    if require_deck and getattr(row, "deck_id", None) is None:
        raise HTTPException(status_code=404, detail=missing_deck_detail)

    if row.used_at is not None:
        raise HTTPException(status_code=404, detail="Link already used")

    if row.expires_at is not None and row.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=404, detail="Link expired")

    ev = _db.get_event(session, row.event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    if mark_used:
        _db.mark_upload_link_used(session, token)

    return row, ev


@router.get("/api/v1/upload/{token}", dependencies=[Depends(require_database)])
def get_upload_link_info(token: str):
    """Return event info for a valid one-time upload link (public). For update links, also return current deck."""
    with _db.session_scope() as session:
        row, ev = _get_validated_upload_link(
            session,
            token,
            forbid_event_edit=True,
        )
        event_name = event_display_name(ev.name, ev.store or "", ev.location or "")
        link_type = getattr(row, "link_type", _db.LINK_TYPE_DECK_UPLOAD)
        purpose = "feedback" if link_type == _db.LINK_TYPE_FEEDBACK else "deck"
        out = {
            "event_id": row.event_id,
            "event_name": event_name,
            "format_id": ev.format_id or "",
            "date": ev.date or "",
            "mode": "update" if getattr(row, "deck_id", None) else "create",
            "purpose": purpose,
        }
        if getattr(row, "deck_id", None) is not None:
            deck = _get_deck_by_id(row.deck_id)
            if deck:
                out["deck_id"] = deck["deck_id"]
                deck_out = {
                    "deck_id": deck["deck_id"],
                    "name": deck.get("name", ""),
                    "player": deck.get("player", ""),
                    "rank": deck.get("rank", ""),
                    "mainboard": deck.get("mainboard", []),
                    "sideboard": deck.get("sideboard", []),
                    "commanders": deck.get("commanders", []),
                    "archetype": deck.get("archetype"),
                }
                if purpose == "feedback":
                    matchup_rows = _db.list_matchups_by_deck(session, row.deck_id)
                    deck_out["matchups"] = [
                        {
                            "opponent_player": m.get("opponent_player", ""),
                            "result": m.get("result", "1-1"),
                            "intentional_draw": _is_intentional_draw_result(m.get("result") or ""),
                        }
                        for m in matchup_rows
                    ]
                    # Other players in this event (for opponent dropdown), excluding this deck's player
                    current_player = (deck.get("player") or "").strip()
                    event_players_set = set()
                    for d in state.decks:
                        if str(d.get("event_id")) != str(row.event_id):
                            continue
                        p = (d.get("player") or "").strip()
                        if p and p != current_player:
                            event_players_set.add(p)
                    deck_out["event_players"] = sorted(event_players_set)
                    # Matchups others reported vs this player (prepopulate: their win = our loss)
                    current_player_norm = _normalize_player((deck.get("player") or "").strip())
                    reported_against_me = _db.list_matchups_reported_against_player(
                        session, row.event_id, current_player_norm
                    )
                    inverted = []
                    for r in reported_against_me:
                        res = (r.get("result") or "").strip().lower()
                        if res == "win":
                            inv_result = "loss"
                        elif res == "loss":
                            inv_result = "win"
                        elif res == "intentional_draw_win":
                            inv_result = "intentional_draw_loss"
                        elif res == "intentional_draw_loss":
                            inv_result = "intentional_draw_win"
                        else:
                            inv_result = "draw" if res == "intentional_draw" else "draw"
                        # Use normalized name so it matches opponent dropdown (event_players / deck list)
                        reporting_player = _normalize_player((r.get("reporting_player") or "").strip())
                        if reporting_player and reporting_player != "(unknown)":
                            inverted.append({
                                "opponent_player": reporting_player,
                                "result": inv_result,
                                "intentional_draw": _is_intentional_draw_result(res),
                                "round": r.get("round"),
                            })
                    deck_out["opponent_reported_matchups"] = inverted
                out["deck"] = deck_out
            else:
                out["deck_id"] = row.deck_id
                out["deck"] = None
        return out


@router.get("/api/v1/event-edit/{token}", dependencies=[Depends(require_database)])
def get_event_edit_link_info(token: str):
    """Validate a one-time event-edit link, mark it as used, and return event_id. Public (no auth)."""
    with _db.session_scope() as session:
        row, _ = _get_validated_upload_link(
            session,
            token,
            expected_link_type=_db.LINK_TYPE_EVENT_EDIT,
            mark_used=True,
        )
        return {"event_id": row.event_id}


def _validate_deck_payload(body: SubmitDeckBody) -> None:
    """Raise HTTPException if payload is invalid."""
    if not (body.player or "").strip():
        raise HTTPException(status_code=400, detail="player is required")
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    main = body.mainboard or []
    side = body.sideboard or []
    if len(main) > 500:
        raise HTTPException(status_code=400, detail="mainboard has too many entries (max 500)")
    if len(side) > 100:
        raise HTTPException(status_code=400, detail="sideboard has too many entries (max 100)")
    if not main:
        raise HTTPException(status_code=400, detail="mainboard is required and must not be empty")
    for card in main:
        if not isinstance(card, dict) or "card" not in card:
            raise HTTPException(status_code=400, detail="mainboard entries must be { qty, card }")
    if not any(str(c.get("card", "")).strip() for c in main):
        raise HTTPException(status_code=400, detail="mainboard must have at least one non-empty card")
    for card in side:
        if not isinstance(card, dict) or "card" not in card:
            raise HTTPException(status_code=400, detail="sideboard entries must be { qty, card }")


def _submit_create_with_upload_link(session, row, ev, event_name: str, body: SubmitDeckBody):
    """Create a new deck via upload link. Returns (deck_id, status_code)."""
    deck_id = _db.next_manual_deck_id(session)
    commanders = body.commanders if body.commanders is not None else []
    if not isinstance(commanders, list):
        commanders = []
    mainboard = _build_board(body.mainboard)
    sideboard = _build_board(body.sideboard)
    commanders = _normalize_commanders(commanders)
    format_id = (ev.format_id or "").upper()
    if format_id == "EDH" and not commanders and mainboard:
        commanders = [mainboard[0]["card"]]
    deck = {
        "deck_id": deck_id,
        "event_id": row.event_id,
        "event_name": event_name,
        "date": ev.date or "",
        "format_id": ev.format_id or "",
        "name": (body.name or "").strip(),
        "player": _normalize_player((body.player or "").strip()),
        "rank": (body.rank or "").strip(),
        "player_count": 0,
        "commanders": commanders,
        "mainboard": mainboard,
        "sideboard": sideboard,
    }
    deck_list = _normalize_split_cards([deck])
    _resolve_deck_player(session, deck_list[0])
    _db.upsert_deck(session, deck_list[0], origin=_db.ORIGIN_MANUAL)
    return deck_id


@router.post("/api/v1/upload/{token}", dependencies=[Depends(require_database)])
def submit_deck_with_upload_link(token: str, body: SubmitDeckBody):
    """Submit or update a deck using a one-time upload link (public). Update links modify the linked deck."""
    _validate_deck_payload(body)
    with _db.session_scope() as session:
        row, ev = _get_validated_upload_link(
            session,
            token,
            forbid_event_edit=True,
        )
        event_name = event_display_name(ev.name, ev.store or "", ev.location or "")

        deck_id = getattr(row, "deck_id", None)
        if deck_id is not None:
            # Update existing deck
            current = _get_deck_by_id(deck_id)
            if not current:
                raise HTTPException(status_code=400, detail="Deck not found")
            current = dict(current)
            commanders = body.commanders if body.commanders is not None else []
            if not isinstance(commanders, list):
                commanders = []
            mainboard = _build_board(body.mainboard)
            sideboard = _build_board(body.sideboard)
            commanders = _normalize_commanders(commanders)
            format_id = (current.get("format_id") or "").upper()
            if format_id == "EDH" and not commanders and mainboard:
                commanders = [mainboard[0]["card"]]
            current["name"] = (body.name or "").strip()
            current["player"] = _normalize_player((body.player or "").strip())
            current["rank"] = (body.rank or "").strip()
            current["mainboard"] = mainboard
            current["sideboard"] = sideboard
            current["commanders"] = commanders
            deck_list = _normalize_split_cards([current])
            _resolve_deck_player(session, deck_list[0])
            _db.upsert_deck(session, deck_list[0], origin=current.get("origin", _db.ORIGIN_MANUAL))
            _db.mark_upload_link_used(session, token)
            _load_decks_from_db()
            return {"deck_id": deck_id, "message": "Deck updated successfully"}
        else:
            # Create new deck
            deck_id = _submit_create_with_upload_link(session, row, ev, event_name, body)
            _db.mark_upload_link_used(session, token)
            _load_decks_from_db()
            return Response(
                content=json.dumps({"deck_id": deck_id, "message": "Deck submitted successfully"}),
                status_code=201,
                media_type="application/json",
            )


@router.post("/api/v1/upload/{token}/feedback", dependencies=[Depends(require_database)])
def submit_feedback_with_upload_link(token: str, body: EventFeedbackBody):
    """Submit event feedback (archetype + matchups) via one-time feedback link. Deck must exist; deck list not required."""
    if not (body.archetype or "").strip():
        raise HTTPException(status_code=400, detail="archetype is required")
    if len(body.matchups or []) > 12:
        raise HTTPException(status_code=400, detail="Maximum 12 matchups allowed")
    with _db.session_scope() as session:
        row, ev = _get_validated_upload_link(
            session,
            token,
            expected_link_type=_db.LINK_TYPE_FEEDBACK,
            require_deck=True,
            missing_deck_detail="Feedback link has no deck",
        )
        deck_id = row.deck_id
        deck_dict = _get_deck_by_id(deck_id)
        if not deck_dict:
            raise HTTPException(status_code=400, detail="Deck not found")
        deck_dict = dict(deck_dict)
        deck_dict["archetype"] = (body.archetype or "").strip()
        if body.deck_name is not None:
            deck_dict["name"] = (body.deck_name or "").strip()
        if body.rank is not None:
            deck_dict["rank"] = (body.rank or "").strip()
        _db.upsert_deck(session, deck_dict, origin=deck_dict.get("origin", _db.ORIGIN_MANUAL))
        feedback_event_id = _db._event_id_str(deck_dict.get("event_id", ""))
        matchup_rows = []
        for m in body.matchups or []:
            result_raw = (m.result or "1-1").strip().lower()
            if result_raw in ("bye", "drop"):
                opponent_player = "Bye" if result_raw == "bye" else "(drop)"
                matchup_rows.append({
                    "opponent_player": opponent_player,
                    "opponent_deck_id": None,
                    "opponent_archetype": None,
                    "result": result_raw,
                    "result_note": None,
                    "round": None,
                })
                continue
            opp_player = _normalize_player((m.opponent_player or "").strip())
            if not opp_player or opp_player == "(unknown)":
                continue
            opp_deck = _db.get_deck_by_event_and_player(session, feedback_event_id, opp_player)
            opp_deck_id = opp_deck.deck_id if opp_deck else None
            opp_archetype = _db.deck_archetype_for_deck_id(session, opp_deck_id)
            matchup_rows.append({
                "opponent_player": opp_player,
                "opponent_deck_id": opp_deck_id,
                "opponent_archetype": opp_archetype,
                "result": (m.result or "1-1").strip(),
                "result_note": None,
                "round": None,
            })
        _db.upsert_matchups_for_deck(session, deck_id, matchup_rows)
        _db.mark_upload_link_used(session, token)
    _load_decks_from_db()
    return {"deck_id": deck_id, "message": "Feedback submitted successfully"}


@router.post("/api/v1/upload/{token}/decklist", dependencies=[Depends(require_database)])
def submit_decklist_with_upload_link(token: str, body: DeckListBody):
    """Update deck list (mainboard/sideboard/commanders) via one-time feedback link. Does not mark the link as used."""
    with _db.session_scope() as session:
        row, _ = _get_validated_upload_link(
            session,
            token,
            expected_link_type=_db.LINK_TYPE_FEEDBACK,
            require_deck=True,
            missing_deck_detail="No deck linked",
        )
        deck_id = row.deck_id
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    mainboard = _build_board(body.mainboard)
    if not mainboard:
        raise HTTPException(status_code=400, detail="mainboard must have at least one card")
    sideboard = _build_board(body.sideboard)
    commanders = _normalize_commanders(body.commanders or [])
    current = dict(deck_dict)
    current["mainboard"] = mainboard
    current["sideboard"] = sideboard
    current["commanders"] = commanders if commanders else None
    if (current.get("format_id") or "").upper() == "EDH" and not current.get("commanders") and current.get("mainboard"):
        current["commanders"] = [current["mainboard"][0]["card"]]
    try:
        with _db.session_scope() as session:
            _db.upsert_deck(session, current, origin=current.get("origin", _db.ORIGIN_MTGTOP8))
    except Exception as e:
        logger.exception("Deck list update failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    _load_decks_from_db()
    return {"deck_id": deck_id, "message": "Deck list updated"}
