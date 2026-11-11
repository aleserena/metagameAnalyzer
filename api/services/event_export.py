"""Build the JSON export payload for a single event."""

from api import db as _db
from api.schemas.events import EventExportData, EventResponse


def build_event_export(session, event_id: str, *, include_emails: bool) -> EventExportData | None:
    """Return the export for ``event_id`` or ``None`` when the event does not exist.

    Player emails are only collected when ``include_emails`` is true.
    """
    row = _db.get_event(session, event_id)
    if not row:
        return None
    event_dict = _db.event_row_to_dict(row)
    decks = _db.get_decks_by_event(session, event_id)

    # Collect matchups for all decks in this event (single batched query).
    deck_ids = [d.get("deck_id") for d in decks if d.get("deck_id") is not None]
    matchups = list(_db.list_matchups_by_decks(session, deck_ids))

    # Emails only for players in this event. Batch by player_id (resolving by
    # display name does a per-name full-table scan).
    player_emails: dict[str, str] = {}
    if include_emails:
        pid_to_name = {
            d.get("player_id"): (d.get("player") or "").strip()
            for d in decks
            if d.get("player_id") is not None and (d.get("player") or "").strip()
        }
        if pid_to_name:
            email_by_id = _db.get_emails_for_player_ids(session, list(pid_to_name))
            player_emails = {
                pid_to_name[pid]: email for pid, email in email_by_id.items() if pid in pid_to_name
            }

    # Distinct player_ids from decks and matchups for the players array
    player_ids: set[int] = set()
    for d in decks:
        pid = d.get("player_id")
        if pid is not None:
            player_ids.add(pid)
    for m in matchups:
        pid = m.get("opponent_player_id")
        if pid is not None:
            player_ids.add(pid)
    player_rows = _db.get_players_by_ids(session, list(player_ids))
    players_list: list[dict] = []
    for pid in sorted(player_ids):
        prow = player_rows.get(pid)
        if prow:
            players_list.append({"id": prow.id, "display_name": prow.display_name or ""})

    return EventExportData(
        schema_version=1,
        event=EventResponse(**event_dict),
        decks=decks,
        matchups=matchups,
        player_emails=player_emails,
        players=players_list,
    )
