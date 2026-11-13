"""Change log: one row per data mutation — when, who, what.

"Who" is ``admin`` or a link, named by its type and label and never by its token. Handlers call
:func:`log` after their change has committed: the entry is written in its own short transaction and a
failure there is logged, never raised, so the log can never block or undo a legitimate edit (for
example a player's deck submission). A handler that fails records nothing.
"""

import logging
import time
from datetime import timedelta

from api import db as _db
from api.db import ChangeLogRow

logger = logging.getLogger(__name__)

CHANGE_LOG_MAX_AGE_DAYS = 180
SUMMARY_MAX_LENGTH = 512
ADMIN = "admin"
UNKNOWN = "unknown"

_PRUNE_EVERY_SECONDS = 3600
_last_prune: float | None = None  # monotonic time of the last prune; None = not yet in this process


def link_actor(link_row) -> str:
    """``link:<type>:<label>`` for an upload / feedback / event-edit link. Never includes the token."""
    link_type = getattr(link_row, "link_type", None) or "link"
    label = (getattr(link_row, "label", None) or "").strip() or "unlabelled"
    return f"link:{link_type}:{label}"


def actor_for_token(token: str | None) -> str:
    """Actor name for a link token sent by a client. An unknown token is not echoed back."""
    token = (token or "").strip()
    if not token:
        return UNKNOWN
    try:
        with _db.session_scope() as session:
            row = _db.get_upload_link(session, token)
            return link_actor(row) if row is not None else "link:unknown"
    except Exception:
        logger.warning("Could not resolve the link behind a change")
        return "link:unknown"


def acting_as(role: str | None, event_edit_token: str | None) -> str:
    """Actor for a handler guarded by ``require_admin_or_event_edit*`` (role is its return value)."""
    return ADMIN if role == ADMIN else actor_for_token(event_edit_token)


def _prune(session) -> None:
    global _last_prune
    now = time.monotonic()
    if _last_prune is not None and now - _last_prune < _PRUNE_EVERY_SECONDS:
        return
    _last_prune = now
    cutoff = _db.utcnow_naive() - timedelta(days=CHANGE_LOG_MAX_AGE_DAYS)
    session.query(ChangeLogRow).filter(ChangeLogRow.at < cutoff).delete(synchronize_session=False)


def record(
    session,
    *,
    actor: str,
    action: str,
    summary: str,
    event_id: str | int | None = None,
    deck_id: int | None = None,
) -> None:
    """Add one entry in the caller's session. Old entries are dropped at most once an hour."""
    session.add(
        ChangeLogRow(
            at=_db.utcnow_naive(),
            actor=(actor or UNKNOWN)[:128],
            action=action[:64],
            event_id=_db._event_id_str(event_id) if event_id not in (None, "") else None,
            deck_id=deck_id,
            summary=(summary or "")[:SUMMARY_MAX_LENGTH],
        )
    )
    session.flush()
    _prune(session)


def log(
    actor: str,
    action: str,
    summary: str,
    *,
    event_id: str | int | None = None,
    deck_id: int | None = None,
) -> None:
    """Write one entry in its own transaction, after the change it describes has committed.

    Never raises. Keep personal data (email addresses) and secrets (link tokens) out of ``summary``.
    """
    try:
        with _db.session_scope() as session:
            record(session, actor=actor, action=action, summary=summary, event_id=event_id, deck_id=deck_id)
    except Exception:
        logger.warning("Could not write change log entry for %s", action, exc_info=True)


def list_changes(session, *, event_id: str | None = None, limit: int = 200) -> list[dict]:
    """Newest first."""
    query = session.query(ChangeLogRow)
    if event_id:
        query = query.filter(ChangeLogRow.event_id == _db._event_id_str(event_id))
    return [
        {
            "id": r.id,
            "at": _db.iso_utc(r.at),
            "actor": r.actor,
            "action": r.action,
            "event_id": r.event_id,
            "deck_id": r.deck_id,
            "summary": r.summary,
        }
        for r in query.order_by(ChangeLogRow.id.desc()).limit(limit)
    ]
