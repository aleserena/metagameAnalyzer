import logging
import re

import requests
from fastapi import Depends, HTTPException, Query
from src.mtgtop8.analyzer import (
    deck_analysis,
    effective_commanders,
    find_duplicate_decks,
    similar_decks,
)
from src.mtgtop8.card_lookup import lookup_cards
from src.mtgtop8.models import Deck
from src.mtgtop8.scraper import event_display_name

from api.dependencies import (
    optional_admin,
    require_admin,
    require_admin_or_event_edit_deck,
    require_database,
)
from api.helpers import (
    _build_board,
    _deck_sort_key,
    _filter_decks_for_query,
    _normalize_commanders,
    _normalize_search,
    _parse_date_sortkey,
    _rank_sort_value,
)
from api.schemas.decks import ImportMoxfieldBody, UpdateDeckBody
from api.schemas.matchups import AdminMatchupsBody
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


def _deck_sort_key_by(sort: str, order: str):
    """Return (key_fn, reverse) for sorting decks."""
    reverse = order == "desc"

    def key(d: dict):
        if sort == "date":
            date_key = _parse_date_sortkey(d.get("date", ""))
            val = int(date_key) if date_key.isdigit() else 0
            rv = _rank_sort_value(d.get("rank", ""))
            return (-val if reverse else val, -rv if reverse else rv)
        if sort == "rank":
            rk = _rank_sort_value(d.get("rank", ""))
            return (-rk if reverse else rk,)
        if sort == "player":
            return ((d.get("player") or "").lower(),)
        if sort == "name":
            return ((d.get("name") or "").lower(),)
        return _deck_sort_key(d)

    return key, reverse if sort in ("player", "name") else False


