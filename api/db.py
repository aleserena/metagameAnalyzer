"""Database layer: SQLAlchemy models, engine, session, and repository helpers.

When DATABASE_URL is set, all persistence uses PostgreSQL. When unset, the API
falls back to in-memory + file storage (see api/main.py).
"""

from __future__ import annotations

import logging
import math
import os
import re
import unicodedata
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
from sqlalchemy.orm import Session, aliased, declarative_base, sessionmaker

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


class PlayerRow(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True, autoincrement=True)
    display_name = Column(Text, nullable=False, unique=True)


class DeckRow(Base):
    __tablename__ = "decks"
    deck_id = Column(Integer, primary_key=True)
    event_id = Column(String(32), nullable=False)  # matches events.event_id (string)
    origin = Column(String(32), nullable=False, default=ORIGIN_MTGTOP8)
    format_id = Column(String(32), nullable=False, default="")
    name = Column(String(512), nullable=False, default="")
    player_id = Column(Integer, nullable=False)  # FK to players.id
    player = Column(String(512), nullable=False, default="")  # denormalized display name
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
    player_id = Column(Integer, nullable=False)  # FK to players.id


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
    player_id = Column(Integer, primary_key=True)  # FK to players.id
    email = Column(Text, nullable=False)


class MatchupRow(Base):
    __tablename__ = "matchups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    deck_id = Column(Integer, nullable=False)
    opponent_player_id = Column(Integer, nullable=True)  # FK to players.id; NULL for Bye/drop
    opponent_player = Column(String(512), nullable=False)  # display name or "Bye"/"(drop)"
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


