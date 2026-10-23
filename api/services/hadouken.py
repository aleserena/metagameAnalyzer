"""Complete an existing event (usually scraped from MTGTop8) with standings and matchups from a Hadouken page.

MTGTop8 only lists the top decks; the Hadouken league page lists every player and every round. Preview
matches each Hadouken player to a deck of the event (or proposes a new blank deck); apply creates the
missing decks and writes the round results through the normal matchup path (both sides stored).
"""

from api import db as _db
from api.helpers import _rank_sort_value
from sqlalchemy import and_, or_
from src.mtgtop8.hadouken import HadoukenEvent, pairing_results
from src.mtgtop8.scraper import event_display_name

# How a Hadouken player was matched to an event deck (shown in the preview).
MATCH_PLAYER = "player"  # same player (alias, exact or accent-insensitive name)
MATCH_REORDERED = "reordered"  # same words in a different order ("Masino Julian" vs "Julián Masino")
MATCH_PARTIAL = "partial"  # one name contains the other ("Juan Manuel Perea" vs "Juan Perea") - verify
MATCH_NONE = "none"  # no deck: a blank deck will be created


def _name_tokens(name: str) -> list[str]:
    return sorted(_db._normalize_name_for_lookup(name).split())


def suggest_deck_matches(
    names: list[str],
    decks: list[dict],
    resolved_player_ids: dict[str, int | None],
) -> dict[str, tuple[int | None, str]]:
    """Map each Hadouken name to (deck_id, match kind). Each deck is used at most once.

    ``decks`` are the event's decks (deck_id, player, player_id); ``resolved_player_ids`` is the result of
    resolving each name against players/aliases. Stronger match kinds are assigned first.
    """
    result: dict[str, tuple[int | None, str]] = {n: (None, MATCH_NONE) for n in names}
    used: set[int] = set()
    by_player_id = {d["player_id"]: d for d in decks if d.get("player_id") is not None}

    def assign(name: str, deck: dict, kind: str) -> None:
        result[name] = (deck["deck_id"], kind)
        used.add(deck["deck_id"])

    for n in names:
        deck = by_player_id.get(resolved_player_ids.get(n))
        if deck and deck["deck_id"] not in used:
            assign(n, deck, MATCH_PLAYER)

    for kind in (MATCH_REORDERED, MATCH_PARTIAL):
        for n in names:
            if result[n][0] is not None:
                continue
            tokens = set(_name_tokens(n))
            candidates = []
            for d in decks:
                if d["deck_id"] in used:
                    continue
                deck_tokens = set(_name_tokens(d.get("player") or ""))
                if not tokens or not deck_tokens:
                    continue
                if kind == MATCH_REORDERED and tokens == deck_tokens:
                    candidates.append(d)
                elif kind == MATCH_PARTIAL and min(len(tokens), len(deck_tokens)) >= 2 and (
                    tokens <= deck_tokens or deck_tokens <= tokens
                ):
                    candidates.append(d)
            if len(candidates) == 1:  # ambiguous partial matches are left for the admin
                assign(n, candidates[0], kind)
    return result


def _event_or_error(session, event_id: str):
    ev = _db.get_event(session, event_id)
    if not ev:
        raise LookupError("Event not found")
    return ev


class _PlayerLookup:
    """In-memory version of ``db.resolve_name_to_player_id`` (alias, exact name, front face, accent/case-insensitive).

    Loads players and aliases once: resolving each name with the per-name DB helper scans the players table
    every time, which made a 26-player import take minutes against a remote database.
    """

    def __init__(self, session):
        players = session.query(_db.PlayerRow.id, _db.PlayerRow.display_name).all()
        self.display = {pid: (name or "") for pid, name in players}
        self.by_name = {(name or ""): pid for pid, name in players}
        self.by_norm: dict[str, int] = {}
        for pid, name in sorted(players):  # lowest id wins, like the DB helper's first match
            self.by_norm.setdefault(_db._normalize_name_for_lookup(name or ""), pid)
        self.aliases = {a: pid for a, pid in session.query(_db.PlayerAliasRow.alias, _db.PlayerAliasRow.player_id).all()}

    def resolve(self, name: str) -> int | None:
        n = (name or "").strip()
        if not n or n in ("Bye", "(drop)"):
            return None
        if n in self.aliases and self.aliases[n] in self.display:
            return self.aliases[n]
        canonical = _db._front_face_name(n)
        for candidate in (n, canonical):
            if candidate in self.by_name:
                return self.by_name[candidate]
        return self.by_norm.get(_db._normalize_name_for_lookup(canonical))


