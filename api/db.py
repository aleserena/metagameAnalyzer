"""Database layer: SQLAlchemy models, engine, session, and repository helpers.

When DATABASE_URL is set, all persistence uses PostgreSQL. When unset, the API
falls back to in-memory + file storage (see api/main.py).
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger(__name__)

# Manual event IDs use prefix "m" + number (m1, m2, ...) to distinguish from scraped numeric IDs
MANUAL_EVENT_ID_PREFIX = "m"
# Manual deck IDs start at 2_000_000 to avoid clashing with MTGTop8 deck IDs
MANUAL_DECK_ID_START = 2_000_000

ORIGIN_MTGTOP8 = "mtgtop8"
ORIGIN_MANUAL = "manual"

Base = declarative_base()


class EventRow(Base):
    __tablename__ = "events"
    event_id = Column(String(32), primary_key=True)  # scraped: "80454"; manual: "m1", "m2"
    origin = Column(String(32), nullable=False, default=ORIGIN_MTGTOP8)  # 'mtgtop8' | 'manual'
    format_id = Column(String(32), nullable=False, default="")
    name = Column(String(512), nullable=False, default="")
    store = Column(String(512), nullable=False, default="")
    location = Column(String(512), nullable=False, default="")
    date = Column(String(32), nullable=False, default="")  # DD/MM/YY
    player_count = Column(Integer, nullable=False, default=0)  # number of players in the event


class DeckRow(Base):
    __tablename__ = "decks"
    deck_id = Column(Integer, primary_key=True)
    event_id = Column(String(32), nullable=False)  # matches events.event_id (string)
    origin = Column(String(32), nullable=False, default=ORIGIN_MTGTOP8)
    format_id = Column(String(32), nullable=False, default="")
    name = Column(String(512), nullable=False, default="")
    player = Column(String(512), nullable=False, default="")
    event_name = Column(String(512), nullable=False, default="")
    date = Column(String(32), nullable=False, default="")
    rank = Column(String(32), nullable=False, default="")
    player_count = Column(Integer, nullable=False, default=0)
    commanders = Column(JSONB, nullable=False)  # list of strings
    archetype = Column(String(512), nullable=True)
    mainboard = Column(JSONB, nullable=False)  # [{"qty": int, "card": str}, ...]
    sideboard = Column(JSONB, nullable=False)
    # deck_id is globally unique: MTGTop8 use site IDs; manual use MANUAL_DECK_ID_START+


class PlayerAliasRow(Base):
    __tablename__ = "player_aliases"
    alias = Column(Text, primary_key=True)
    canonical = Column(Text, nullable=False)


class SettingsRow(Base):
    __tablename__ = "settings"
    key = Column(String(128), primary_key=True)
    value = Column(JSONB, nullable=False)


LINK_TYPE_DECK_UPLOAD = "deck_upload"
LINK_TYPE_DECK_UPDATE = "deck_update"
LINK_TYPE_EVENT_EDIT = "event_edit"
LINK_TYPE_FEEDBACK = "feedback"


class PlayerEmailRow(Base):
    __tablename__ = "player_emails"
    player = Column(Text, primary_key=True)
    email = Column(Text, nullable=False)


class MatchupRow(Base):
    __tablename__ = "matchups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    deck_id = Column(Integer, nullable=False)
    opponent_player = Column(String(512), nullable=False)
    opponent_deck_id = Column(Integer, nullable=True)
    opponent_archetype = Column(String(512), nullable=True)
    result = Column(String(32), nullable=False)  # win | loss | draw | intentional_draw
    result_note = Column(String(512), nullable=True)
    round = Column(Integer, nullable=True)


class EventUploadLinkRow(Base):
    __tablename__ = "event_upload_links"
    token = Column(String(64), primary_key=True)
    event_id = Column(String(32), nullable=False)
    deck_id = Column(Integer, nullable=True)  # when set, link is for updating this deck (one-time)
    link_type = Column(String(32), nullable=False, default=LINK_TYPE_DECK_UPLOAD)  # deck_upload | deck_update | event_edit | feedback
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    label = Column(String(256), nullable=True)


def _get_engine():
    url = os.getenv("DATABASE_URL")
    if not url or not url.strip():
        return None
    url = url.strip()
    # Must be a full postgres URL (postgresql:// or postgres://), not just host:port
    if not (url.startswith("postgresql://") or url.startswith("postgres://")):
        logger.debug(
            "DATABASE_URL is set but not a PostgreSQL URL (expected postgresql://user:pass@host:port/db). Ignoring."
        )
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    try:
        return create_engine(url, pool_pre_ping=True, echo=os.getenv("SQL_ECHO", "").lower() in ("1", "true"))
    except Exception as e:
        logger.warning("Failed to create DB engine: %s. Database features disabled.", e)
        return None


_engine = None
_engine_tried = False  # So we only try once and don't spam logs on every request


def get_engine():
    global _engine, _engine_tried
    if _engine_tried:
        return _engine
    _engine_tried = True
    _engine = _get_engine()
    return _engine


def is_database_available() -> bool:
    return get_engine() is not None


def get_session_factory():
    engine = get_engine()
    if engine is None:
        return None
    return sessionmaker(engine, autocommit=False, autoflush=False, expire_on_commit=False)


_session_factory = None


def get_session_factory_cached():
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory()
    return _session_factory


@contextmanager
def session_scope():
    """Provide a transactional scope for a series of operations."""
    factory = get_session_factory_cached()
    if factory is None:
        raise RuntimeError("Database not configured (DATABASE_URL unset)")
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_migrations():
    """Run Alembic migrations (upgrade to head). Call from CLI or at startup."""
    from alembic import command
    from alembic.config import Config
    _project_root = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(_project_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(_project_root / "alembic"))
    command.upgrade(alembic_cfg, "head")


# --- Repository helpers: decks ---


def deck_row_to_dict(row: DeckRow) -> dict:
    return {
        "deck_id": row.deck_id,
        "event_id": row.event_id,
        "format_id": row.format_id or "",
        "name": row.name or "",
        "player": row.player or "",
        "event_name": row.event_name or "",
        "date": row.date or "",
        "rank": row.rank or "",
        "player_count": row.player_count or 0,
        "commanders": row.commanders if isinstance(row.commanders, list) else [],
        "archetype": row.archetype,
        "mainboard": row.mainboard if isinstance(row.mainboard, list) else [],
        "sideboard": row.sideboard if isinstance(row.sideboard, list) else [],
    }


def dict_to_deck_row(d: dict, origin: str = ORIGIN_MTGTOP8) -> DeckRow:
    mainboard, sideboard = _normalize_boards(d)
    return DeckRow(
        deck_id=d["deck_id"],
        event_id=_event_id_str(d["event_id"]),
        origin=origin,
        format_id=d.get("format_id", ""),
        name=d.get("name", ""),
        player=d.get("player", ""),
        event_name=d.get("event_name", ""),
        date=d.get("date", ""),
        rank=d.get("rank", ""),
        player_count=int(d.get("player_count", 0)),
        commanders=d.get("commanders") or [],
        archetype=d.get("archetype"),
        mainboard=mainboard,
        sideboard=sideboard,
    )


def get_all_decks(session: Session) -> list[dict]:
    rows = session.query(DeckRow).all()
    return [deck_row_to_dict(r) for r in rows]


def get_decks_by_event(session: Session, event_id: int | str) -> list[dict]:
    """Return all decks for an event (by event_id)."""
    eid = _event_id_str(event_id)
    rows = session.query(DeckRow).filter(DeckRow.event_id == eid).all()
    return [deck_row_to_dict(r) for r in rows]


def upsert_deck(session: Session, d: dict, origin: str = ORIGIN_MTGTOP8) -> DeckRow:
    """Insert or update a deck by deck_id. For scrape duplicate protection (re-scrape same event = update)."""
    row = session.query(DeckRow).filter(DeckRow.deck_id == d["deck_id"]).first()
    mainboard, sideboard = _normalize_boards(d)
    if row:
        row.event_id = _event_id_str(d.get("event_id", row.event_id))
        row.format_id = d.get("format_id", row.format_id)
        row.name = d.get("name", row.name)
        row.player = d.get("player", row.player)
        row.event_name = d.get("event_name", row.event_name)
        row.date = d.get("date", row.date)
        row.rank = d.get("rank", row.rank)
        row.player_count = int(d.get("player_count", row.player_count))
        row.commanders = d.get("commanders") or row.commanders
        row.archetype = d.get("archetype", row.archetype)
        row.mainboard = mainboard
        row.sideboard = sideboard
        return row
    row = DeckRow(
        deck_id=d["deck_id"],
        event_id=_event_id_str(d["event_id"]),
        origin=origin,
        format_id=d.get("format_id", ""),
        name=d.get("name", ""),
        player=d.get("player", ""),
        event_name=d.get("event_name", ""),
        date=d.get("date", ""),
        rank=d.get("rank", ""),
        player_count=int(d.get("player_count", 0)),
        commanders=d.get("commanders") or [],
        archetype=d.get("archetype"),
        mainboard=mainboard,
        sideboard=sideboard,
    )
    session.add(row)
    return row


def delete_deck(session: Session, deck_id: int) -> bool:
    row = session.query(DeckRow).filter(DeckRow.deck_id == deck_id).first()
    if row:
        session.delete(row)
        return True
    return False


def update_deck_event(
    session: Session,
    deck_id: int,
    event_id: str,
    event_name: str,
    date: str,
) -> bool:
    """Update a deck's event assignment (move to another event). Returns True if deck existed."""
    row = session.query(DeckRow).filter(DeckRow.deck_id == deck_id).first()
    if not row:
        return False
    row.event_id = _event_id_str(event_id)
    row.event_name = event_name or row.event_name
    row.date = date or row.date
    return True


