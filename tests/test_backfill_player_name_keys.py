from sqlalchemy import text

from api.db import PlayerRow
from scripts.backfill_player_name_keys import backfill_name_keys


def test_backfill_fills_only_null_keys_and_is_idempotent(db_session_rollback):
    session = db_session_rollback
    p = PlayerRow(display_name="Zzscript Ñandú")
    session.add(p)
    session.flush()
    session.execute(text("UPDATE players SET name_key = NULL WHERE id = :i"), {"i": p.id})
    session.expire_all()
    changes = backfill_name_keys(session)
    assert (p.id, "Zzscript Ñandú", "zzscript nandu") in changes
    session.flush()
    assert session.get(PlayerRow, p.id).name_key == "zzscript nandu"
    assert backfill_name_keys(session) == []
