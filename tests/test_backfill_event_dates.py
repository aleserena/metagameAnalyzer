from datetime import date

from sqlalchemy import text

from api.dates import parse_ddmmyy
from api.db import DeckRow, EventRow, PlayerRow, create_event
from scripts.backfill_event_dates import sync_event_dates

_TEXTS = ["05/03/25", "06/03/25", "07/03/2025", "garbage", "08/03/25"]


def _seed(session):
    player = PlayerRow(display_name="Zzbfed Player")
    session.add(player)
    session.flush()
    for i, d in enumerate(_TEXTS):
        create_event(session, "Bf", d, "EDH", event_id=f"test_bfed_{i}", player_count=1)
        session.add(
            DeckRow(
                deck_id=980000 + i,
                event_id=f"test_bfed_{i}",
                player_id=player.id,
                date=d,
                commanders=[],
                mainboard=[],
                sideboard=[],
            )
        )
    session.flush()
    # 0: NULL, 1: stale (wrong date), 2: correct, 3: unparseable text but a value, 4: correct
    stale = {0: None, 1: date(2020, 1, 1), 2: date(2025, 3, 7), 3: date(2024, 4, 4), 4: date(2025, 3, 8)}
    for i, value in stale.items():
        session.execute(
            text("UPDATE events SET event_date = :v WHERE event_id = :e"), {"v": value, "e": f"test_bfed_{i}"}
        )
        session.execute(text("UPDATE decks SET event_date = :v WHERE deck_id = :d"), {"v": value, "d": 980000 + i})
    session.expire_all()


def _assert_all_match(session):
    session.expire_all()
    for i, d in enumerate(_TEXTS):
        assert session.get(EventRow, f"test_bfed_{i}").event_date == parse_ddmmyy(d)
        assert session.query(DeckRow).filter_by(deck_id=980000 + i).one().event_date == parse_ddmmyy(d)


def test_sync_event_dates_fixes_null_stale_and_unparseable_rows(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    counts = sync_event_dates(session, apply=True)
    assert counts["events"] >= 3
    assert counts["decks"] >= 3
    _assert_all_match(session)


def test_sync_event_dates_dry_run_changes_nothing_and_rerun_is_clean(db_session_rollback):
    session = db_session_rollback
    _seed(session)
    dry = sync_event_dates(session, apply=False)
    assert dry["events"] >= 3
    session.expire_all()
    assert session.get(EventRow, "test_bfed_0").event_date is None
    assert session.get(EventRow, "test_bfed_3").event_date == date(2024, 4, 4)
    applied = sync_event_dates(session, apply=True)
    assert applied == dry
    assert sync_event_dates(session, apply=True) == {"events": 0, "decks": 0}