def next_manual_deck_id(session: Session) -> int:
    """Return next deck_id for manual uploads (>= MANUAL_DECK_ID_START)."""
    from sqlalchemy import func
    r = session.query(func.max(DeckRow.deck_id)).filter(DeckRow.origin == ORIGIN_MANUAL).scalar()
    if r is None:
        return MANUAL_DECK_ID_START
    return max(MANUAL_DECK_ID_START, r + 1)


# --- Repository helpers: events ---


def event_row_to_dict(row: EventRow) -> dict:
    """Convert an EventRow into the canonical event dict shape used by the API."""
    return {
        "event_id": row.event_id,
        "event_name": row.name,
        "store": row.store or "",
        "location": row.location or "",
        "date": row.date,
        "format_id": row.format_id,
        "player_count": row.player_count or 0,
        "origin": row.origin or ORIGIN_MTGTOP8,
    }


def _normalize_boards(d: dict) -> tuple[list[dict], list[dict]]:
    """Ensure mainboard/sideboard are lists of {qty, card} dicts."""
    mainboard = d.get("mainboard", []) or []
    sideboard = d.get("sideboard", []) or []

    def _ensure_board(board):
        if board and isinstance(board[0], dict):
            return board
        return [{"qty": q, "card": c} for q, c in board]

    return _ensure_board(mainboard), _ensure_board(sideboard)