def deck_row_to_dict(row: DeckRow, player_display_override: str | None = None) -> dict:
    """If ``player_display_override`` is set (e.g. ``players.display_name`` from a join), use it as ``player``."""
    disp = (player_display_override or "").strip() or (row.player or "")
    return {
        "deck_id": row.deck_id,
        "event_id": row.event_id,
        "format_id": row.format_id or "",
        "name": row.name or "",
        "player_id": getattr(row, "player_id", None),
        "player": disp,
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
        player_id=d["player_id"],
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
    """Load decks; ``player`` comes from ``players.display_name`` when joined so UI matches alias canonical."""
    rows = (
        session.query(DeckRow, PlayerRow.display_name)
        .outerjoin(PlayerRow, DeckRow.player_id == PlayerRow.id)
        .all()
    )
    return [deck_row_to_dict(r, pname) for r, pname in rows]


def get_decks_by_event(session: Session, event_id: int | str) -> list[dict]:
    """Return all decks for an event (by event_id)."""
    eid = _event_id_str(event_id)
    rows = (
        session.query(DeckRow, PlayerRow.display_name)
        .outerjoin(PlayerRow, DeckRow.player_id == PlayerRow.id)
        .filter(DeckRow.event_id == eid)
        .all()
    )
    return [deck_row_to_dict(r, pname) for r, pname in rows]


def _sync_deck_row_player_denorm(session: Session, row: DeckRow) -> None:
    """Keep ``decks.player`` equal to ``players.display_name`` for this ``player_id`` (canonical / alias target)."""
    if row.player_id is None:
        return
    prow = get_player_by_id(session, row.player_id)
    if prow and (prow.display_name or "").strip():
        row.player = (prow.display_name or "").strip()


def upsert_deck(session: Session, d: dict, origin: str = ORIGIN_MTGTOP8) -> DeckRow:
    """Insert or update a deck by deck_id. For scrape duplicate protection (re-scrape same event = update).
    If d does not contain player_id, resolves d['player'] to player_id (get_or_create) and sets d['player_id'], d['player']."""
    if "player_id" not in d:
        name = (d.get("player") or "").strip() or "(unknown)"
        pid, display = resolve_name_to_player_id(session, name)
        if pid is None:
            pid, display = get_or_create_player(session, name)
        d["player_id"] = pid
        d["player"] = display
    row = session.query(DeckRow).filter(DeckRow.deck_id == d["deck_id"]).first()
    mainboard, sideboard = _normalize_boards(d)
    if row:
        row.event_id = _event_id_str(d.get("event_id", row.event_id))
        row.format_id = d.get("format_id", row.format_id)
        row.name = d.get("name", row.name)
        if "player_id" in d:
            row.player_id = d["player_id"]
        row.player = d.get("player", row.player)
        row.event_name = d.get("event_name", row.event_name)
        row.date = d.get("date", row.date)
        row.rank = d.get("rank", row.rank)
        row.player_count = int(d.get("player_count", row.player_count))
        row.commanders = d.get("commanders") or row.commanders
        row.archetype = d.get("archetype", row.archetype)
        row.mainboard = mainboard
        row.sideboard = sideboard
        _sync_deck_row_player_denorm(session, row)
        return row
    row = DeckRow(
        deck_id=d["deck_id"],
        event_id=_event_id_str(d["event_id"]),
        origin=origin,
        format_id=d.get("format_id", ""),
        name=d.get("name", ""),
        player_id=d["player_id"],
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
    _sync_deck_row_player_denorm(session, row)
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
    """Return next deck_id for manual uploads (>= MANUAL_DECK_ID_START).

    Must be strictly greater than every existing deck_id (MTGTop8 and manual) to avoid PK collisions.
    """
    from sqlalchemy import func

    r = session.query(func.max(DeckRow.deck_id)).scalar()
    next_after_max = (r or 0) + 1
    return max(MANUAL_DECK_ID_START, next_after_max)


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


def list_event_ids_with_missing_decks(session: Session) -> list[str]:
    """Event IDs where deck count < player_count (and player_count > 0)."""
    deck_counts = (
        session.query(DeckRow.event_id, func.count(DeckRow.deck_id).label("cnt"))
        .group_by(DeckRow.event_id)
        .all()
    )
    deck_by_event = {_event_id_str(eid): cnt for (eid, cnt) in deck_counts}
    result = []
    for (eid, pc) in session.query(EventRow.event_id, EventRow.player_count).all():
        if eid is None:
            continue
        eid_str = _event_id_str(eid)
        pc_val = pc or 0
        if pc_val > 0 and deck_by_event.get(eid_str, 0) < pc_val:
            result.append(eid_str)
    return result


def list_event_ids_with_complete_matchups(session: Session) -> list[str]:
    """Event IDs where every deck has the expected number of matchups (Swiss rounds).
    Frontend uses this set: events NOT in this list have missing matchups.
    Uses bulk queries to avoid N+1 (one query per event)."""
    # All event IDs
    event_ids = [
        (r.event_id or "").strip()
        for r in session.query(EventRow.event_id).all()
        if (r.event_id or "").strip()
    ]
    if not event_ids:
        return []

    # All decks: event_id, deck_id, player_id, player (for events we care about)
    deck_rows = (
        session.query(DeckRow.event_id, DeckRow.deck_id, DeckRow.player_id, DeckRow.player)
        .filter(DeckRow.event_id.in_(event_ids))
        .all()
    )
    # event_id -> [(deck_id, player_id, player)], event_id -> set(deck_id), and event_id -> player_id -> [deck_id]
    decks_by_event: dict[str, list[tuple[int, int, str]]] = {}
    event_deck_ids: dict[str, set[int]] = {}
    event_player_to_decks: dict[str, dict[int, list[int]]] = {}
    for eid, deck_id, pid, player in deck_rows:
        eid = (eid or "").strip()
        decks_by_event.setdefault(eid, []).append((deck_id, pid, (player or "").strip()))
        event_deck_ids.setdefault(eid, set()).add(deck_id)
        event_player_to_decks.setdefault(eid, {}).setdefault(pid, []).append(deck_id)
    # Decks that have any result=drop (exempt from expected count)
    all_deck_ids = {did for s in event_deck_ids.values() for did in s}
    dropped_deck_ids: set[int] = set()
    if all_deck_ids:
        dropped_rows = (
            session.query(MatchupRow.deck_id)
            .filter(MatchupRow.deck_id.in_(all_deck_ids), MatchupRow.result == "drop")
            .distinct()
            .all()
        )
        dropped_deck_ids = {r[0] for r in dropped_rows}
    # All matchups for these decks, with event_id and opponent_player_id
    matchup_rows = (
        session.query(
            DeckRow.event_id,
            MatchupRow.deck_id,
            MatchupRow.opponent_deck_id,
            MatchupRow.opponent_player_id,
        )
        .join(MatchupRow, MatchupRow.deck_id == DeckRow.deck_id)
        .filter(DeckRow.event_id.in_(event_ids))
        .all()
    )

    result = []
    for eid in event_ids:
        decks = decks_by_event.get(eid, [])
        n = len(decks)
        expected = _swiss_rounds_for_players(n)
        if n == 0:
            result.append(eid)
            continue
        ev_deck_ids = event_deck_ids.get(eid, set())
        dropped_in_event = dropped_deck_ids & ev_deck_ids
        player_id_to_deck_ids = event_player_to_decks.get(eid, {})
        reported_by: dict[int, set[int]] = {}
        reported_against: dict[int, set[int]] = {}
        for ev, did, opp_did, opp_pid in matchup_rows:
            if ev != eid:
                continue
            if did not in reported_by:
                reported_by[did] = set()
            if opp_did is not None and opp_did in ev_deck_ids:
                reported_by[did].add(opp_did)
            elif opp_pid is not None:
                for opp_did_in_ev in player_id_to_deck_ids.get(opp_pid, []):
                    if opp_did_in_ev != did:
                        reported_by[did].add(opp_did_in_ev)
            if did not in ev_deck_ids:
                continue
            victims = set()
            if opp_did is not None and opp_did in ev_deck_ids:
                victims.add(opp_did)
            if opp_pid is not None:
                victims.update(player_id_to_deck_ids.get(opp_pid, []))
            for victim in victims:
                if victim != did:
                    reported_against.setdefault(victim, set()).add(did)
        has_missing = False
        for did, _pid, _ in decks:
            if did in dropped_in_event:
                continue
            effective = reported_by.get(did, set()) | reported_against.get(did, set())
            if len(effective) < expected:
                has_missing = True
                break
        if not has_missing:
            result.append(eid)
    return result


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
    """Upsert player email by canonical name (resolve to player_id). Empty email deletes the row."""
    player = (player or "").strip()
    if not player:
        return
    pid, _ = resolve_name_to_player_id(session, player)
    if pid is None:
        pid, _ = get_or_create_player(session, player)
    row = session.query(PlayerEmailRow).filter(PlayerEmailRow.player_id == pid).first()
    if not email or not email.strip():
        if row:
            session.delete(row)
        return
    email = email.strip()
    if row:
        row.email = email
    else:
        session.add(PlayerEmailRow(player_id=pid, email=email))


def get_player_email(session: Session, player: str) -> str | None:
    """Get email for player by name (resolve to player_id)."""
    pid, _ = resolve_name_to_player_id(session, (player or "").strip())
    if pid is None:
        return None
    row = session.query(PlayerEmailRow).filter(PlayerEmailRow.player_id == pid).first()
    return row.email if row else None


def get_emails_for_players(session: Session, players: list[str]) -> dict[str, str]:
    """Return { canonical_player_name: email } for players that have an email stored."""
    if not players:
        return {}
    result = {}
    for p in players:
        p = (p or "").strip()
        if not p:
            continue
        pid, display = resolve_name_to_player_id(session, p)
        if pid is None:
            pid, display = get_or_create_player(session, p)
        row = session.query(PlayerEmailRow).filter(PlayerEmailRow.player_id == pid).first()
        if row:
            result[display] = row.email
    return result


def get_emails_for_player_ids(session: Session, player_ids: list[int]) -> dict[int, str]:
    """Return { player_id: email } for player_ids that have an email stored."""
    if not player_ids:
        return {}
    rows = session.query(PlayerEmailRow).filter(PlayerEmailRow.player_id.in_(player_ids)).all()
    return {r.player_id: r.email for r in rows}


def has_emails_for_players(session: Session, players: list[str]) -> dict[str, bool]:
    """Return { player: True } for each player that has an email (for has_email in UI)."""
    emails = get_emails_for_players(session, players)
    return {p: True for p in emails}


# --- Repository helpers: matchups ---


def get_deck_by_event_and_player_id(session: Session, event_id: str, player_id: int) -> DeckRow | None:
    """One deck per player per event: return the deck for this event and player_id."""
    eid = _event_id_str(event_id)
    return session.query(DeckRow).filter(DeckRow.event_id == eid, DeckRow.player_id == player_id).first()


def get_deck_by_event_and_player(session: Session, event_id: str, player: str) -> DeckRow | None:
    """One deck per player per event: return the deck for this event and canonical player.
    Resolves name via aliases/players then looks up by player_id."""
    eid = _event_id_str(event_id)
    player = (player or "").strip()
    if not player:
        return None
    pid, _ = resolve_name_to_player_id(session, player)
    if pid is None:
        pid, _ = get_or_create_player(session, player)
    return get_deck_by_event_and_player_id(session, eid, pid)


def list_matchups_by_deck(session: Session, deck_id: int) -> list[dict]:
    Opp = aliased(PlayerRow)
    rows = (
        session.query(MatchupRow, Opp.display_name)
        .outerjoin(Opp, MatchupRow.opponent_player_id == Opp.id)
        .filter(MatchupRow.deck_id == deck_id)
        .order_by(MatchupRow.round, MatchupRow.id)
        .all()
    )
    out: list[dict] = []
    for r, opp_disp in rows:
        opp_name = (opp_disp or "").strip() or (r.opponent_player or "")
        out.append({
            "id": r.id,
            "deck_id": r.deck_id,
            "opponent_player_id": getattr(r, "opponent_player_id", None),
            "opponent_player": opp_name,
            "opponent_deck_id": r.opponent_deck_id,
            "opponent_archetype": r.opponent_archetype,
            "result": r.result,
            "result_note": r.result_note or "",
            "round": r.round,
        })
    return out


def count_effective_matchups_for_deck(session: Session, deck_id: int) -> int:
    """Count matchups where this deck is involved: as deck_id (reported by this deck) or as opponent_deck_id (reported by opponent)."""
    as_deck = session.query(MatchupRow).filter(MatchupRow.deck_id == deck_id).count()
    as_opponent = session.query(MatchupRow).filter(MatchupRow.opponent_deck_id == deck_id).count()
    return as_deck + as_opponent


def _invert_matchup_result(result: str) -> str:
    """Return the opponent's result: win<->loss, intentional_draw_win<->intentional_draw_loss, draw and intentional_draw unchanged."""
    r = (result or "").strip().lower()
    if r in ("win", "2-1", "1-0"):
        return "loss"
    if r in ("loss", "1-2", "0-1"):
        return "win"
    if r == "intentional_draw_win":
        return "intentional_draw_loss"
    if r == "intentional_draw_loss":
        return "intentional_draw_win"
    return result  # draw, intentional_draw, id, etc.


def upsert_matchups_for_deck(
    session: Session,
    deck_id: int,
    matchups: list[dict],
) -> None:
    """Replace all matchups for this deck. Each item: opponent_player, opponent_player_id?, opponent_deck_id?, result, ...
    Sets opponent_player_id from item or by resolving opponent_player (name). Bye/drop: opponent_player_id NULL.
    When opponent_deck_id is set (real opponent), also upserts the inverse row for the opponent so both sides
    of the matchup are stored (if A beats B, B is recorded as having lost to A)."""
    session.query(MatchupRow).filter(MatchupRow.deck_id == deck_id).delete()
    deck_row = session.query(DeckRow).filter(DeckRow.deck_id == deck_id).first()
    my_player_id = deck_row.player_id if deck_row else None
    my_player = (deck_row.player or "").strip() or "(unknown)" if deck_row else "(unknown)"
    if my_player_id is not None:
        prow = get_player_by_id(session, my_player_id)
        if prow and (prow.display_name or "").strip():
            my_player = (prow.display_name or "").strip()
    my_archetype = getattr(deck_row, "archetype", None) if deck_row else None

    for m in matchups:
        opponent_player = (m.get("opponent_player") or "").strip()
        result = (m.get("result") or "").strip()
        if not result:
            continue
        if not opponent_player and result not in ("bye", "drop"):
            continue
        opp_pid = m.get("opponent_player_id")
        if opp_pid is None and opponent_player and opponent_player not in ("Bye", "(drop)"):
            opp_pid, disp = resolve_name_to_player_id(session, opponent_player)
            if opp_pid is None:
                opp_pid, disp = get_or_create_player(session, opponent_player)
                opponent_player = disp
        elif opponent_player in ("Bye", "(drop)"):
            opp_pid = None
        opponent_deck_id = m.get("opponent_deck_id")
        round_num = m.get("round")

        row = MatchupRow(
            deck_id=deck_id,
            opponent_player_id=opp_pid,
            opponent_player=opponent_player or "Bye",
            opponent_deck_id=opponent_deck_id,
            opponent_archetype=m.get("opponent_archetype"),
            result=result,
            result_note=(m.get("result_note") or "").strip() or None,
            round=round_num,
        )
        session.add(row)

        # Store inverse for the opponent so both sides appear in the matrix and matchup counts are complete.
        if opponent_deck_id is not None and result.lower() not in ("bye", "drop"):
            session.query(MatchupRow).filter(
                MatchupRow.deck_id == opponent_deck_id,
                MatchupRow.opponent_deck_id == deck_id,
                MatchupRow.round == round_num,
            ).delete()
            inverse = MatchupRow(
                deck_id=opponent_deck_id,
                opponent_player_id=my_player_id,
                opponent_player=my_player,
                opponent_deck_id=deck_id,
                opponent_archetype=my_archetype,
                result=_invert_matchup_result(result),
                result_note=None,
                round=round_num,
            )
            session.add(inverse)


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


def delete_matchups_for_deck(session: Session, deck_id: int) -> int:
    """Delete all matchups for this deck. Returns count deleted."""
    rows = session.query(MatchupRow).filter(MatchupRow.deck_id == deck_id).all()
    for r in rows:
        session.delete(r)
    return len(rows)


def sync_matchup_opponent_identity_for_deck(
    session: Session,
    deck_id: int,
    player_id: int,
    player_display: str,
) -> int:
    """Update inverse matchup rows: where another deck reports playing against ``deck_id``,
    set opponent_player_id / opponent_player to this deck's current player.

    Stale values after a rename would otherwise leave two identities (old + new) for the same deck."""
    display = (player_display or "").strip() or "(unknown)"
    rows = session.query(MatchupRow).filter(MatchupRow.opponent_deck_id == deck_id).all()
    for r in rows:
        r.opponent_player_id = player_id
        r.opponent_player = display
    return len(rows)


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


def _swiss_rounds_for_players(n: int) -> int:
    """Expected Swiss rounds: 1–2 → 1 round, 3–4 → 2, 5–8 → 3, 9–16 → 4, 17–32 → 5, 33–64 → 6, etc."""
    if n <= 0:
        return 0
    return max(1, math.ceil(math.log2(n)))


def list_missing_matchups_for_event(session: Session, event_id: str) -> list[dict]:
    """Decks in this event that have fewer matchups than expected (expected = Swiss rounds for player count).
    A round is counted as covered for a deck if either that deck reported it or another player reported
    the matchup (opponent reported vs this deck). Byes count as a round. Decks with any result=drop
    are exempt from validation.
    Returns list of { deck_id, player, matchup_count, expected_count }. Uses player_id/opponent_player_id."""
    eid = _event_id_str(event_id)
    decks = (
        session.query(DeckRow.deck_id, DeckRow.player_id, DeckRow.player)
        .filter(DeckRow.event_id == eid)
        .all()
    )
    n = len(decks)
    expected = _swiss_rounds_for_players(n)
    if n == 0:
        return []
    event_deck_ids = set(d.deck_id for d in decks)
    player_id_to_deck_ids = {}
    for d in decks:
        player_id_to_deck_ids.setdefault(d.player_id, []).append(d.deck_id)
    dropped_deck_ids = set()
    if event_deck_ids:
        rows = (
            session.query(MatchupRow.deck_id)
            .filter(MatchupRow.deck_id.in_(event_deck_ids), MatchupRow.result == "drop")
            .distinct()
            .all()
        )
        dropped_deck_ids = {r[0] for r in rows}
    matchup_rows = (
        session.query(
            MatchupRow.deck_id,
            MatchupRow.opponent_deck_id,
            MatchupRow.opponent_player_id,
            MatchupRow.opponent_player,
        )
        .filter(MatchupRow.deck_id.in_(event_deck_ids))
        .all()
    )
    result = []
    for d in decks:
        deck_id, my_pid, player_name = d.deck_id, d.player_id, (d.player or "").strip() or "(unknown)"
        if deck_id in dropped_deck_ids:
            continue
        reported_by = set()
        for r in matchup_rows:
            if r.deck_id != deck_id:
                continue
            if r.opponent_deck_id is not None and r.opponent_deck_id in event_deck_ids:
                reported_by.add(r.opponent_deck_id)
            elif r.opponent_player_id is not None:
                for opp_did in player_id_to_deck_ids.get(r.opponent_player_id, []):
                    if opp_did != deck_id:
                        reported_by.add(opp_did)
        reported_against = set()
        for r in matchup_rows:
            if r.deck_id == deck_id:
                continue
            if r.deck_id not in event_deck_ids:
                continue
            if r.opponent_deck_id == deck_id:
                reported_against.add(r.deck_id)
            elif r.opponent_player_id is not None and r.opponent_player_id == my_pid:
                reported_against.add(r.deck_id)
        bye_count = sum(
            1
            for r in matchup_rows
            if r.deck_id == deck_id and (r.opponent_player or "").strip() == "Bye"
        )
        effective_count = len(reported_by | reported_against) + bye_count
        if effective_count < expected:
            result.append({
                "deck_id": deck_id,
                "player": player_name,
                "matchup_count": effective_count,
                "expected_count": expected,
            })
    return result


def list_matchups_reported_against_player(session: Session, event_id: str, opponent_player: str) -> list[dict]:
    """Matchups in this event where the given player was the opponent (others reported a result vs them).
    Resolves opponent_player to player_id, then filters by opponent_player_id. Returns list of { reporting_player, result }."""
    eid = _event_id_str(event_id)
    opp = (opponent_player or "").strip()
    if not opp:
        return []
    pid, _ = resolve_name_to_player_id(session, opp)
    if pid is None:
        pid, _ = get_or_create_player(session, opp)
    return list_matchups_reported_against_player_id(session, eid, pid)


def list_matchups_reported_against_player_id(session: Session, event_id: str, opponent_player_id: int) -> list[dict]:
    """Matchups in this event where the given player_id was the opponent. Returns list of { reporting_player, result }."""
    eid = _event_id_str(event_id)
    deck_ids = [r.deck_id for r in session.query(DeckRow.deck_id).filter(DeckRow.event_id == eid).all()]
    if not deck_ids:
        return []
    rows = (
        session.query(MatchupRow, DeckRow)
        .join(DeckRow, MatchupRow.deck_id == DeckRow.deck_id)
        .filter(DeckRow.event_id == eid, MatchupRow.opponent_player_id == opponent_player_id)
        .all()
    )
    return [
        {"reporting_player": (d.player or "").strip(), "result": (m.result or "").strip()}
        for m, d in rows
    ]


# --- Repository helpers: players ---


def _front_face_name(name: str) -> str:
    """Dual-faced style 'Front // Back' -> 'Front'. Used so 'Norman Osborn' and 'Norman Osborn // Green Goblin' match."""
    s = (name or "").strip()
    if not s or s in ("Bye", "(drop)"):
        return s or "(unknown)"
    if " // " in s:
        return s.split(" // ", 1)[0].strip() or s
    return s


def _normalize_name_for_lookup(name: str) -> str:
    """Lowercase and strip accents so 'Matias' and 'Matías' match when relating to existing players."""
    if not name or not (name := (name or "").strip()):
        return ""
    s = name.lower()
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def get_or_create_player(session: Session, display_name: str) -> tuple[int, str]:
    """Resolve display name to player_id (create player if missing). Returns (player_id, display_name).
    Dual-faced names (X // Y) are stored as front face (X). Accent-insensitive lookup avoids duplicate
    players (e.g. Matias and Matías map to the same record)."""
    name = (display_name or "").strip() or "(unknown)"
    canonical = _front_face_name(name)
    # Exact matches first
    row = session.query(PlayerRow).filter(PlayerRow.display_name == canonical).first()
    if row:
        if name != canonical:
            alias_row = session.query(PlayerAliasRow).filter(PlayerAliasRow.alias == name).first()
            if not alias_row:
                session.add(PlayerAliasRow(alias=name, player_id=row.id))
        return row.id, (row.display_name or "")
    row = session.query(PlayerRow).filter(PlayerRow.display_name == name).first()
    if row:
        return row.id, (row.display_name or "")
    # Before creating, find existing player by normalized name (e.g. Matías vs Matias)
    norm = _normalize_name_for_lookup(canonical)
    if norm:
        for existing in session.query(PlayerRow).all():
            if _normalize_name_for_lookup(existing.display_name or "") == norm:
                if name != (existing.display_name or ""):
                    alias_row = session.query(PlayerAliasRow).filter(PlayerAliasRow.alias == name).first()
                    if not alias_row:
                        session.add(PlayerAliasRow(alias=name, player_id=existing.id))
                return existing.id, (existing.display_name or "")
    new_row = PlayerRow(display_name=canonical)
    session.add(new_row)
    session.flush()
    if name != canonical:
        session.add(PlayerAliasRow(alias=name, player_id=new_row.id))
    return new_row.id, (new_row.display_name or "")


def get_player_by_id(session: Session, player_id: int) -> PlayerRow | None:
    return session.query(PlayerRow).filter(PlayerRow.id == player_id).first()


def resolve_name_to_player_id(session: Session, name: str) -> tuple[int | None, str]:
    """Resolve a name (alias or display name) to (player_id, display_name). Uses aliases then players table.
    Dual-faced names (X // Y) match display_name X. Accent-insensitive so 'Matias' resolves to 'Matías'."""
    n = (name or "").strip()
    if not n or n in ("Bye", "(drop)"):
        return None, n
    alias_row = session.query(PlayerAliasRow).filter(PlayerAliasRow.alias == n).first()
    if alias_row:
        player = get_player_by_id(session, alias_row.player_id)
        if player:
            return player.id, (player.display_name or "")
    player = session.query(PlayerRow).filter(PlayerRow.display_name == n).first()
    if player:
        return player.id, (player.display_name or "")
    canonical = _front_face_name(n)
    if canonical != n:
        player = session.query(PlayerRow).filter(PlayerRow.display_name == canonical).first()
        if player:
            return player.id, (player.display_name or "")
    # Normalized lookup so new event data (e.g. "Matias") relates to existing "Matías"
    norm = _normalize_name_for_lookup(canonical)
    if norm:
        for existing in session.query(PlayerRow).all():
            if _normalize_name_for_lookup(existing.display_name or "") == norm:
                return existing.id, (existing.display_name or "")
    return None, n


# --- Repository helpers: player_aliases ---


def get_player_aliases(session: Session) -> dict[str, str]:
    """Return alias -> canonical display name (for backward compat with _normalize_player)."""
    rows = (
        session.query(PlayerAliasRow.alias, PlayerRow.display_name)
        .join(PlayerRow, PlayerAliasRow.player_id == PlayerRow.id)
        .all()
    )
    return {r.alias: (r.display_name or "") for r in rows}


def set_player_alias(session: Session, alias: str, canonical: str) -> None:
    """Set alias -> canonical (creates player if needed, stores alias -> player_id)."""
    alias = (alias or "").strip()
    canonical = (canonical or "").strip() or "(unknown)"
    pid, _ = get_or_create_player(session, canonical)
    row = session.query(PlayerAliasRow).filter(PlayerAliasRow.alias == alias).first()
    if row:
        row.player_id = pid
    else:
        session.add(PlayerAliasRow(alias=alias, player_id=pid))


def set_player_alias_by_id(session: Session, alias: str, player_id: int) -> None:
    """Set alias -> player_id (for internal use)."""
    alias = (alias or "").strip()
    if not alias:
        return
    row = session.query(PlayerAliasRow).filter(PlayerAliasRow.alias == alias).first()
    if row:
        row.player_id = player_id
    else:
        session.add(PlayerAliasRow(alias=alias, player_id=player_id))


def remove_player_alias(session: Session, alias: str) -> bool:
    row = session.query(PlayerAliasRow).filter(PlayerAliasRow.alias == alias).first()
    if row:
        session.delete(row)
        return True
    return False


def merge_players(
    session: Session,
    from_player_id: int,
    to_player_id: int,
    canonical_name: str | None = None,
) -> None:
    """
    Merge all data from from_player_id into to_player_id, then delete from_player.

    No-op if ids are equal or to_player_id does not exist. On success, the
    from_player PlayerRow is always removed after references are repointed.

    Updates:
    - decks.player_id / decks.player (or delete a deck when ``(event_id, to_player_id)`` already exists —
      e.g. placeholder deck + real deck for same person in one event; matchups cascade with deck delete)
    - matchups.opponent_player_id / matchups.opponent_player
    - player_emails (player_id is PK: drops source email if canonical already has one)
    - player_aliases.player_id
    """
    if from_player_id == to_player_id:
        return

    to_row = get_player_by_id(session, to_player_id)
    if not to_row:
        return
    display = (canonical_name or to_row.display_name or "").strip() or "(unknown)"

    # Decks: one deck per (event_id, player_id). If target already has a deck in this event, drop the
    # from-player row (typically an Unnamed placeholder duplicate).
    decks = session.query(DeckRow).filter(DeckRow.player_id == from_player_id).all()
    for d in decks:
        conflict = (
            session.query(DeckRow)
            .filter(
                DeckRow.event_id == d.event_id,
                DeckRow.player_id == to_player_id,
                DeckRow.deck_id != d.deck_id,
            )
            .first()
        )
        if conflict is not None:
            session.delete(d)
        else:
            d.player_id = to_player_id
            d.player = display

    # Matchups where this player is the opponent
    matchups = (
        session.query(MatchupRow)
        .filter(MatchupRow.opponent_player_id == from_player_id)
        .all()
    )
    for m in matchups:
        m.opponent_player_id = to_player_id
        m.opponent_player = display

    # Emails: one row per player_id (PK). Repoint only if canonical has no email yet.
    to_email = (
        session.query(PlayerEmailRow)
        .filter(PlayerEmailRow.player_id == to_player_id)
        .first()
    )
    from_emails = (
        session.query(PlayerEmailRow)
        .filter(PlayerEmailRow.player_id == from_player_id)
        .all()
    )
    for e in from_emails:
        if to_email is not None:
            session.delete(e)
        else:
            e.player_id = to_player_id
            to_email = e

    # Aliases pointing at from_player_id
    alias_rows = (
        session.query(PlayerAliasRow)
        .filter(PlayerAliasRow.player_id == from_player_id)
        .all()
    )
    for a in alias_rows:
        a.player_id = to_player_id

    old = get_player_by_id(session, from_player_id)
    if old:
        session.delete(old)


def merge_players_by_names(session: Session, alias: str, canonical: str) -> None:
    """
    Convenience helper: given alias and canonical names, resolve to player_ids and
    merge alias player into canonical player when they differ.
    """
    alias = (alias or "").strip()
    canonical = (canonical or "").strip()
    if not alias or not canonical:
        return

    # Resolve canonical first (or create)
    pid_canonical, display = resolve_name_to_player_id(session, canonical)
    if pid_canonical is None:
        pid_canonical, display = get_or_create_player(session, canonical)

    pid_alias, _ = resolve_name_to_player_id(session, alias)
    if pid_alias is None or pid_alias == pid_canonical:
        return

    merge_players(
        session,
        from_player_id=pid_alias,
        to_player_id=pid_canonical,
        canonical_name=display,
    )


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


MATCHUPS_PLAYERS_MIN_MATCHES_KEY = "matchups_players_min_matches"


def get_matchups_players_min_matches(session: Session) -> int:
    """Return the minimum number of matches to show a player pair (default 0)."""
    v = get_setting(session, MATCHUPS_PLAYERS_MIN_MATCHES_KEY)
    if v is None:
        return 0
    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], int):
        return max(0, v[0])
    if isinstance(v, int):
        return max(0, v)
    return 0


