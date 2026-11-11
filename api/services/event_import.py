"""Import a manual event from an exported JSON payload."""

from api import db as _db
from api.db import DeckRow, MatchupRow
from api.schemas.events import EventExportData
from api.state import _resolve_deck_player


def import_event_payload(session, body: EventExportData) -> dict:
    """Create a new manual event with its decks, matchups and player emails.

    Returns ``{"event_id", "deck_count", "matchup_count"}``. Raises ``ValueError``
    for a deck without an integer ``deck_id``.
    """
    # Create new manual event with a fresh ID
    new_event_id = _db.next_manual_event_id(session)
    ev = body.event
    row = _db.create_event(
        session,
        event_name=(ev.event_name or "").strip() or "Unnamed",
        date=(ev.date or "").strip(),
        format_id=(ev.format_id or "").strip() or "EDH",
        origin=_db.ORIGIN_MANUAL,
        event_id=new_event_id,
        player_count=ev.player_count or 0,
        store=(ev.store or "").strip(),
        location=(ev.location or "").strip(),
    )
    event_dict = _db.event_row_to_dict(row)

    # Map old deck_ids -> new manual deck_ids
    decks_data = body.decks or []
    deck_id_map: dict[int, int] = {}
    next_deck_id = _db.next_manual_deck_id(session)
    for deck_dict_raw in decks_data:
        if "deck_id" not in deck_dict_raw:
            raise ValueError("Each deck must include a 'deck_id' field")
        try:
            old_deck_id = int(deck_dict_raw.get("deck_id"))
        except Exception:
            raise ValueError("Each deck 'deck_id' must be an integer")
        new_deck_id = next_deck_id
        next_deck_id += 1
        deck_id_map[old_deck_id] = new_deck_id

        deck_data = dict(deck_dict_raw)
        deck_data["deck_id"] = new_deck_id
        deck_data["event_id"] = new_event_id
        deck_data["event_name"] = event_dict.get("event_name") or deck_data.get("event_name") or ""
        deck_data["date"] = event_dict.get("date") or deck_data.get("date") or ""
        if not deck_data.get("format_id"):
            deck_data["format_id"] = event_dict.get("format_id", "") or "EDH"

        _resolve_deck_player(session, deck_data)
        deck_row = _db.dict_to_deck_row(deck_data, origin=_db.ORIGIN_MANUAL)
        session.add(deck_row)

    # Decks must exist in the DB before matchups reference them.
    session.flush()
    # Decks carry the event's display name (with store/location), like every other path.
    _db.sync_decks_with_event(session, new_event_id)
    new_deck_player_ids = {
        r.deck_id: r.player_id
        for r in session.query(DeckRow.deck_id, DeckRow.player_id).filter(DeckRow.event_id == new_event_id)
    }

    # Reproduce the exported matchup rows exactly (both sides are already in the export),
    # remapping deck IDs. No inverse rows are generated.
    matchup_count = 0
    seen: set[tuple[int, object, str]] = set()
    for m_raw in body.matchups or []:
        try:
            new_deck_id = deck_id_map.get(int(m_raw.get("deck_id")))
        except (TypeError, ValueError):
            continue
        if new_deck_id is None:
            continue

        new_opp_id = None
        opp_old = m_raw.get("opponent_deck_id")
        if opp_old is not None:
            try:
                new_opp_id = deck_id_map.get(int(opp_old))
            except (TypeError, ValueError):
                new_opp_id = None

        result = (m_raw.get("result") or "loss").strip() or "loss"
        opponent_player = (m_raw.get("opponent_player") or "").strip()
        opp_pid = None
        if new_opp_id is not None:
            opp_pid = new_deck_player_ids.get(new_opp_id)
        elif opponent_player and opponent_player not in ("Bye", "(drop)"):
            opp_pid, disp = _db.resolve_name_to_player_id(session, opponent_player)
            if opp_pid is None:
                opp_pid, disp = _db.get_or_create_player(session, opponent_player)
            opponent_player = disp or opponent_player
        opponent_player = opponent_player or "Bye"

        round_num = m_raw.get("round")
        key = (new_deck_id, round_num, opponent_player)
        if key in seen:
            continue
        seen.add(key)

        oa_in = m_raw.get("opponent_archetype")
        oa_norm = None
        if oa_in is not None and str(oa_in).strip():
            oa_norm = _db._normalize_archetype_or_commander_display(str(oa_in))
        session.add(
            MatchupRow(
                deck_id=new_deck_id,
                opponent_player_id=opp_pid,
                opponent_player=opponent_player,
                opponent_deck_id=new_opp_id,
                opponent_archetype=oa_norm,
                result=result,
                result_note=(m_raw.get("result_note") or "").strip() or None,
                round=round_num,
            )
        )
        matchup_count += 1

    # Restore player emails for players in this event
    for player, email in (body.player_emails or {}).items():
        _db.set_player_email(session, player, email)

    return {
        "event_id": event_dict["event_id"],
        "deck_count": len(decks_data),
        "matchup_count": matchup_count,
    }