def get_all_events(session: Session) -> list[dict]:
    rows = session.query(EventRow).order_by(EventRow.date.desc(), EventRow.event_id).all()
    return [event_row_to_dict(r) for r in rows]


def get_mtgtop8_event_ids(session: Session) -> set[int]:
    """Return set of numeric MTGTop8 event IDs. Manual IDs (e.g. m1) are excluded."""
    rows = session.query(EventRow.event_id).filter(EventRow.origin == ORIGIN_MTGTOP8).all()
    result: set[int] = set()
    for (eid,) in rows:
        if eid and str(eid).isdigit():
            result.add(int(eid))
    return result


def _event_id_str(value: int | str) -> str:
    """Normalize event_id to string for DB (scraped: 80454 -> '80454'; manual: 'm1')."""
    if value is None:
        raise ValueError("event_id is required")
    return str(value) if not isinstance(value, str) else value


def next_manual_event_id(session: Session) -> str:
    """Return next manual event id: m1, m2, m3, ..."""
    rows = (
        session.query(EventRow.event_id)
        .filter(EventRow.origin == ORIGIN_MANUAL, EventRow.event_id.like(f"{MANUAL_EVENT_ID_PREFIX}%"))
        .all()
    )
    max_n = 0
    for (eid,) in rows:
        try:
            n = int(eid[len(MANUAL_EVENT_ID_PREFIX) :].strip() or "0")
            max_n = max(max_n, n)
        except ValueError:
            pass
    return f"{MANUAL_EVENT_ID_PREFIX}{max_n + 1}"