def set_matchups_players_min_matches(session: Session, value: int) -> None:
    set_setting(session, MATCHUPS_PLAYERS_MIN_MATCHES_KEY, max(0, value))


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


_UNNAMED_PLACEHOLDER_DISPLAY_RE = re.compile(r"^Unnamed\s*\d*$", re.IGNORECASE)
# add_blank_deck_to_event fallback: Unnamed_<uuid10>
_UNNAMED_HEX_PLACEHOLDER_RE = re.compile(r"^Unnamed_[a-f0-9]{10}$", re.IGNORECASE)


def _is_unnamed_placeholder_display(name: str) -> bool:
    s = (name or "").strip()
    if _UNNAMED_PLACEHOLDER_DISPLAY_RE.fullmatch(s):
        return True
    return bool(_UNNAMED_HEX_PLACEHOLDER_RE.fullmatch(s))


def player_row_is_unnamed_placeholder(session: Session, player_id: int) -> bool:
    """True if this ``players`` row is a blank-deck placeholder (Unnamed / Unnamed N), not a real name."""
    row = get_player_by_id(session, player_id)
    if not row:
        return False
    return _is_unnamed_placeholder_display(row.display_name or "")


def _matchup_row_player_display(player_row: PlayerRow | None, denormalized: str) -> str:
    """Label for matrix / summaries: use players.display_name unless it is Unnamed* and denormalized text is a real name."""
    den = (denormalized or "").strip()
    if player_row is not None:
        disp = (player_row.display_name or "").strip()
        if (
            disp
            and _is_unnamed_placeholder_display(disp)
            and den
            and not _is_unnamed_placeholder_display(den)
        ):
            return den
        if disp:
            return disp
    return den or "(unknown)"