def _existing_results(session, deck_ids: set[int]) -> dict[tuple[int, int, int | None], str]:
    rows = session.query(_db.MatchupRow).filter(_db.MatchupRow.deck_id.in_(deck_ids)).all() if deck_ids else []
    return {(r.deck_id, r.opponent_deck_id, r.round): r.result for r in rows if r.opponent_deck_id is not None}


def _require_same_date(ev, hev: HadoukenEvent) -> None:
    """A Hadouken page can only complete the event played the same day."""
    if not hev.date:
        raise ValueError("Could not read the date of the Hadouken tournament.")
    if (ev.date or "").strip() != hev.date:
        raise ValueError(
            f"Dates do not match: this event is {ev.date or '(no date)'}, the Hadouken tournament is {hev.date}."
        )


def assign_places_by_points(hev: HadoukenEvent) -> dict[str, int]:
    """Re-number places by tournament points (most points first). Ties keep Hadouken's order, which
    reflects its tiebreakers, so places stay unique. Returns Hadouken's original place per player."""
    original = {s.player: s.rank for s in hev.standings}
    for place, s in enumerate(sorted(hev.standings, key=lambda s: (-s.points, s.rank)), start=1):
        s.rank = place
    return original


def apply_standings_edits(hev: HadoukenEvent, edits: dict[str, dict]) -> None:
    """Overwrite place/points of Hadouken standings with the admin's edits (name -> {rank, points})."""
    by_name = {s.player: s for s in hev.standings}
    unknown = set(edits) - set(by_name)
    if unknown:
        raise ValueError(f"Players not on the Hadouken page: {', '.join(sorted(unknown))}")
    for name, edit in edits.items():
        if edit.get("rank") is not None:
            by_name[name].rank = int(edit["rank"])
        if edit.get("points") is not None:
            by_name[name].points = int(edit["points"])
    ranks = [s.rank for s in hev.standings]
    if any(r < 1 for r in ranks):
        raise ValueError("Places must be 1 or higher")
    if len(ranks) != len(set(ranks)):
        raise ValueError("Each place can only be used once")
    if any(s.points < 0 for s in hev.standings):
        raise ValueError("Points cannot be negative")