def create_event(
    session: Session,
    event_name: str,
    date: str,
    format_id: str,
    origin: str = ORIGIN_MANUAL,
    event_id: int | str | None = None,
    player_count: int = 0,
    store: str = "",
    location: str = "",
) -> EventRow:
    if event_id is None and origin == ORIGIN_MANUAL:
        event_id = next_manual_event_id(session)
    elif event_id is None:
        raise ValueError("event_id required for mtgtop8 origin")
    event_id = _event_id_str(event_id)
    row = EventRow(
        event_id=event_id,
        origin=origin,
        format_id=format_id or "",
        name=event_name or "",
        store=store or "",
        location=location or "",
        date=date or "",
        player_count=player_count or 0,
    )
    session.add(row)
    return row


def get_event(session: Session, event_id: int | str) -> EventRow | None:
    return session.query(EventRow).filter(EventRow.event_id == _event_id_str(event_id)).first()


def update_event(
    session: Session,
    event_id: int | str,
    event_name: str | None = None,
    date: str | None = None,
    format_id: str | None = None,
    player_count: int | None = None,
    store: str | None = None,
    location: str | None = None,
) -> bool:
    eid = _event_id_str(event_id)
    row = session.query(EventRow).filter(EventRow.event_id == eid).first()
    if not row:
        return False
    if event_name is not None:
        row.name = event_name
    if date is not None:
        row.date = date
    if format_id is not None:
        row.format_id = format_id
    if player_count is not None:
        row.player_count = player_count
    if store is not None:
        row.store = store
    if location is not None:
        row.location = location
    return True


def delete_event(session: Session, event_id: int | str, delete_decks: bool = False) -> bool:
    eid = _event_id_str(event_id)
    row = session.query(EventRow).filter(EventRow.event_id == eid).first()
    if not row:
        return False
    if delete_decks:
        session.query(DeckRow).filter(DeckRow.event_id == eid).delete()
    session.delete(row)
    return True


def reassign_decks_to_event(
    session: Session,
    from_event_id: int | str,
    to_event_id: str,
    new_event_name: str,
    new_date: str,
) -> int:
    """Move all decks from from_event_id to to_event_id and set event_name/date. Returns count of decks moved."""
    eid_from = _event_id_str(from_event_id)
    eid_to = _event_id_str(to_event_id)
    rows = session.query(DeckRow).filter(DeckRow.event_id == eid_from).all()
    for row in rows:
        row.event_id = eid_to
        row.event_name = new_event_name or row.event_name
        row.date = new_date or row.date
    return len(rows)


def reassign_upload_links_to_event(
    session: Session,
    from_event_id: int | str,
    to_event_id: str,
) -> int:
    """Update all upload links pointing at from_event_id to to_event_id. Returns count updated."""
    eid_from = _event_id_str(from_event_id)
    eid_to = _event_id_str(to_event_id)
    rows = session.query(EventUploadLinkRow).filter(EventUploadLinkRow.event_id == eid_from).all()
    for row in rows:
        row.event_id = eid_to
    return len(rows)


# --- Repository helpers: event_upload_links ---