@router.get("/api/v1/decks")
def list_decks(
    event_id: str | None = Query(None, description="Filter by event ID (single, for backward compatibility)"),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    commander: str | None = Query(None, description="Filter by commander name (substring)"),
    deck_name: str | None = Query(None, description="Filter by deck name (substring)"),
    archetype: str | None = Query(None, description="Filter by archetype (substring)"),
    player: str | None = Query(None, description="Filter by player name (substring)"),
    player_id: int | None = Query(None, description="Filter by player ID (exact)"),
    card: str | None = Query(None, description="Filter by card name (substring, commander, mainboard or sideboard)"),
    colors: str | None = Query(
        None,
        description="Filter by commander color identity (comma-separated, e.g. 'W,U' for Azorius)",
    ),
    sort: str = Query("date", description="Sort by: date, rank, player, name"),
    order: str = Query("desc", description="Sort order: asc, desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    is_admin: str | None = Depends(optional_admin),
):
    """List decks with optional filters and pagination. When admin and event_id, includes has_email per deck."""
    filtered = _filter_decks_for_query(state.decks, event_id, event_ids, None, None)
    if commander:
        c_norm = _normalize_search(commander)
        filtered = [
            d for d in filtered
            if any(c_norm in _normalize_search(c or "") for c in d.get("commanders", []))
        ]
    if deck_name:
        dn_norm = _normalize_search(deck_name)
        filtered = [d for d in filtered if dn_norm in _normalize_search(d.get("name") or "")]
    if archetype:
        arch_norm = _normalize_search(archetype)
        filtered = [
            d for d in filtered
            if arch_norm in _normalize_search(d.get("archetype") or "")
        ]
    if player:
        p_norm = _normalize_search(player)
        filtered = [
            d for d in filtered
            if p_norm in _normalize_search(d.get("player") or "")
            or p_norm in _normalize_search(_normalize_player(d.get("player") or ""))
        ]
    if player_id is not None:
        filtered = [d for d in filtered if d.get("player_id") == player_id]
    if card:
        card_norm = _normalize_search(card)
        filtered = [
            d for d in filtered
            if any(card_norm in _normalize_search(c or "") for c in d.get("commanders", []))
            or any(
                card_norm in _normalize_search((e.get("card") if isinstance(e, dict) else "") or "")
                for section in (d.get("mainboard", []), d.get("sideboard", []))
                for e in section
            )
        ]

    # Optional filter by commander-based color identity (EDH / Commander decks).
    # Also attaches color_identity (ordered WUBRG + C for colorless) to each deck for UI mana symbols.
    color_filter: set[str] | None = None
    if colors:
        wanted = {c.strip().upper() for c in colors.split(",") if c.strip()}
        valid = {"W", "U", "B", "R", "G", "C"}
        color_filter = {c for c in wanted if c in valid} or None

    try:
        if filtered:
            deck_objs = [Deck.from_dict(d) for d in filtered]
            commander_names = list(
                {c for deck in deck_objs for c in effective_commanders(deck) if c}
            )
            metadata = lookup_cards(commander_names) if commander_names else {}
            color_order = ["W", "U", "B", "R", "G", "C"]
            filtered_with_colors: list[dict] = []
            for deck_obj, d in zip(deck_objs, filtered):
                ec = effective_commanders(deck_obj)
                ci: set[str] = set()
                for name in ec:
                    entry = metadata.get(name)
                    if entry and "error" not in entry:
                        for c in entry.get("color_identity") or entry.get("colors") or []:
                            if c in {"W", "U", "B", "R", "G"}:
                                ci.add(c)
                # Treat EDH/Commander decks with no colors as colorless ("C") for filtering and display.
                is_edh = (deck_obj.format_id or "").upper() in {"EDH", "CEDH", "COMMANDER"}
                if not ci and is_edh and ec:
                    ci.add("C")
                if ci:
                    d["color_identity"] = [c for c in color_order if c in ci]
                if color_filter:
                    # Require deck to contain all selected colors.
                    if not ci or not color_filter.issubset(ci):
                        continue
                    filtered_with_colors.append(d)
            if color_filter:
                filtered = filtered_with_colors
    except Exception:
        # Color identity and color filter are cosmetic; ignore lookup failures.
        logger.exception("Color identity lookup failed for /api/decks")

    sort_val = sort if sort in ("date", "rank", "player", "name") else "date"
    order_val = order if order in ("asc", "desc") else "desc"
    key_fn, reverse = _deck_sort_key_by(sort_val, order_val)
    filtered = sorted(filtered, key=key_fn, reverse=reverse)
    total = len(filtered)
    page = filtered[skip : skip + limit]

    # Normalize player names for display (merge aliases)
    page = [{**d, "player": _normalize_player(d.get("player") or "")} for d in page]
    if is_admin == "admin" and event_id is not None and state.database_available():
        players = list({d.get("player") or "" for d in page})
        with _db.session_scope() as session:
            email_map = _db.get_emails_for_players(session, players)
        for d in page:
            d["has_email"] = (d.get("player") or "") in email_map
    return {"decks": page, "total": total, "skip": skip, "limit": limit}


@router.get("/api/v1/decks/compare")
def compare_decks(ids: str = Query(..., description="Comma-separated deck IDs")):
    """Get multiple decks by ID for comparison."""
    try:
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deck IDs")
    if len(id_list) < 2 or len(id_list) > 4:
        raise HTTPException(status_code=400, detail="Provide 2 to 4 deck IDs")
    deck_map = {d.get("deck_id"): d for d in state.decks}
    result = []
    for did in id_list:
        if did not in deck_map:
            raise HTTPException(status_code=404, detail=f"Deck {did} not found")
        d = dict(deck_map[did])
        d["player"] = _normalize_player(d.get("player") or "")
        result.append(d)
    return {"decks": result}


def _deck_duplicate_info(deck_id: int) -> dict | None:
    """Return duplicate info for a deck: is_duplicate, duplicate_of, same_mainboard_ids, same_mainboard_decks, primary_deck."""
    decks = [Deck.from_dict(d) for d in state.decks]
    dup_map = find_duplicate_decks(decks)
    deck_map = {d.get("deck_id"): d for d in state.decks}

    def deck_summary(did: int) -> dict:
        d = deck_map.get(did, {})
        return {
            "deck_id": did,
            "name": d.get("name"),
            "player": _normalize_player(d.get("player") or ""),
            "event_name": d.get("event_name"),
            "date": d.get("date"),
            "rank": d.get("rank"),
        }

    for primary, others in dup_map.items():
        if deck_id == primary:
            same_mainboard_decks = [deck_summary(did) for did in others]
            return {
                "is_duplicate": False,
                "duplicate_of": None,
                "same_mainboard_ids": others,
                "same_mainboard_decks": same_mainboard_decks,
            }
        if deck_id in others:
            primary_deck = deck_summary(primary)
            same_mainboard_ids = [x for x in others if x != deck_id]
            same_mainboard_decks = [deck_summary(did) for did in same_mainboard_ids]
            return {
                "is_duplicate": True,
                "duplicate_of": primary,
                "same_mainboard_ids": same_mainboard_ids,
                "same_mainboard_decks": same_mainboard_decks,
                "primary_deck": primary_deck,
            }
    return None


@router.get("/api/v1/decks/duplicates")
def list_duplicate_decks(
    event_ids: str | None = Query(None, description="Limit to events (comma-separated)"),
):
    """Decks with identical mainboard (duplicates across events)."""
    candidate = _filter_decks_for_query(state.decks, None, event_ids, None, None)
    decks = [Deck.from_dict(d) for d in candidate]
    dup_map = find_duplicate_decks(decks)
    deck_map = {d.get("deck_id"): d for d in state.decks}
    result = []
    for primary_id, duplicate_ids in dup_map.items():
        primary = deck_map.get(primary_id, {})
        result.append({
            "primary_deck_id": primary_id,
            "primary_name": primary.get("name"),
            "primary_player": _normalize_player(primary.get("player") or ""),
            "primary_event": primary.get("event_name"),
            "primary_date": primary.get("date"),
            "duplicate_deck_ids": duplicate_ids,
            "duplicates": [
                {
                    "deck_id": did,
                    "name": deck_map.get(did, {}).get("name"),
                    "player": _normalize_player(deck_map.get(did, {}).get("player") or ""),
                    "event_name": deck_map.get(did, {}).get("event_name"),
                    "date": deck_map.get(did, {}).get("date"),
                }
                for did in duplicate_ids
            ],
        })
    return {"duplicates": result}


@router.get("/api/v1/decks/{deck_id}")
def get_deck(deck_id: int):
    """Get single deck by ID."""
    d = _get_deck_by_id(deck_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deck not found")
    out = dict(d)
    out["player"] = _normalize_player(out.get("player") or "")
    dup = _deck_duplicate_info(deck_id)
    if dup:
        out["duplicate_info"] = dup
    return out


@router.get("/api/v1/decks/{deck_id}/similar")
def get_similar_decks(
    deck_id: int,
    limit: int = Query(10, ge=1, le=20),
    event_ids: str | None = Query(None, description="Limit to events (comma-separated)"),
):
    """Decks with high card overlap (same metagame)."""
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    deck = Deck.from_dict(deck_dict)
    candidate_decks = _filter_decks_for_query(state.decks, None, event_ids, None, None)
    all_decks = [Deck.from_dict(d) for d in candidate_decks]
    return {"similar": similar_decks(deck, all_decks, limit=limit)}


@router.get("/api/v1/decks/{deck_id}/analysis")
def get_deck_analysis(deck_id: int):
    """Deck analysis: mana curve, color distribution, lands distribution."""
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    deck = Deck.from_dict(deck_dict)
    card_names = list({c for _, c in deck.mainboard} | {c for _, c in deck.sideboard})
    metadata = lookup_cards(card_names)
    # Ensure every deck card name has meta (case-insensitive fallback for name variants)
    merged: dict = {}
    for name in card_names:
        if name in metadata and "error" not in metadata.get(name, {}):
            merged[name] = metadata[name]
        else:
            for k, v in metadata.items():
                if "error" not in v and k.lower() == name.lower():
                    merged[name] = v
                    break
    return deck_analysis(deck, merged)


def _classify_finality(oracle_text: str, type_line: str) -> str:
    """Classify a card's functional role for budget-alternative matching.

    Checked in priority order so more-specific functional tags win over generic type labels.
    """
    text = oracle_text.lower()
    tline = type_line.lower()

    if "counter target" in text:
        return "counter"
    if "draw" in text and "card" in text:
        return "card-draw"
    if "add {" in text or ("search your library" in text and "land" in text):
        return "ramp"
    if "destroy all" in text or "exile all" in text or "deals damage to each" in text:
        return "wipe"
    if ("destroy target" in text or "exile target" in text) and any(
        w in text for w in ("creature", "artifact", "enchantment", "permanent", "planeswalker")
    ):
        return "removal"
    if "search your library" in text:
        return "tutor"
    if "from your graveyard" in text or "from a graveyard" in text:
        return "graveyard"
    if "create" in text and "token" in text:
        return "token"
    if "protection from" in text or "hexproof" in text or "shroud" in text:
        return "protection"

    if "land" in tline:
        return "land"
    if "creature" in tline:
        return "creature"
    if "planeswalker" in tline:
        return "planeswalker"
    if "instant" in tline or "sorcery" in tline:
        return "spell"
    if "artifact" in tline:
        return "artifact"
    if "enchantment" in tline:
        return "enchantment"
    return "other"


@router.get("/api/v1/decks/{deck_id}/budget-alternatives")
def get_budget_alternatives(
    deck_id: int,
    threshold: float = Query(5.0, ge=0.01, description="Max price for a replacement card in the selected currency"),
    limit: int = Query(10, ge=1, le=30),
    currency: str = Query("usd", pattern="^(usd|eur|tix)$"),
):
    """For each expensive mainboard card (price > threshold), suggest cheaper replacements
    played in same-archetype decks (fallback: similar decks by card overlap)."""
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    deck = Deck.from_dict(deck_dict)

    mainboard_names = list({c for _, c in deck.mainboard})
    metadata = lookup_cards(mainboard_names)

    expensive: list[tuple[str, float]] = []
    for _, card in deck.mainboard:
        meta = metadata.get(card) or {}
        price_str = (meta.get("prices") or {}).get(currency)
        if price_str:
            try:
                price = float(price_str)
                if price > threshold:
                    expensive.append((card, price))
            except ValueError:
                pass

    if not expensive:
        return {"deck_id": deck_id, "threshold": threshold, "currency": currency, "source": "archetype", "alternatives": []}

    deck_archetype = deck_dict.get("archetype")
    deck_format = deck_dict.get("format_id")
    arch_key = _db.archetype_canonical_key(deck_archetype) if deck_archetype else None

    # Prefer same-archetype decks; fall back to similar decks when pool is too small
    if arch_key and deck_archetype:
        candidate_dicts = [
            d for d in state.decks
            if d.get("deck_id") != deck_id
            and d.get("format_id") == deck_format
            and _db.archetype_canonical_key(d.get("archetype")) == arch_key
        ]
        source = "archetype"
    else:
        candidate_dicts = []
        source = "similar"

    if len(candidate_dicts) < 3:
        all_deck_objs = [Deck.from_dict(d) for d in state.decks if d.get("deck_id") != deck_id]
        similar_summaries = similar_decks(deck, all_deck_objs, limit=20)
        similar_ids = {s["deck_id"] for s in similar_summaries}
        candidate_decks = [
            Deck.from_dict(d) for d in state.decks if d.get("deck_id") in similar_ids
        ]
        source = "similar"
    else:
        candidate_decks = [Deck.from_dict(d) for d in candidate_dicts]

    deck_mainboard_names = {c for _, c in deck.mainboard}

    # Collect all candidate card names for a single bulk lookup
    candidate_card_names: set[str] = set()
    for cd in candidate_decks:
        for _, c in cd.mainboard:
            if c not in deck_mainboard_names:
                candidate_card_names.add(c)

    candidate_metadata = lookup_cards(list(candidate_card_names))

    # For EDH/cEDH, build the commander color identity and use it to exclude illegal replacements
    edh_formats = {"EDH", "cEDH"}
    allowed_colors: set[str] | None = None
    if deck_format in edh_formats and deck.commanders:
        commander_meta = lookup_cards(list(deck.commanders))
        allowed_colors = set()
        for cmd in deck.commanders:
            ci = (commander_meta.get(cmd) or {}).get("color_identity") or []
            allowed_colors.update(ci)

    # Build frequency map: card → number of candidate decks containing it
    freq: dict[str, int] = {}
    for cd in candidate_decks:
        seen = set()
        for _, c in cd.mainboard:
            if c not in deck_mainboard_names and c not in seen:
                freq[c] = freq.get(c, 0) + 1
                seen.add(c)

    alternatives = []
    for expensive_card, expensive_price in expensive:
        exp_meta = metadata.get(expensive_card) or {}
        exp_finality = _classify_finality(
            exp_meta.get("oracle_text") or "",
            exp_meta.get("type_line") or "",
        )
        replacements = []
        for card, count in freq.items():
            meta = candidate_metadata.get(card) or {}
            price_str = (meta.get("prices") or {}).get(currency)
            if not price_str:
                continue
            try:
                price = float(price_str)
            except ValueError:
                continue
            if price >= threshold:
                continue
            cand_finality = _classify_finality(
                meta.get("oracle_text") or "",
                meta.get("type_line") or "",
            )
            if cand_finality != exp_finality:
                continue
            if allowed_colors is not None:
                card_ci = set(meta.get("color_identity") or [])
                if not card_ci.issubset(allowed_colors):
                    continue
            replacements.append({
                "card": card,
                "price": price,
                "deck_count": count,
                "savings": round(expensive_price - price, 2),
            })
        if not replacements:
            continue
        replacements.sort(key=lambda r: (-r["deck_count"], r["price"]))
        alternatives.append({
            "expensive_card": expensive_card,
            "expensive_price": expensive_price,
            "replacements": replacements[:limit],
        })

    return {"deck_id": deck_id, "threshold": threshold, "currency": currency, "source": source, "alternatives": alternatives}


@router.put("/api/v1/decks/{deck_id}", dependencies=[Depends(require_admin_or_event_edit_deck), Depends(require_database)])
def update_deck_endpoint(deck_id: int, body: UpdateDeckBody):
    """Update deck metadata (admin-only)."""
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    current = dict(deck_dict)
    # DB player row before this edit (used to merge away Unnamed* rows when renaming to a real player)
    prior_player_id = deck_dict.get("player_id")
    # Merge body into current
    if body.name is not None:
        current["name"] = body.name
    if body.player is not None:
        current["player"] = _normalize_player(body.player.strip())
        # deck_dict always includes player_id; force re-resolve so player_id matches the new name
        current.pop("player_id", None)
    if body.rank is not None:
        current["rank"] = body.rank
    if body.archetype is not None:
        current["archetype"] = body.archetype
    if body.event_id is not None:
        with _db.session_scope() as session:
            ev = _db.get_event(session, body.event_id)
            if not ev:
                raise HTTPException(status_code=400, detail="Event not found")
            current["event_id"] = _db._event_id_str(body.event_id)
            current["event_name"] = event_display_name(ev.name, ev.store or "", ev.location or "")
            current["date"] = ev.date
            current["format_id"] = ev.format_id
    if body.commanders is not None:
        current["commanders"] = _normalize_commanders(body.commanders)
    if body.mainboard is not None:
        current["mainboard"] = _build_board(body.mainboard)
    if body.sideboard is not None:
        current["sideboard"] = _build_board(body.sideboard)
    # EDH: if no commander present, use first mainboard card as commander
    if (current.get("format_id") or "").upper() == "EDH" and not current.get("commanders") and current.get("mainboard"):
        current["commanders"] = [current["mainboard"][0]["card"]]
    # No duplicate player per event: another deck in same event cannot have the same player_id
    event_id = current.get("event_id")
    try:
        with _db.session_scope() as session:
            if "player_id" not in current:
                _resolve_deck_player(session, current)
            new_pid = current.get("player_id")
            if event_id and (body.player is not None or current.get("player")):
                if new_pid is not None:
                    event_decks = _db.get_decks_by_event(session, event_id)
                    for d in event_decks:
                        if d.get("deck_id") != deck_id and d.get("player_id") == new_pid:
                            raise HTTPException(
                                status_code=400,
                                detail="Player already in this event. Each player can only have one deck per event.",
                            )
            # Drop orphan Unnamed* PlayerRow: GET /players/id/{id} shows decks.player (denormalized), not
            # players.display_name, so renames looked correct while the placeholder row lingered.
            if (
                body.player is not None
                and prior_player_id is not None
                and new_pid is not None
                and prior_player_id != new_pid
                and _db.player_row_is_unnamed_placeholder(session, prior_player_id)
            ):
                _db.merge_players(
                    session,
                    prior_player_id,
                    new_pid,
                    canonical_name=(current.get("player") or "").strip() or None,
                )
                current["player_id"] = new_pid
                to_row = _db.get_player_by_id(session, new_pid)
                if to_row and (to_row.display_name or "").strip():
                    current["player"] = to_row.display_name
            if new_pid is not None:
                _db.sync_matchup_opponent_identity_for_deck(
                    session, deck_id, new_pid, current.get("player", "")
                )
            _db.upsert_deck(session, current, origin=current.get("origin", _db.ORIGIN_MTGTOP8))
        _load_decks_from_db()
        return {"deck_id": deck_id, "message": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Update deck failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/decks/{deck_id}", dependencies=[Depends(require_admin_or_event_edit_deck), Depends(require_database)])
def delete_deck_endpoint(deck_id: int):
    """Delete a single deck (admin-only)."""
    try:
        with _db.session_scope() as session:
            ok = _db.delete_deck(session, deck_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Deck not found")
        _load_decks_from_db()
        return {"deck_id": deck_id, "message": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Delete deck failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/decks/{deck_id}/matchups", dependencies=[Depends(require_admin_or_event_edit_deck), Depends(require_database)])
def get_deck_matchups(deck_id: int):
    """List matchups for a deck (admin or event-edit). Also returns opponent_reported_matchups:
    matchups others reported vs this deck's player (inverted: their win = our loss), for prepopulating the form."""
    deck = _get_deck_by_id(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    event_id = str(deck.get("event_id", ""))
    current_player = (deck.get("player") or "").strip()
    with _db.session_scope() as session:
        rows = _db.list_matchups_by_deck(session, deck_id)
        opponent_reported_matchups = []
        if event_id and current_player:
            # Use normalized current player so we match MatchupRow.opponent_player (stored normalized)
            current_player_norm = _normalize_player(current_player)
            reported_against_me = _db.list_matchups_reported_against_player(session, event_id, current_player_norm)
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
                # Use normalized name so it matches opponent dropdown (deck list uses normalized player)
                reporting_player = _normalize_player((r.get("reporting_player") or "").strip())
                if reporting_player and reporting_player != "(unknown)":
                    opponent_reported_matchups.append({
                        "opponent_player": reporting_player,
                        "result": inv_result,
                        "intentional_draw": _is_intentional_draw_result(res),
                        "round": r.get("round"),
                    })
    return {"matchups": rows, "opponent_reported_matchups": opponent_reported_matchups}


@router.put("/api/v1/decks/{deck_id}/matchups", dependencies=[Depends(require_admin_or_event_edit_deck), Depends(require_database)])
def update_deck_matchups(deck_id: int, body: AdminMatchupsBody):
    """Replace all matchups for a deck (admin or event-edit)."""
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    if len(body.matchups or []) > 12:
        raise HTTPException(status_code=400, detail="Maximum 12 matchups allowed")
    event_id = str(deck_dict.get("event_id", ""))
    if not event_id:
        raise HTTPException(status_code=400, detail="Deck has no event")
    with _db.session_scope() as session:
        matchup_rows = []
        seen_opponent_round: set[tuple[str, int | None]] = set()
        for m in body.matchups or []:
            result_raw = (m.result or "draw").strip().lower()
            if result_raw in ("bye", "drop"):
                # Bye and drop don't require an opponent; count as a round for validation
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
            round_num = getattr(m, "round", None)
            key = (opp_player, round_num)
            if key in seen_opponent_round:
                continue
            seen_opponent_round.add(key)
            opp_deck = _db.get_deck_by_event_and_player(session, event_id, opp_player)
            opp_deck_id = opp_deck.deck_id if opp_deck else None
            opp_archetype = _db.deck_archetype_for_deck_id(session, opp_deck_id)
            matchup_rows.append({
                "opponent_player": opp_player,
                "opponent_deck_id": opp_deck_id,
                "opponent_archetype": opp_archetype,
                "result": (m.result or "draw").strip(),
                "result_note": None,
                "round": round_num,
            })
        _db.upsert_matchups_for_deck(session, deck_id, matchup_rows)
    _load_decks_from_db()
    return {"deck_id": deck_id, "message": "Matchups updated"}


def _parse_moxfield_board(obj) -> list[dict]:
    """Turn Moxfield board (dict of id -> {quantity/qty, card: {name} or string}) into [{qty, card}]."""
    if not obj:
        return []
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            if not isinstance(v, dict):
                continue
            qty = v.get("quantity") or v.get("qty", 1) or 1
            try:
                qty = max(1, int(qty) if isinstance(qty, (int, float)) else 1)
            except (TypeError, ValueError):
                qty = 1
            card = v.get("card")
            if card is None:
                continue
            if isinstance(card, dict):
                name = (card.get("name") or card.get("cardName") or "").strip()
            else:
                name = str(card or "").strip()
            if name:
                out.append({"qty": qty, "card": name})
    return out


def _parse_moxfield_commanders(obj) -> list[str]:
    """Turn Moxfield commanders into list of card names."""
    entries = _parse_moxfield_board(obj)
    return [e["card"] for e in entries for _ in range(e["qty"])]


@router.post("/api/v1/decks/import-moxfield", dependencies=[Depends(require_admin)])
def import_moxfield_deck(body: ImportMoxfieldBody):
    """Fetch a public Moxfield deck by URL and return commanders, mainboard, sideboard for the editor."""
    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    match = re.search(r"moxfield\.com/decks/([a-zA-Z0-9_-]+)", url, re.IGNORECASE)
    if not match:
        match = re.match(r"^([a-zA-Z0-9_-]+)$", url.strip())
    deck_id = match.group(1) if match else None
    if not deck_id:
        raise HTTPException(status_code=400, detail="Invalid Moxfield URL or deck ID")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.moxfield.com/",
    }
    # Try v2 first; some environments get 403 (e.g. Cloudflare). v3 may work as fallback.
    urls_to_try = [
        f"https://api.moxfield.com/v2/decks/all/{deck_id}",
        f"https://api.moxfield.com/v3/decks/all/{deck_id}",
    ]
    data = None
    last_error = None
    for api_url in urls_to_try:
        try:
            r = requests.get(api_url, timeout=15, headers=headers)
            if r.status_code == 403:
                last_error = "Moxfield blocked the request (403)."
                continue
            r.raise_for_status()
            data = r.json()
            break
        except requests.RequestException as e:
            last_error = str(e)
            logger.warning("Moxfield fetch %s failed: %s", api_url, e)
            continue
    if data is None:
        logger.warning("Moxfield import failed for deck %s: %s", deck_id, last_error)
        raise HTTPException(
            status_code=502,
            detail="Could not fetch deck from Moxfield. The deck may be private, or Moxfield may be blocking requests. Try again later or paste the deck list manually (Export from Moxfield → Moxfield format).",
        )
    try:
        commanders = _parse_moxfield_commanders(data.get("commanders"))
        mainboard = _parse_moxfield_board(data.get("mainboard"))
        sideboard = _parse_moxfield_board(data.get("sideboard"))
        return {
            "commanders": commanders,
            "mainboard": mainboard,
            "sideboard": sideboard,
            "name": (data.get("name") or "").strip() or None,
            "format": (data.get("format") or "").strip() or None,
        }
    except (ValueError, TypeError) as e:
        logger.warning("Moxfield parse error for deck %s: %s", deck_id, e)
        raise HTTPException(status_code=502, detail="Invalid response from Moxfield")
