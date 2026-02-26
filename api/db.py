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


class EventUploadLinkRow(Base):
    __tablename__ = "event_upload_links"
    token = Column(String(64), primary_key=True)
    event_id = Column(String(32), nullable=False)
    deck_id = Column(Integer, nullable=True)  # when set, link is for updating this deck (one-time)
    link_type = Column(String(32), nullable=False, default=LINK_TYPE_DECK_UPLOAD)  # deck_upload | deck_update | event_edit
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
    mainboard = d.get("mainboard", [])
    sideboard = d.get("sideboard", [])
    if mainboard and isinstance(mainboard[0], dict):
        pass
    else:
        mainboard = [{"qty": q, "card": c} for q, c in mainboard]
    if sideboard and isinstance(sideboard[0], dict):
        pass
    else:
        sideboard = [{"qty": q, "card": c} for q, c in sideboard]
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


def upsert_deck(session: Session, d: dict, origin: str = ORIGIN_MTGTOP8) -> DeckRow:
    """Insert or update a deck by deck_id. For scrape duplicate protection (re-scrape same event = update)."""
    row = session.query(DeckRow).filter(DeckRow.deck_id == d["deck_id"]).first()
    mainboard = d.get("mainboard", [])
    sideboard = d.get("sideboard", [])
    if mainboard and isinstance(mainboard[0], dict):
        pass
    else:
        mainboard = [{"qty": q, "card": c} for q, c in mainboard]
    if sideboard and isinstance(sideboard[0], dict):
        pass
    else:
        sideboard = [{"qty": q, "card": c} for q, c in sideboard]
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


def next_manual_deck_id(session: Session) -> int:
    """Return next deck_id for manual uploads (>= MANUAL_DECK_ID_START)."""
    from sqlalchemy import func
    r = session.query(func.max(DeckRow.deck_id)).filter(DeckRow.origin == ORIGIN_MANUAL).scalar()
    if r is None:
        return MANUAL_DECK_ID_START
    return max(MANUAL_DECK_ID_START, r + 1)


# --- Repository helpers: events ---


def get_all_events(session: Session) -> list[dict]:
    rows = session.query(EventRow).order_by(EventRow.date.desc(), EventRow.event_id).all()
    return [
        {
            "event_id": r.event_id,
            "event_name": r.name,
            "store": r.store or "",
            "location": r.location or "",
            "date": r.date,
            "format_id": r.format_id,
            "player_count": r.player_count or 0,
        }
        for r in rows
    ]


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
    """Insert a one-time upload link. Token from secrets.token_urlsafe(32). If deck_id is set, link_type becomes deck_update. link_type: deck_upload | deck_update | event_edit."""
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


def delete_all_upload_links(session: Session, used_only: bool = False) -> int:
    """Delete upload links. If used_only=True, only delete links that have been used. Returns count deleted."""
    q = session.query(EventUploadLinkRow)
    if used_only:
        q = q.filter(EventUploadLinkRow.used_at.isnot(None))
    count = q.count()
    q.delete()
    return count


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


def set_setting(session: Session, key: str, value: dict | list) -> None:
    row = session.query(SettingsRow).filter(SettingsRow.key == key).first()
    if row:
        row.value = value
    else:
        session.add(SettingsRow(key=key, value=value))