def create_upload_link(
    session: Session,
    token: str,
    event_id: str,
    label: str | None = None,
    expires_at: datetime | None = None,
    deck_id: int | None = None,
    link_type: str = LINK_TYPE_DECK_UPLOAD,
) -> EventUploadLinkRow:
    """Insert a one-time upload link. Token from secrets.token_urlsafe(32). If deck_id is set and link_type is deck_upload, becomes deck_update. link_type: deck_upload | deck_update | event_edit | feedback."""
    eid = _event_id_str(event_id)
    if deck_id is not None and link_type == LINK_TYPE_DECK_UPLOAD:
        link_type = LINK_TYPE_DECK_UPDATE
    row = EventUploadLinkRow(
        token=token,
        event_id=eid,
        deck_id=deck_id,
        link_type=link_type,
        label=label,
        expires_at=expires_at,
    )
    session.add(row)
    return row


def get_upload_link(session: Session, token: str) -> EventUploadLinkRow | None:
    return session.query(EventUploadLinkRow).filter(EventUploadLinkRow.token == token).first()


def mark_upload_link_used(session: Session, token: str) -> bool:
    row = session.query(EventUploadLinkRow).filter(EventUploadLinkRow.token == token).first()
    if not row:
        return False
    row.used_at = datetime.utcnow()
    return True


def get_all_upload_links(session: Session) -> list[dict]:
    """Return all upload links for admin listing."""
    rows = session.query(EventUploadLinkRow).order_by(EventUploadLinkRow.created_at.desc()).all()
    return [
        {
            "token": r.token,
            "event_id": r.event_id,
            "deck_id": getattr(r, "deck_id", None),
            "link_type": getattr(r, "link_type", "deck_upload"),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "used_at": r.used_at.isoformat() if r.used_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "label": r.label,
        }
        for r in rows
    ]


def delete_upload_link(session: Session, token: str) -> bool:
    row = session.query(EventUploadLinkRow).filter(EventUploadLinkRow.token == token).first()
    if not row:
        return False
    session.delete(row)
    return True


def invalidate_upload_links_for_slot(
    session: Session,
    event_id: str,
    link_type: str,
    deck_id: int | None = None,
) -> int:
    """Delete existing one-time links for the same slot (event_id + link_type + optional deck_id). Returns count deleted.
    Use before creating a new link so the old one becomes invalid."""
    eid = _event_id_str(event_id)
    q = session.query(EventUploadLinkRow).filter(
        EventUploadLinkRow.event_id == eid,
        EventUploadLinkRow.link_type == link_type,
    )
    if deck_id is not None:
        q = q.filter(EventUploadLinkRow.deck_id == deck_id)
    count = q.count()
    q.delete()
    return count


def delete_all_upload_links(session: Session, used_only: bool = False) -> int:
    """Delete upload links. If used_only=True, only delete links that have been used. Returns count deleted."""
    q = session.query(EventUploadLinkRow)
    if used_only:
        q = q.filter(EventUploadLinkRow.used_at.isnot(None))
    count = q.count()
    q.delete()
    return count


# --- Repository helpers: player_emails ---


def set_player_email(session: Session, player: str, email: str) -> None:
    """Upsert player email. Empty email deletes the row."""
    player = (player or "").strip()
    if not player:
        return
    row = session.query(PlayerEmailRow).filter(PlayerEmailRow.player == player).first()
    if not email or not email.strip():
        if row:
            session.delete(row)
        return
    email = email.strip()
    if row:
        row.email = email
    else:
        session.add(PlayerEmailRow(player=player, email=email))


def get_player_email(session: Session, player: str) -> str | None:
    row = session.query(PlayerEmailRow).filter(PlayerEmailRow.player == player).first()
    return row.email if row else None


def get_emails_for_players(session: Session, players: list[str]) -> dict[str, str]:
    """Return { canonical_player: email } for players that have an email stored."""
    if not players:
        return {}
    rows = session.query(PlayerEmailRow).filter(PlayerEmailRow.player.in_(players)).all()
    return {r.player: r.email for r in rows}


def has_emails_for_players(session: Session, players: list[str]) -> dict[str, bool]:
    """Return { player: True } for each player that has an email (for has_email in UI)."""
    emails = get_emails_for_players(session, players)
    return {p: True for p in emails}