def list_matchups_with_deck_and_players(session: Session) -> list[dict]:
    """All matchups with deck's player_id, opponent_player_id, player names, archetypes, event_id, date, round.

    Names prefer ``players.display_name`` when it is a real name; if the row is still ``Unnamed*`` but
    ``decks.player`` / ``matchups.opponent_player`` was updated to the human-readable name, that text
    is used so the matchups matrix matches the event UI.
    """
    PlayerDeck = aliased(PlayerRow)
    PlayerOpp = aliased(PlayerRow)
    rows = (
        session.query(MatchupRow, DeckRow, PlayerDeck, PlayerOpp)
        .join(DeckRow, MatchupRow.deck_id == DeckRow.deck_id)
        .outerjoin(PlayerDeck, DeckRow.player_id == PlayerDeck.id)
        .outerjoin(PlayerOpp, MatchupRow.opponent_player_id == PlayerOpp.id)
        .all()
    )
    return [
        {
            "deck_id": m.deck_id,
            "opponent_deck_id": m.opponent_deck_id,
            "player_id": d.player_id,
            "opponent_player_id": (p_opp.id if p_opp else None),
            "player": _matchup_row_player_display(p_deck, d.player or ""),
            "opponent_player": _matchup_row_player_display(p_opp, m.opponent_player or ""),
            "archetype": (d.archetype or "").strip() or "(unknown)",
            "opponent_archetype": (m.opponent_archetype or "").strip() or "(unknown)",
            "format_id": d.format_id or "",
            "event_id": d.event_id,
            "date": d.date or "",
            "result": m.result or "loss",
            "result_note": m.result_note or "",
            "round": m.round,
        }
        for m, d, p_deck, p_opp in rows
    ]
