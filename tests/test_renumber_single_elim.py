"""scripts/renumber_single_elim_rounds.py: bracket rounds rebuilt from the decks' ranks."""

import pytest

from api.db import EventSnapshotRow, MatchupRow, event_row_to_dict, get_event
from scripts.renumber_single_elim_rounds import apply_renumber, plan_renumber
from tests._bracket_fixture import seed_bracket

EID = "test_renum_1"
BASE = 989900


def _scrambled(rnd, _winner, _loser):
    # Like the prod data: later rounds stored as round 1, first-round games pushed to round 3.
    return 1 if rnd > 1 else 3


def _rounds(session, ids):
    """{(deck_id, opponent_deck_id): round} for the event's rows."""
    session.expire_all()
    rows = session.query(MatchupRow).filter(MatchupRow.deck_id.in_(ids)).all()
    return {(r.deck_id, r.opponent_deck_id): r.round for r in rows}


def test_renumber_fixes_scrambled_rounds(db_session_rollback):
    session = db_session_rollback
    ids = seed_bracket(session, EID, 8, BASE, structure=None, stored_round=_scrambled)
    plan = plan_renumber(session, EID, 8)
    assert plan.errors == []
    assert apply_renumber(session, EID, 8, plan) == len(plan.changes) > 0
    rounds = _rounds(session, ids)
    # Quarterfinals: seeds 0-4, 1-5, 2-6, 3-7; semifinals 0-2, 1-3; final 0-1. Both sides agree.
    for a, b, expected in [(0, 4, 1), (1, 5, 1), (2, 6, 1), (3, 7, 1), (0, 2, 2), (1, 3, 2), (0, 1, 3)]:
        assert rounds[(ids[a], ids[b])] == expected
        assert rounds[(ids[b], ids[a])] == expected
    d = event_row_to_dict(get_event(session, EID))
    assert (d["structure"], d["bracket_size"]) == ("single_elimination", 8)
    assert session.query(EventSnapshotRow).filter(EventSnapshotRow.event_id == EID).count() == 1


def test_renumber_refuses_contradictions(db_session_rollback):
    session = db_session_rollback
    ids = seed_bracket(session, EID, 8, BASE, structure=None, stored_round=_scrambled)
    for row in session.query(MatchupRow).filter(MatchupRow.deck_id.in_([ids[0], ids[1]]),
                                                MatchupRow.opponent_deck_id.in_([ids[0], ids[1]])):
        row.result = "draw"
    session.flush()
    before = _rounds(session, ids)
    plan = plan_renumber(session, EID, 8)
    assert plan.errors
    with pytest.raises(ValueError):
        apply_renumber(session, EID, 8, plan)
    assert _rounds(session, ids) == before
    assert event_row_to_dict(get_event(session, EID))["structure"] == "swiss"


def test_renumber_refuses_more_matches_than_rank_allows(db_session_rollback):
    from api.db import DeckRow

    session = db_session_rollback
    ids = seed_bracket(session, EID, 8, BASE, structure=None)
    session.get(DeckRow, ids[2]).rank = "5-8"  # a semifinalist recorded as a quarterfinal loser
    session.flush()
    plan = plan_renumber(session, EID, 8)
    assert plan.errors


def test_renumber_is_idempotent(db_session_rollback):
    session = db_session_rollback
    seed_bracket(session, EID, 8, BASE, structure=None, stored_round=_scrambled)
    apply_renumber(session, EID, 8, plan_renumber(session, EID, 8))
    assert plan_renumber(session, EID, 8).changes == []


def test_second_apply_writes_nothing(db_session_rollback):
    """A second run on an already-fixed event takes no snapshot and does not touch the event."""
    from scripts.renumber_single_elim_rounds import needs_renumber

    session = db_session_rollback
    seed_bracket(session, EID, 8, BASE, structure=None, stored_round=_scrambled)
    plan = plan_renumber(session, EID, 8)
    assert needs_renumber(session, EID, 8, plan)
    apply_renumber(session, EID, 8, plan)
    snapshots = session.query(EventSnapshotRow).filter(EventSnapshotRow.event_id == EID).count()
    again = plan_renumber(session, EID, 8)
    assert not needs_renumber(session, EID, 8, again)
    assert apply_renumber(session, EID, 8, again) == 0
    assert session.query(EventSnapshotRow).filter(EventSnapshotRow.event_id == EID).count() == snapshots


def test_already_renumbered_rounds_but_swiss_event_still_needs_the_structure(db_session_rollback):
    from scripts.renumber_single_elim_rounds import needs_renumber

    session = db_session_rollback
    seed_bracket(session, EID, 8, BASE, structure=None)  # rounds already right, structure still Swiss
    plan = plan_renumber(session, EID, 8)
    assert plan.changes == []
    assert needs_renumber(session, EID, 8, plan)