# --- Repository helpers: matchups ---


def get_deck_by_event_and_player(session: Session, event_id: str, player: str) -> DeckRow | None:
    """One deck per player per event: return the deck for this event and canonical player."""
    eid = _event_id_str(event_id)
    return (
        session.query(DeckRow)
        .filter(DeckRow.event_id == eid, DeckRow.player == player)
        .first()
    )


def list_matchups_by_deck(session: Session, deck_id: int) -> list[dict]:
    rows = (
        session.query(MatchupRow)
        .filter(MatchupRow.deck_id == deck_id)
        .order_by(MatchupRow.round, MatchupRow.id)
        .all()
    )
    return [
        {
            "id": r.id,
            "deck_id": r.deck_id,
            "opponent_player": r.opponent_player,
            "opponent_deck_id": r.opponent_deck_id,
            "opponent_archetype": r.opponent_archetype,
            "result": r.result,
            "result_note": r.result_note or "",
            "round": r.round,
        }
        for r in rows
    ]


def upsert_matchups_for_deck(
    session: Session,
    deck_id: int,
    matchups: list[dict],
) -> None:
    """Replace all matchups for this deck with the given list. Each item: opponent_player, result, result_note?, round?."""
    session.query(MatchupRow).filter(MatchupRow.deck_id == deck_id).delete()
    for m in matchups:
        row = MatchupRow(
            deck_id=deck_id,
            opponent_player=(m.get("opponent_player") or "").strip(),
            opponent_deck_id=m.get("opponent_deck_id"),
            opponent_archetype=m.get("opponent_archetype"),
            result=(m.get("result") or "loss").strip(),
            result_note=(m.get("result_note") or "").strip() or None,
            round=m.get("round"),
        )
        session.add(row)


def get_matchup(session: Session, matchup_id: int) -> MatchupRow | None:
    return session.query(MatchupRow).filter(MatchupRow.id == matchup_id).first()


def update_matchup(
    session: Session,
    matchup_id: int,
    result: str | None = None,
    result_note: str | None = None,
    round: int | None = None,
) -> bool:
    row = get_matchup(session, matchup_id)
    if not row:
        return False
    if result is not None:
        row.result = result
    if result_note is not None:
        row.result_note = result_note or None
    if round is not None:
        row.round = round
    return True


def reassign_matchups_to_deck(
    session: Session,
    from_deck_id: int,
    to_deck_id: int,
) -> tuple[int, int]:
    """Move all matchups from from_deck to to_deck (merge). Updates deck_id and opponent_deck_id. Returns (updated_as_deck, updated_as_opponent)."""
    rows_deck = session.query(MatchupRow).filter(MatchupRow.deck_id == from_deck_id).all()
    rows_opp = session.query(MatchupRow).filter(MatchupRow.opponent_deck_id == from_deck_id).all()
    for r in rows_deck:
        r.deck_id = to_deck_id
    for r in rows_opp:
        r.opponent_deck_id = to_deck_id
    return len(rows_deck), len(rows_opp)


def list_matchups_for_event(session: Session, event_id: str) -> list[dict]:
    """All matchups for decks in this event (join matchups -> decks on event_id)."""
    eid = _event_id_str(event_id)
    deck_ids = [r.deck_id for r in session.query(DeckRow.deck_id).filter(DeckRow.event_id == eid).all()]
    if not deck_ids:
        return []
    rows = (
        session.query(MatchupRow)
        .filter(MatchupRow.deck_id.in_(deck_ids), MatchupRow.opponent_deck_id.isnot(None))
        .all()
    )
    return [
        {
            "id": r.id,
            "deck_id": r.deck_id,
            "opponent_deck_id": r.opponent_deck_id,
            "result": r.result,
            "result_note": r.result_note,
            "round": r.round,
        }
        for r in rows
    ]


