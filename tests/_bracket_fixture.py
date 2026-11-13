"""Seed a complete single-elimination bracket in the test database (both sides of every match stored)."""

from api.db import DeckRow, MatchupRow, create_event, upsert_deck


def rank_for_seed(seed: int, bracket_size: int) -> str:
    """Seed 0 wins; every other seed's rank band follows from the round it loses in (see bracket_matches)."""
    if seed == 0:
        return "1"
    upper = 1
    while upper <= seed:
        upper *= 2
    return "2" if upper == 2 else f"{upper // 2 + 1}-{upper}"


def bracket_matches(bracket_size: int) -> list[tuple[int, int, int]]:
    """``(round, winner_seed, loser_seed)``: each round pairs seed i with seed i + half; the lower seed wins."""
    out = []
    remaining = list(range(bracket_size))
    rnd = 1
    while len(remaining) > 1:
        half = len(remaining) // 2
        out += [(rnd, remaining[i], remaining[i + half]) for i in range(half)]
        remaining = remaining[:half]
        rnd += 1
    return out


def seed_bracket(
    session,
    event_id: str,
    bracket_size: int,
    base_deck_id: int,
    *,
    structure: str | None = "single_elimination",
    player_count: int | None = None,
    skip: frozenset = frozenset(),
    stored_round=None,
    winner_result: str = "win",
    loser_result: str = "loss",
) -> list[int]:
    """Create the event, one ranked deck per seed and every match. Returns deck ids by seed.

    ``skip``: ``(winner_seed, loser_seed)`` pairs not stored. ``stored_round(round, winner, loser)``: the round
    number written (default: the real round)."""
    create_event(
        session, event_name="Bracket", date="01/01/25", format_id="ST", origin="manual", event_id=event_id,
        player_count=player_count or bracket_size, structure=structure,
        bracket_size=bracket_size if structure == "single_elimination" else None,
    )
    deck_ids = []
    for seed in range(bracket_size):
        deck_id = base_deck_id + seed
        upsert_deck(session, {
            "deck_id": deck_id, "event_id": event_id, "format_id": "ST", "name": f"Deck {deck_id}",
            "player": f"Seed {event_id} {seed}", "event_name": "Bracket", "date": "01/01/25",
            "rank": rank_for_seed(seed, bracket_size), "player_count": player_count or bracket_size,
            "mainboard": [], "sideboard": [], "commanders": [], "archetype": None,
        }, origin="manual")
        deck_ids.append(deck_id)
    session.flush()
    rows = {r.deck_id: r for r in session.query(DeckRow).filter(DeckRow.deck_id.in_(deck_ids))}
    for rnd, w, loser in bracket_matches(bracket_size):
        if (w, loser) in skip:
            continue
        stored = stored_round(rnd, w, loser) if stored_round else rnd
        dw, dl = rows[deck_ids[w]], rows[deck_ids[loser]]
        session.add(MatchupRow(deck_id=dw.deck_id, opponent_player_id=dl.player_id, opponent_player=dl.player,
                               opponent_deck_id=dl.deck_id, result=winner_result, round=stored))
        session.add(MatchupRow(deck_id=dl.deck_id, opponent_player_id=dw.player_id, opponent_player=dw.player,
                               opponent_deck_id=dw.deck_id, result=loser_result, round=stored))
    session.flush()
    return deck_ids