def build_preview(session, event_id: str, hev: HadoukenEvent) -> dict:
    """Read-only: what applying this Hadouken page to the event would do."""
    ev = _event_or_error(session, event_id)
    decks = _db.get_decks_by_event(session, event_id)
    _require_same_date(ev, hev)
    names = [s.player for s in hev.standings]
    lookup = _PlayerLookup(session)
    resolved = {n: lookup.resolve(n) for n in names}
    suggestions = suggest_deck_matches(names, decks, resolved)
    deck_by_id = {d["deck_id"]: d for d in decks}

    warnings = []
    if hev.format_id and ev.format_id and hev.format_id != ev.format_id:
        warnings.append(f"Format differs: event is {ev.format_id}, Hadouken page is {hev.format_id}.")
    if len(hev.standings) < len(decks):
        warnings.append(f"Event has {len(decks)} decks but the Hadouken page lists {len(hev.standings)} players.")

    hadouken_ranks = assign_places_by_points(hev)
    players = []
    for s in sorted(hev.standings, key=lambda s: s.rank):
        deck_id, kind = suggestions[s.player]
        players.append(
            {
                "name": s.player,
                "rank": s.rank,
                "hadouken_rank": hadouken_ranks[s.player],
                "points": s.points,
                "wins": s.wins,
                "losses": s.losses,
                "draws": s.draws,
                "deck_id": deck_id,
                "match": kind,
            }
        )

    # Results that would replace different results already stored (e.g. reported via feedback links).
    existing = _existing_results(session, {d for d, _ in suggestions.values() if d is not None})
    pairings, conflicts = [], []
    for p in hev.pairings:
        r1, r2 = pairing_results(p)
        pairings.append(
            {"round": p.round, "player1": p.player1, "player2": p.player2,
             "games1": p.games1, "games2": p.games2, "result1": r1, "result2": r2}
        )
        d1, d2 = suggestions[p.player1][0], suggestions[p.player2][0]
        old = existing.get((d1, d2, p.round)) if d1 is not None and d2 is not None else None
        if old is not None and old != r1:
            conflicts.append({"round": p.round, "player1": p.player1, "player2": p.player2, "existing": old, "hadouken": r1})

    return {
        "hadouken": {
            "url": hev.url, "name": hev.name, "date": hev.date, "format_id": hev.format_id,
            "store": hev.store, "player_count": hev.player_count,
        },
        "event": {"event_id": ev.event_id, "event_name": ev.name, "date": ev.date,
                  "format_id": ev.format_id, "player_count": ev.player_count or 0},
        "warnings": warnings,
        "players": players,
        "decks": [
            {"deck_id": d["deck_id"], "player": d.get("player") or "", "rank": d.get("rank") or "",
             "archetype": d.get("archetype") or ""}
            for d in sorted(decks, key=lambda d: (_rank_sort_value(d.get("rank") or ""), d["deck_id"]))
        ],
        "unmatched_deck_ids": sorted(set(deck_by_id) - {d for d, _ in suggestions.values() if d is not None}),
        "pairings": pairings,
        "conflicts": conflicts,
        "existing_matchup_count": len(existing),
    }