def list_all_matchups_with_event_id(session: Session) -> list[dict]:
    """All matchups with event_id (via deck). Returns list of { deck_id, opponent_deck_id, result, event_id }."""
    rows = (
        session.query(MatchupRow.deck_id, MatchupRow.opponent_deck_id, MatchupRow.result, DeckRow.event_id)
        .join(DeckRow, MatchupRow.deck_id == DeckRow.deck_id)
        .filter(MatchupRow.opponent_deck_id.isnot(None))
        .all()
    )
    return [
        {"deck_id": r.deck_id, "opponent_deck_id": r.opponent_deck_id, "result": r.result or "", "event_id": r.event_id or ""}
        for r in rows
    ]


def list_matchups_reported_against_player(session: Session, event_id: str, opponent_player: str) -> list[dict]:
    """Matchups in this event where the given player was the opponent (others reported a result vs them).
    Returns list of { reporting_player, result }."""
    eid = _event_id_str(event_id)
    opp = (opponent_player or "").strip()
    if not opp:
        return []
    deck_ids = [r.deck_id for r in session.query(DeckRow.deck_id).filter(DeckRow.event_id == eid).all()]
    if not deck_ids:
        return []
    rows = (
        session.query(MatchupRow, DeckRow)
        .join(DeckRow, MatchupRow.deck_id == DeckRow.deck_id)
        .filter(DeckRow.event_id == eid, MatchupRow.opponent_player == opp)
        .all()
    )
    return [
        {"reporting_player": (d.player or "").strip(), "result": (m.result or "").strip()}
        for m, d in rows
    ]


# --- Repository helpers: player_aliases ---


def get_player_aliases(session: Session) -> dict[str, str]:
    rows = session.query(PlayerAliasRow).all()
    return {r.alias: r.canonical for r in rows}


def set_player_alias(session: Session, alias: str, canonical: str) -> None:
    row = session.query(PlayerAliasRow).filter(PlayerAliasRow.alias == alias).first()
    if row:
        row.canonical = canonical
    else:
        session.add(PlayerAliasRow(alias=alias, canonical=canonical))


def remove_player_alias(session: Session, alias: str) -> bool:
    row = session.query(PlayerAliasRow).filter(PlayerAliasRow.alias == alias).first()
    if row:
        session.delete(row)
        return True
    return False


# --- Repository helpers: settings ---


def get_setting(session: Session, key: str) -> dict | list | None:
    row = session.query(SettingsRow).filter(SettingsRow.key == key).first()
    if row is None or row.value is None:
        return None
    return row.value


def set_setting(session: Session, key: str, value: dict | list | int) -> None:
    row = session.query(SettingsRow).filter(SettingsRow.key == key).first()
    if row:
        row.value = value
    else:
        session.add(SettingsRow(key=key, value=value))


MATCHUPS_MIN_MATCHES_KEY = "matchups_min_matches"


def get_matchups_min_matches(session: Session) -> int:
    """Return the minimum number of matches to show an archetype pair (default 0)."""
    v = get_setting(session, MATCHUPS_MIN_MATCHES_KEY)
    if v is None:
        return 0
    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], int):
        return max(0, v[0])
    if isinstance(v, int):
        return max(0, v)
    return 0


def set_matchups_min_matches(session: Session, value: int) -> None:
    set_setting(session, MATCHUPS_MIN_MATCHES_KEY, max(0, value))


def list_matchups_with_deck_info(session: Session) -> list[dict]:
    """All matchups with their deck's archetype, format_id, date, event_id (for summary aggregation)."""
    rows = (
        session.query(MatchupRow, DeckRow)
        .join(DeckRow, MatchupRow.deck_id == DeckRow.deck_id)
        .all()
    )
    return [
        {
            "deck_id": m.deck_id,
            "opponent_deck_id": m.opponent_deck_id,
            "archetype": (d.archetype or "").strip() or "(unknown)",
            "format_id": d.format_id or "",
            "event_id": d.event_id,
            "date": d.date or "",
            "opponent_archetype": (m.opponent_archetype or "").strip() or "(unknown)",
            "result": m.result or "loss",
            "result_note": m.result_note or "",
        }
        for m, d in rows
    ]