def apply_import(
    session,
    event_id: str,
    hev: HadoukenEvent,
    player_map: dict[str, int | None],
    standings_edits: dict[str, dict] | None = None,
) -> dict:
    """Create missing decks, write all Hadouken round results and raise the event's player count.

    ``player_map``: Hadouken name -> event deck_id, or None to create a blank deck for that player.
    Names missing from the map are treated as None. ``standings_edits``: name -> {rank, points} corrections
    made in the preview (places are used as the rank of decks without one). Raises ValueError on invalid input.
    """
    ev = _event_or_error(session, event_id)
    _require_same_date(ev, hev)
    assign_places_by_points(hev)  # same starting places as the preview; edits are relative to these
    apply_standings_edits(hev, standings_edits or {})
    decks = _db.get_decks_by_event(session, event_id)
    deck_by_id = {d["deck_id"]: d for d in decks}
    names = [s.player for s in hev.standings]
    unknown = set(player_map) - set(names)
    if unknown:
        raise ValueError(f"Players not on the Hadouken page: {', '.join(sorted(unknown))}")

    chosen = [d for d in (player_map.get(n) for n in names) if d is not None]
    if len(chosen) != len(set(chosen)):
        raise ValueError("A deck was assigned to more than one Hadouken player")
    bad = [d for d in chosen if d not in deck_by_id]
    if bad:
        raise ValueError(f"Decks not in this event: {bad}")

    # Everything below is written in bulk: a few queries instead of hundreds of per-row round trips.
    lookup = _PlayerLookup(session)
    used_player_ids = {d["player_id"] for d in decks}
    event_name = event_display_name(ev.name, ev.store or "", ev.location or "")
    player_count = max(ev.player_count or 0, hev.player_count, len(names))
    rank_by_name = {s.player: s.rank for s in hev.standings}
    name_to_deck: dict[str, int] = {}
    aliases_added = 0

    # Matched players: remember the Hadouken spelling so the next import matches automatically, unless it
    # already names some player (an alias would silently redirect that player's results).
    for name in names:
        deck_id = player_map.get(name)
        if deck_id is None:
            continue
        name_to_deck[name] = deck_id
        if lookup.resolve(name) is None:
            session.add(_db.PlayerAliasRow(alias=name, player_id=deck_by_id[deck_id]["player_id"]))
            lookup.aliases[name] = deck_by_id[deck_id]["player_id"]
            aliases_added += 1

    # Unmatched players: existing player (by name/alias) or a new one, then a blank deck each.
    new_names = [n for n in names if player_map.get(n) is None]
    new_players: dict[str, _db.PlayerRow] = {}
    for name in new_names:
        if lookup.resolve(name) is None:
            new_players[name] = _db.PlayerRow(display_name=name)
    session.add_all(new_players.values())
    session.flush()  # assigns ids to the new players
    next_deck_id = _db.next_manual_deck_id(session)
    for name in new_names:
        pid = new_players[name].id if name in new_players else lookup.resolve(name)
        display = name if name in new_players else lookup.display[pid]
        if pid in used_player_ids:
            raise ValueError(f"{name} already has a deck in this event; assign it instead of creating a new one")
        used_player_ids.add(pid)
        deck_id = next_deck_id
        next_deck_id += 1
        deck = {
            "deck_id": deck_id,
            "event_id": event_id,
            "event_name": event_name,
            "date": ev.date,
            "format_id": ev.format_id,
            "name": "Unnamed",
            "player": display,
            "player_id": pid,
            "rank": str(rank_by_name[name]),
            "player_count": player_count,
            "commanders": [],
            "mainboard": [],
            "sideboard": [],
        }
        session.add(_db.dict_to_deck_row(deck, origin=_db.ORIGIN_MANUAL))
        name_to_deck[name] = deck_id
        deck_by_id[deck_id] = {"deck_id": deck_id, "player": display, "player_id": pid, "archetype": None}

    # Matchups: same outcome as upsert_matchups_for_deck for every involved deck (replace each deck's
    # results, mirrored rows and orphan reports against its player), with both sides written at once.
    deck_ids = list(name_to_deck.values())
    player_ids = [deck_by_id[d]["player_id"] for d in deck_ids]
    event_deck_ids = list(deck_by_id)
    session.flush()
    session.query(_db.MatchupRow).filter(
        or_(
            _db.MatchupRow.deck_id.in_(deck_ids),
            _db.MatchupRow.opponent_deck_id.in_(deck_ids),
            and_(_db.MatchupRow.deck_id.in_(event_deck_ids), _db.MatchupRow.opponent_player_id.in_(player_ids)),
        )
    ).delete(synchronize_session=False)
    rows = []
    for p in hev.pairings:
        if p.player1 not in name_to_deck or p.player2 not in name_to_deck:
            continue
        r1, r2 = pairing_results(p)
        d1, d2 = name_to_deck[p.player1], name_to_deck[p.player2]
        for me, opp, result, note in ((d1, d2, r1, f"{p.games1}-{p.games2}"), (d2, d1, r2, f"{p.games2}-{p.games1}")):
            rows.append(
                _db.MatchupRow(
                    deck_id=me,
                    opponent_player_id=deck_by_id[opp]["player_id"],
                    opponent_player=deck_by_id[opp]["player"],
                    opponent_deck_id=opp,
                    opponent_archetype=_db._normalize_archetype_or_commander_display(deck_by_id[opp].get("archetype")),
                    result=result,
                    result_note=note,
                    round=p.round,
                )
            )
    session.add_all(rows)

    # Matched decks without a rank get their Hadouken place (MTGTop8 ranks are kept).
    rank_by_deck = {name_to_deck[n]: rank_by_name[n] for n in names if player_map.get(n) is not None}
    if rank_by_deck:
        for row in session.query(_db.DeckRow).filter(_db.DeckRow.deck_id.in_(list(rank_by_deck))).all():
            if not (row.rank or "").strip():
                row.rank = str(rank_by_deck[row.deck_id])

    created = len(new_names)
    if player_count != (ev.player_count or 0):
        _db.update_event(session, event_id, player_count=player_count)

    return {
        "event_id": event_id,
        "decks_created": created,
        "decks_matched": len(chosen),
        "matches_imported": len(hev.pairings),
        "aliases_added": aliases_added,
        "player_count": player_count,
    }
