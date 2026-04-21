"""FastAPI backend for MTG Metagame web app."""

import hashlib
import json
import logging
import math
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

# Load .env from project root so DATABASE_URL (and others) are set before any config.
# First load .env (base), then if DB_ENV=dev|staging|prod load .env.{env} to override.
_project_root_for_env = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    _env_base = _project_root_for_env / ".env"
    if _env_base.exists():
        load_dotenv(_env_base)
    _db_env = os.getenv("DB_ENV", "").strip().lower()
    if _db_env in ("dev", "staging", "prod"):
        _env_override = _project_root_for_env / f".env.{_db_env}"
        if _env_override.exists():
            load_dotenv(_env_override)
except ImportError:
    pass

from api.logging_config import configure_logging
configure_logging()

import re
import threading
import time
import unicodedata
import uuid
from contextlib import asynccontextmanager
from urllib.parse import unquote

import jwt
import requests

logger = logging.getLogger(__name__)

def _normalize_search(s: str) -> str:
    """Lowercase and strip accents for relaxed substring matching."""
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

# Import from project - run from project root
import sys
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

DATA_DIR = Path(os.getenv("DATA_DIR", str(_project_root)))
if not DATA_DIR.is_absolute():
    DATA_DIR = _project_root / DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Max JSON upload size for admin load / deck import (bytes). Default 50 MiB.
MAX_UPLOAD_JSON_BYTES = int(os.getenv("MAX_UPLOAD_JSON_BYTES", str(50 * 1024 * 1024)))


async def _read_upload_json_bytes_async(upload: UploadFile) -> bytes:
    content = await upload.read(MAX_UPLOAD_JSON_BYTES + 1)
    if len(content) > MAX_UPLOAD_JSON_BYTES:
        raise HTTPException(status_code=413, detail="Upload too large")
    return content


def _resolve_load_path_under_data_dir(raw: str) -> Path:
    """Resolve a relative path under DATA_DIR; reject absolute paths and path traversal."""
    if raw is None or not str(raw).strip():
        raise HTTPException(status_code=400, detail="Invalid path")
    rel = Path(str(raw).strip())
    if rel.is_absolute():
        raise HTTPException(status_code=400, detail="path must be relative to DATA_DIR")
    base = DATA_DIR.resolve()
    resolved = (base / rel).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="path must stay under DATA_DIR") from None
    return resolved

from api.routers import router as api_router
from api.schemas.auth_feedback import CardLookupBody, LoginBody, SiteFeedbackBody
from api.schemas.decks import DeckListBody, ImportMoxfieldBody, SubmitDeckBody, UpdateDeckBody
from api.schemas.events import (
    CreateEventBody,
    DeckPairPreview,
    DECK_MERGE_FIELDS,
    EventExportData,
    EventResponse,
    EVENT_MERGE_FIELDS,
    LoadBody,
    MergeConflictItem,
    MergeEventsBody,
    MergePreviewResponse,
    ScrapeBody,
    UploadDecksBody,
)
from api.schemas.matchups import AdminMatchupsBody, PatchMatchupBody
from api.schemas.players import (
    PlayerAliasBody,
    PlayerAnalysisResponse,
    PlayerEmailBody,
)
from api.schemas.settings import (
    IgnoreLandsCardsBody,
    MatchupsMinMatchesBody,
    RankWeightsBody,
    SendFeedbackLinkToPlayerBody,
)
from api.schemas.upload import CreateUploadLinksBody, EventFeedbackBody
from api.services import settings as settings_service
from src.mtgtop8.analyzer import (
    analyze,
    archetype_aggregate_analysis,
    archetype_distribution,
    card_stat_buckets,
    deck_analysis,
    effective_commanders,
    effective_mainboard,
    find_duplicate_decks,
    is_top8,
    normalize_rank,
    player_leaderboard,
    similar_decks,
    top_cards_main,
)
from src.mtgtop8.card_lookup import autocomplete_cards, clear_cache as clear_scryfall_cache, lookup_cards
from src.mtgtop8.config import FORMATS
from src.mtgtop8.models import Deck
from src.mtgtop8.normalize import (
    canonical_card_name_for_compare as _canonical_card_key,
    normalize_card_name as _normalize_card_name,
)
from src.mtgtop8.scraper import event_display_name, parse_event_display, scrape
from src.mtgtop8.storage import load_json, save_json

try:
    from api import db as _db
except ImportError:
    _db = None

def _database_available() -> bool:
    return _db is not None and _db.is_database_available()


@asynccontextmanager
async def lifespan(_app):
    """Log startup and shutdown for monitoring (e.g. Railway)."""
    logger.info("Application startup", extra={"event": "startup"})
    yield
    logger.info("Application shutdown", extra={"event": "shutdown"})


app = FastAPI(title="MTG Metagame API", version="1.0.0", lifespan=lifespan)

_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount sub-routers
app.include_router(api_router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log each request with method, path, status, and duration for monitoring."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "%s %s %s %sms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return generic 500 and log the real error (avoid leaking internals)."""
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _get_build_id() -> str:
    """Short SHA from Railway or GIT_COMMIT_SHA; 'dev' if unset."""
    sha = os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT_SHA", "")
    if sha:
        return sha[:7]
    return "dev"


def _get_db_env() -> str:
    """DB environment: DB_ENV if set and valid, else 'postgres' when DB available, else 'json'."""
    if _database_available():
        env = os.getenv("DB_ENV", "").strip().lower()
        if env in ("dev", "staging", "prod"):
            return env
        return "postgres"
    return "json"


@app.get("/api/v1/info", tags=["Info"])
def get_info():
    """Public endpoint: build identifier (short SHA) and DB environment for footer display."""
    return {"build_id": _get_build_id(), "db_env": _get_db_env()}


# Admin auth: single user, password from env, JWT for session
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
JWT_SECRET = os.getenv("JWT_SECRET", ADMIN_PASSWORD or "dev-secret-change-in-production")
# PyJWT recommends at least 32 bytes for HS256; derive a 32-byte key if secret is shorter to avoid InsecureKeyLengthWarning
_JWT_KEY = JWT_SECRET.encode("utf-8") if len(JWT_SECRET.encode("utf-8")) >= 32 else hashlib.sha256(JWT_SECRET.encode("utf-8")).digest()
JWT_ALGORITHM = "HS256"
JWT_EXP_SECONDS = 7 * 24 * 3600  # 7 days


def _create_admin_token() -> str:
    return jwt.encode(
        {"sub": "admin", "exp": int(time.time()) + JWT_EXP_SECONDS},
        _JWT_KEY,
        algorithm=JWT_ALGORITHM,
    )


def _verify_admin_token(token: str) -> bool:
    try:
        payload = jwt.decode(token, _JWT_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("sub") == "admin"
    except jwt.PyJWTError:
        return False


def require_admin(authorization: str | None = Header(None, alias="Authorization")):
    """Dependency: require valid admin Bearer token or raise 401."""
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Admin login disabled (ADMIN_PASSWORD not set)")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if not _verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return "admin"


def optional_admin(authorization: str | None = Header(None, alias="Authorization")):
    """Dependency: return 'admin' if valid admin token, else None. Does not raise."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if _verify_admin_token(token):
        return "admin"
    return None


def require_admin_or_event_edit(
    event_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    x_event_edit_token: str | None = Header(None, alias="X-Event-Edit-Token"),
):
    """Dependency: require admin Bearer token OR valid one-time event-edit token for this event."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if _verify_admin_token(token):
            return "admin"
    if x_event_edit_token and _db and _db.is_database_available():
        with _db.session_scope() as session:
            row = _db.get_upload_link(session, x_event_edit_token.strip())
            if row and getattr(row, "link_type", None) == _db.LINK_TYPE_EVENT_EDIT and row.event_id == _db._event_id_str(event_id):
                if row.expires_at is not None and row.expires_at < datetime.utcnow():
                    raise HTTPException(status_code=401, detail="Event edit link expired")
                return "event_edit"
    raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_admin_or_event_edit_deck(
    deck_id: int,
    authorization: str | None = Header(None, alias="Authorization"),
    x_event_edit_token: str | None = Header(None, alias="X-Event-Edit-Token"),
):
    """Dependency: require admin OR valid event-edit token for the event that owns this deck."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if _verify_admin_token(token):
            return "admin"
    deck = _get_deck_by_id(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    event_id = str(deck.get("event_id", ""))
    if x_event_edit_token and _db and _db.is_database_available():
        with _db.session_scope() as session:
            row = _db.get_upload_link(session, x_event_edit_token.strip())
            if row and getattr(row, "link_type", None) == _db.LINK_TYPE_EVENT_EDIT and row.event_id == _db._event_id_str(event_id):
                if row.expires_at is not None and row.expires_at < datetime.utcnow():
                    raise HTTPException(status_code=401, detail="Event edit link expired")
                return "event_edit"
    raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_database():
    """Dependency: require database available or raise 503."""
    if not _database_available():
        raise HTTPException(status_code=503, detail="Database not configured")


# In-memory storage
_decks: list[dict] = []
_metagame_cache: dict | None = None
_events_cache: list[dict] | None = None  # cached list for GET /api/events (invalidated when events/decks change)
_player_aliases: dict[str, str] = {}  # alias -> canonical
_scrape_cancel_event: threading.Event | None = None


def _aliases_path() -> Path:
    return DATA_DIR / "player_aliases.json"


def _load_player_aliases() -> None:
    global _player_aliases
    if _database_available():
        try:
            with _db.session_scope() as session:
                _player_aliases = _db.get_player_aliases(session)
        except Exception as e:
            logger.exception("Failed to load player aliases from DB: %s", e)
            _player_aliases = {}
        return
    data = load_json(_aliases_path(), default={}, suppress_errors=True)
    _player_aliases = data or {}


def _save_player_aliases() -> None:
    if _database_available():
        try:
            with _db.session_scope() as session:
                for alias, canonical in _player_aliases.items():
                    _db.set_player_alias(session, alias, canonical)
        except Exception as e:
            logger.exception("Failed to save player aliases to DB: %s", e)
        return
    save_json(_aliases_path(), _player_aliases, indent=2, ensure_ascii=False)


def _normalize_player(name: str) -> str:
    """Return canonical player name (alias -> canonical mapping). Follows chains so nested aliases resolve."""
    if not name or not name.strip():
        return "(unknown)"
    n = name.strip()
    seen: set[str] = set()
    while n in _player_aliases and n not in seen:
        seen.add(n)
        n = (_player_aliases[n] or "").strip() or n
    return n


def _resolve_deck_player(session, d: dict) -> None:
    """Set d['player_id'] and d['player'] (display name) from d['player'] (name). Resolve via aliases/players; create player if missing."""
    name = (d.get("player") or "").strip() or "(unknown)"
    pid, display = _db.resolve_name_to_player_id(session, name)
    if pid is None:
        pid, display = _db.get_or_create_player(session, name)
    d["player_id"] = pid
    d["player"] = display


_load_player_aliases()


def _get_decks() -> list[Deck]:
    return [Deck.from_dict(d) for d in _decks]


def _get_deck_by_id(deck_id: int) -> dict | None:
    """Return deck dict by deck_id or None if not found."""
    for d in _decks:
        if d.get("deck_id") == deck_id:
            return d
    return None


def _event_from_deck_dict(d: dict) -> dict:
    """Build a normalized event dict from a deck dict."""
    return {
        "event_id": d.get("event_id"),
        "event_name": d.get("event_name", ""),
        "store": "",
        "location": "",
        "date": d.get("date", ""),
        "format_id": d.get("format_id", ""),
        "player_count": d.get("player_count", 0),
        "origin": d.get("origin", "mtgtop8"),
    }


def _events_from_decks(decks: list[dict]) -> list[dict]:
    """Derive unique events from deck dicts."""
    seen: dict[tuple[int | str, str], dict] = {}
    for d in decks:
        key = (d.get("event_id"), d.get("event_name", ""))
        if key not in seen:
            seen[key] = _event_from_deck_dict(d)
    return list(seen.values())


def _get_event_by_id_from_decks(event_id: str) -> dict | None:
    """Return event info derived from first deck with this event_id, or None (file-based fallback)."""
    for d in _decks:
        if str(d.get("event_id")) == str(event_id):
            return _event_from_deck_dict(d)
    return None


def _invalidate_metagame() -> None:
    global _metagame_cache, _events_cache
    _metagame_cache = None
    _events_cache = None


def _invalidate_events_cache() -> None:
    """Clear cached events list so next GET /api/events recomputes."""
    global _events_cache
    _events_cache = None


def _normalize_split_cards(decks: list[dict]) -> list[dict]:
    """Normalize card names in deck dicts (including split cards); archetype/commanders to front-face."""
    for d in decks:
        for section in ("mainboard", "sideboard"):
            cards = d.get(section, [])
            for card in cards:
                if isinstance(card, dict) and "card" in card:
                    card["card"] = _normalize_card_name(card["card"])
        if _db is not None:
            a = d.get("archetype")
            if a is not None and str(a).strip():
                nd = _db.normalize_archetype_display(str(a))
                if nd:
                    d["archetype"] = nd
            cmd = d.get("commanders")
            if isinstance(cmd, list):
                d["commanders"] = _db.normalize_commanders_list(cmd)
    return decks


def _normalize_card_entry(entry) -> dict | None:
    """Normalize a single card entry from dict or Pydantic model into {qty, card}."""
    if entry is None:
        return None
    if isinstance(entry, dict):
        qty = int(entry.get("qty", 1) or 1)
        raw = str(entry.get("card", ""))
    else:
        qty = int(getattr(entry, "qty", 1) or 1)
        raw = getattr(entry, "card", "") or ""
    name = _normalize_card_name(raw)
    if not name:
        return None
    return {"qty": qty, "card": name}


def _build_board(entries) -> list[dict]:
    """Normalize a list of card entries into [{qty, card}, ...], dropping empty names."""
    board: list[dict] = []
    for e in entries or []:
        normalized = _normalize_card_entry(e)
        if normalized:
            board.append(normalized)
    return board


def _normalize_commanders(commanders) -> list[str]:
    """Normalize a commanders list to normalized card-name strings."""
    if not commanders:
        return []
    return [_normalize_card_name(c) for c in commanders if _normalize_card_name(c)]


def _load_from_file(path: str) -> None:
    global _decks
    data = load_json(path, default=[], suppress_errors=False)
    _decks = _normalize_split_cards(data or [])
    _invalidate_metagame()


def _load_decks_from_db() -> None:
    """Load all decks from DB into _decks. No-op if DB not available."""
    global _decks
    if not _database_available():
        return
    try:
        with _db.session_scope() as session:
            _decks = _db.get_all_decks(session)
        _invalidate_metagame()
    except Exception as e:
        logger.exception("Failed to load decks from DB: %s", e)


def _persist_decks_to_db(decks: list[dict], origin: str = None) -> None:
    """Write decks to DB (upsert each). Resolve player name to player_id before each upsert. Then reload _decks from DB."""
    if not _database_available() or _db is None:
        return
    if origin is None:
        origin = _db.ORIGIN_MTGTOP8
    try:
        with _db.session_scope() as session:
            for d in decks:
                if "player_id" not in d:
                    _resolve_deck_player(session, d)
                _db.upsert_deck(session, d, origin=origin)
        _load_decks_from_db()
    except Exception as e:
        logger.exception("Failed to persist decks to DB: %s", e)


def _clear_decks_in_db() -> None:
    """Delete all decks in DB, then clear _decks."""
    if not _database_available() or _db is None:
        return
    try:
        with _db.session_scope() as session:
            session.query(_db.DeckRow).delete()
        global _decks
        _decks = []
        _invalidate_metagame()
    except Exception as e:
        logger.exception("Failed to clear decks in DB: %s", e)


# Load decks on startup from DB only (PostgreSQL required; no JSON fallback)
if _database_available():
    try:
        _load_decks_from_db()
    except Exception as e:
        logger.exception("Failed to load decks from DB at startup: %s", e)


_RANK_ORDER = {"1": 0, "2": 1, "3-4": 2, "5-8": 3, "9-16": 4, "17-32": 5, "33-64": 6, "65-128": 7}


def _rank_sort_value(rank_str: str) -> int:
    """Return a numeric value for ordering ranks (1, 2, 3, ..., 12, ...). Uses lower bound for ranges like 3-4."""
    r = (rank_str or "").strip()
    if not r:
        return 999
    part = r.split("-")[0].strip()
    if not part.isdigit():
        return 999
    n = int(part)
    return n if 1 <= n <= 128 else 999


def _parse_date_sortkey(date_str: str) -> str:
    """Convert DD/MM/YY to YYMMDD for sorting."""
    parts = date_str.split("/")
    if len(parts) == 3:
        return parts[2] + parts[1] + parts[0]
    return date_str


def _date_yymmdd_to_parts(key: str) -> tuple[int, int, int] | None:
    """Convert a YYMMDD sort key to (yy, mm, dd) ints, or None if invalid."""
    if not key or not key.isdigit() or len(key) != 6:
        return None
    return int(key[0:2]), int(key[2:4]), int(key[4:6])


def _yymmdd_to_ordinal(key: str) -> int | None:
    """Convert a YYMMDD key to a day-ordinal (for day arithmetic).

    Uses 2000 + yy heuristic matching the rest of the codebase, which treats
    DD/MM/YY dates as 21st-century years.
    """
    parts = _date_yymmdd_to_parts(key)
    if not parts:
        return None
    yy, mm, dd = parts
    try:
        return date(2000 + yy, mm, dd).toordinal()
    except ValueError:
        return None


def _yymmdd_to_display(key: str) -> str | None:
    """Convert a YYMMDD sort key back to DD/MM/YY display format."""
    parts = _date_yymmdd_to_parts(key)
    if not parts:
        return None
    yy, mm, dd = parts
    return f"{dd:02d}/{mm:02d}/{yy:02d}"


def _window_summary_from_dicts(deck_dicts: list[dict]) -> dict:
    """Summarize a window: deck_count, event_count, date_from, date_to."""
    if not deck_dicts:
        return {"deck_count": 0, "event_count": 0, "date_from": None, "date_to": None}
    keys = [_parse_date_sortkey(d.get("date", "") or "") for d in deck_dicts]
    valid = [k for k in keys if k.isdigit() and len(k) == 6]
    date_from = _yymmdd_to_display(min(valid)) if valid else None
    date_to = _yymmdd_to_display(max(valid)) if valid else None
    events = {str(d.get("event_id")) for d in deck_dicts if d.get("event_id") is not None}
    return {
        "deck_count": len(deck_dicts),
        "event_count": len(events),
        "date_from": date_from,
        "date_to": date_to,
    }


def _deck_sort_key(d: dict) -> tuple:
    """Sort by date descending, then rank ascending (1, 2, ..., 12, ...)."""
    date_key = _parse_date_sortkey(d.get("date", ""))
    rank_val = _rank_sort_value(d.get("rank", ""))
    return (-int(date_key) if date_key.isdigit() else 0, rank_val)


def _date_in_range(date_str: str, date_from: str | None, date_to: str | None) -> bool:
    """Check if DD/MM/YY date_str is within [date_from, date_to] (inclusive)."""
    key = _parse_date_sortkey(date_str)
    if not key.isdigit():
        return True
    key_int = int(key)
    if date_from:
        from_key = _parse_date_sortkey(date_from)
        if from_key.isdigit() and key_int < int(from_key):
            return False
    if date_to:
        to_key = _parse_date_sortkey(date_to)
        if to_key.isdigit() and key_int > int(to_key):
            return False
    return True


def _filter_decks_by_date(decks: list[dict], date_from: str | None, date_to: str | None) -> list[dict]:
    """Filter decks by date range."""
    if not date_from and not date_to:
        return decks
    return [d for d in decks if _date_in_range(d.get("date", ""), date_from, date_to)]


def _parse_event_id_filter(event_id: str | None, event_ids: str | None) -> set[str] | None:
    """Return a set of event IDs to filter by, or None for no event filter."""
    if event_ids:
        ids = {x.strip() for x in event_ids.split(",") if x.strip()}
        return ids or None
    if event_id is not None:
        return {str(event_id)}
    return None


def _filter_decks_for_query(
    decks: list[dict],
    event_id: str | None,
    event_ids: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[dict]:
    """Filter decks by event_id/event_ids and (optionally) date range.

    Behavior matches legacy endpoints:
    - If event_ids or event_id is provided, filter by those event IDs and ignore date_from/date_to.
    - Otherwise, apply date range filtering only.
    """
    id_set = _parse_event_id_filter(event_id, event_ids)
    if id_set is not None:
        return [d for d in decks if str(d.get("event_id")) in id_set]
    return _filter_decks_by_date(decks, date_from, date_to)


@app.post("/api/v1/auth/login")
def auth_login(body: LoginBody):
    """Login as admin. Returns JWT if password matches ADMIN_PASSWORD."""
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Admin login disabled (ADMIN_PASSWORD not set)")
    if body.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"token": _create_admin_token(), "user": "admin"}


@app.get("/api/v1/auth/me")
def auth_me(authorization: str | None = Header(None, alias="Authorization")):
    """Return current user if valid Bearer token, else 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if not _verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"user": "admin"}


# Feedback: create GitHub issue from app (no user GitHub account required)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()  # e.g. aleserena/metagameAnalyzer
_FEEDBACK_LABELS = {"bug", "enhancement", "question"}


@app.post("/api/v1/feedback")
def post_feedback(body: SiteFeedbackBody):
    """Create a GitHub issue from feedback form. Requires GITHUB_TOKEN and GITHUB_REPO."""
    # Honeypot: if filled, treat as bot and return fake success (do not create issue)
    if (body.website or "").strip():
        return {"url": "", "number": None}
    # Simple math captcha: expect small integers (e.g. 1–20) and answer = a + b
    a, b, ans = body.captcha_a, body.captcha_b, body.captcha_answer
    if a is None or b is None or ans is None or not (1 <= a <= 20 and 1 <= b <= 20) or a + b != ans:
        raise HTTPException(status_code=400, detail="Please solve the simple math question correctly.")
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise HTTPException(
            status_code=503,
            detail="Feedback is not configured (GITHUB_TOKEN and GITHUB_REPO must be set)",
        )
    label = (body.type or "bug").strip().lower()
    if label not in _FEEDBACK_LABELS:
        label = "question"
    title = (body.title or "").strip()
    if not title or len(title) > 256:
        raise HTTPException(status_code=400, detail="Title is required and must be at most 256 characters")
    description = (body.description or "").strip()
    if not description or len(description) > 65536:
        raise HTTPException(status_code=400, detail="Description is required and must be at most 65536 characters")
    email = (body.email or "").strip() or None
    issue_body = description
    if email:
        issue_body += f"\n\n---\n*Contact (optional): {email}*"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"title": title, "body": issue_body, "labels": [label]}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        return {"url": data.get("html_url", ""), "number": data.get("number")}
    except requests.RequestException as e:
        if hasattr(e, "response") and e.response is not None:
            try:
                err = e.response.json()
                msg = err.get("message", err.get("documentation_url", str(e)))
            except Exception:
                msg = str(e)
            logger.warning("GitHub API error creating feedback issue: %s", msg)
            raise HTTPException(status_code=502, detail=f"Could not create issue: {msg}")
        raise HTTPException(status_code=502, detail="Could not create issue. Try again later.")


@app.post("/api/v1/cards/lookup")
def cards_lookup(body: CardLookupBody):
    """Look up card metadata and images from Scryfall."""
    if not body.names:
        return {}
    return lookup_cards(body.names)


@app.get("/api/v1/cards/search")
def cards_search(q: str = Query("", description="Card name prefix for autocomplete")):
    """Return card names matching the query prefix (Scryfall autocomplete)."""
    data = autocomplete_cards(q)
    return {"data": data}


def _deck_sort_key_by(sort: str, order: str):
    """Return (key_fn, reverse) for sorting decks."""
    reverse = order == "desc"

    def key(d: dict):
        if sort == "date":
            date_key = _parse_date_sortkey(d.get("date", ""))
            val = int(date_key) if date_key.isdigit() else 0
            rv = _rank_sort_value(d.get("rank", ""))
            return (-val if reverse else val, -rv if reverse else rv)
        if sort == "rank":
            rk = _rank_sort_value(d.get("rank", ""))
            return (-rk if reverse else rk,)
        if sort == "player":
            return ((d.get("player") or "").lower(),)
        if sort == "name":
            return ((d.get("name") or "").lower(),)
        return _deck_sort_key(d)

    return key, reverse if sort in ("player", "name") else False


@app.get("/api/v1/decks")
def list_decks(
    event_id: str | None = Query(None, description="Filter by event ID (single, for backward compatibility)"),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    commander: str | None = Query(None, description="Filter by commander name (substring)"),
    deck_name: str | None = Query(None, description="Filter by deck name (substring)"),
    archetype: str | None = Query(None, description="Filter by archetype (substring)"),
    player: str | None = Query(None, description="Filter by player name (substring)"),
    player_id: int | None = Query(None, description="Filter by player ID (exact)"),
    card: str | None = Query(None, description="Filter by card name (substring, commander, mainboard or sideboard)"),
    colors: str | None = Query(
        None,
        description="Filter by commander color identity (comma-separated, e.g. 'W,U' for Azorius)",
    ),
    sort: str = Query("date", description="Sort by: date, rank, player, name"),
    order: str = Query("desc", description="Sort order: asc, desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    is_admin: str | None = Depends(optional_admin),
):
    """List decks with optional filters and pagination. When admin and event_id, includes has_email per deck."""
    filtered = _filter_decks_for_query(_decks, event_id, event_ids, None, None)
    if commander:
        c_norm = _normalize_search(commander)
        filtered = [
            d for d in filtered
            if any(c_norm in _normalize_search(c or "") for c in d.get("commanders", []))
        ]
    if deck_name:
        dn_norm = _normalize_search(deck_name)
        filtered = [d for d in filtered if dn_norm in _normalize_search(d.get("name") or "")]
    if archetype:
        arch_norm = _normalize_search(archetype)
        filtered = [
            d for d in filtered
            if arch_norm in _normalize_search(d.get("archetype") or "")
        ]
    if player:
        p_norm = _normalize_search(player)
        filtered = [
            d for d in filtered
            if p_norm in _normalize_search(d.get("player") or "")
            or p_norm in _normalize_search(_normalize_player(d.get("player") or ""))
        ]
    if player_id is not None:
        filtered = [d for d in filtered if d.get("player_id") == player_id]
    if card:
        card_norm = _normalize_search(card)
        filtered = [
            d for d in filtered
            if any(card_norm in _normalize_search(c or "") for c in d.get("commanders", []))
            or any(
                card_norm in _normalize_search((e.get("card") if isinstance(e, dict) else "") or "")
                for section in (d.get("mainboard", []), d.get("sideboard", []))
                for e in section
            )
        ]

    # Optional filter by commander-based color identity (EDH / Commander decks).
    # Also attaches color_identity (ordered WUBRG + C for colorless) to each deck for UI mana symbols.
    color_filter: set[str] | None = None
    if colors:
        wanted = {c.strip().upper() for c in colors.split(",") if c.strip()}
        valid = {"W", "U", "B", "R", "G", "C"}
        color_filter = {c for c in wanted if c in valid} or None

    try:
        if filtered:
            deck_objs = [Deck.from_dict(d) for d in filtered]
            commander_names = list(
                {c for deck in deck_objs for c in effective_commanders(deck) if c}
            )
            metadata = lookup_cards(commander_names) if commander_names else {}
            color_order = ["W", "U", "B", "R", "G", "C"]
            filtered_with_colors: list[dict] = []
            for deck_obj, d in zip(deck_objs, filtered):
                ec = effective_commanders(deck_obj)
                ci: set[str] = set()
                for name in ec:
                    entry = metadata.get(name)
                    if entry and "error" not in entry:
                        for c in entry.get("color_identity") or entry.get("colors") or []:
                            if c in {"W", "U", "B", "R", "G"}:
                                ci.add(c)
                # Treat EDH/Commander decks with no colors as colorless ("C") for filtering and display.
                is_edh = (deck_obj.format_id or "").upper() in {"EDH", "CEDH", "COMMANDER"}
                if not ci and is_edh and ec:
                    ci.add("C")
                if ci:
                    d["color_identity"] = [c for c in color_order if c in ci]
                if color_filter:
                    # Require deck to contain all selected colors.
                    if not ci or not color_filter.issubset(ci):
                        continue
                    filtered_with_colors.append(d)
            if color_filter:
                filtered = filtered_with_colors
    except Exception:
        # Color identity and color filter are cosmetic; ignore lookup failures.
        logger.exception("Color identity lookup failed for /api/decks")

    sort_val = sort if sort in ("date", "rank", "player", "name") else "date"
    order_val = order if order in ("asc", "desc") else "desc"
    key_fn, reverse = _deck_sort_key_by(sort_val, order_val)
    filtered = sorted(filtered, key=key_fn, reverse=reverse)
    total = len(filtered)
    page = filtered[skip : skip + limit]

    # Normalize player names for display (merge aliases)
    page = [{**d, "player": _normalize_player(d.get("player") or "")} for d in page]
    if is_admin == "admin" and event_id is not None and _database_available():
        players = list({d.get("player") or "" for d in page})
        with _db.session_scope() as session:
            email_map = _db.get_emails_for_players(session, players)
        for d in page:
            d["has_email"] = (d.get("player") or "") in email_map
    return {"decks": page, "total": total, "skip": skip, "limit": limit}


@app.get("/api/v1/decks/compare")
def compare_decks(ids: str = Query(..., description="Comma-separated deck IDs")):
    """Get multiple decks by ID for comparison."""
    try:
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deck IDs")
    if len(id_list) < 2 or len(id_list) > 4:
        raise HTTPException(status_code=400, detail="Provide 2 to 4 deck IDs")
    deck_map = {d.get("deck_id"): d for d in _decks}
    result = []
    for did in id_list:
        if did not in deck_map:
            raise HTTPException(status_code=404, detail=f"Deck {did} not found")
        d = dict(deck_map[did])
        d["player"] = _normalize_player(d.get("player") or "")
        result.append(d)
    return {"decks": result}


def _deck_duplicate_info(deck_id: int) -> dict | None:
    """Return duplicate info for a deck: is_duplicate, duplicate_of, same_mainboard_ids, same_mainboard_decks, primary_deck."""
    decks = [Deck.from_dict(d) for d in _decks]
    dup_map = find_duplicate_decks(decks)
    deck_map = {d.get("deck_id"): d for d in _decks}

    def deck_summary(did: int) -> dict:
        d = deck_map.get(did, {})
        return {
            "deck_id": did,
            "name": d.get("name"),
            "player": _normalize_player(d.get("player") or ""),
            "event_name": d.get("event_name"),
            "date": d.get("date"),
            "rank": d.get("rank"),
        }

    for primary, others in dup_map.items():
        if deck_id == primary:
            same_mainboard_decks = [deck_summary(did) for did in others]
            return {
                "is_duplicate": False,
                "duplicate_of": None,
                "same_mainboard_ids": others,
                "same_mainboard_decks": same_mainboard_decks,
            }
        if deck_id in others:
            primary_deck = deck_summary(primary)
            same_mainboard_ids = [x for x in others if x != deck_id]
            same_mainboard_decks = [deck_summary(did) for did in same_mainboard_ids]
            return {
                "is_duplicate": True,
                "duplicate_of": primary,
                "same_mainboard_ids": same_mainboard_ids,
                "same_mainboard_decks": same_mainboard_decks,
                "primary_deck": primary_deck,
            }
    return None


@app.get("/api/v1/decks/duplicates")
def list_duplicate_decks(
    event_ids: str | None = Query(None, description="Limit to events (comma-separated)"),
):
    """Decks with identical mainboard (duplicates across events)."""
    candidate = _filter_decks_for_query(_decks, None, event_ids, None, None)
    decks = [Deck.from_dict(d) for d in candidate]
    dup_map = find_duplicate_decks(decks)
    deck_map = {d.get("deck_id"): d for d in _decks}
    result = []
    for primary_id, duplicate_ids in dup_map.items():
        primary = deck_map.get(primary_id, {})
        result.append({
            "primary_deck_id": primary_id,
            "primary_name": primary.get("name"),
            "primary_player": _normalize_player(primary.get("player") or ""),
            "primary_event": primary.get("event_name"),
            "primary_date": primary.get("date"),
            "duplicate_deck_ids": duplicate_ids,
            "duplicates": [
                {
                    "deck_id": did,
                    "name": deck_map.get(did, {}).get("name"),
                    "player": _normalize_player(deck_map.get(did, {}).get("player") or ""),
                    "event_name": deck_map.get(did, {}).get("event_name"),
                    "date": deck_map.get(did, {}).get("date"),
                }
                for did in duplicate_ids
            ],
        })
    return {"duplicates": result}


@app.get("/api/v1/decks/{deck_id}")
def get_deck(deck_id: int):
    """Get single deck by ID."""
    d = _get_deck_by_id(deck_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deck not found")
    out = dict(d)
    out["player"] = _normalize_player(out.get("player") or "")
    dup = _deck_duplicate_info(deck_id)
    if dup:
        out["duplicate_info"] = dup
    return out


@app.get("/api/v1/decks/{deck_id}/similar")
def get_similar_decks(
    deck_id: int,
    limit: int = Query(10, ge=1, le=20),
    event_ids: str | None = Query(None, description="Limit to events (comma-separated)"),
):
    """Decks with high card overlap (same metagame)."""
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    deck = Deck.from_dict(deck_dict)
    candidate_decks = _filter_decks_for_query(_decks, None, event_ids, None, None)
    all_decks = [Deck.from_dict(d) for d in candidate_decks]
    return {"similar": similar_decks(deck, all_decks, limit=limit)}


@app.get("/api/v1/decks/{deck_id}/analysis")
def get_deck_analysis(deck_id: int):
    """Deck analysis: mana curve, color distribution, lands distribution."""
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    deck = Deck.from_dict(deck_dict)
    card_names = list({c for _, c in deck.mainboard} | {c for _, c in deck.sideboard})
    metadata = lookup_cards(card_names)
    # Ensure every deck card name has meta (case-insensitive fallback for name variants)
    merged: dict = {}
    for name in card_names:
        if name in metadata and "error" not in metadata.get(name, {}):
            merged[name] = metadata[name]
        else:
            for k, v in metadata.items():
                if "error" not in v and k.lower() == name.lower():
                    merged[name] = v
                    break
    return deck_analysis(deck, merged)


@app.get("/api/v1/date-range")
def get_date_range():
    """Return min/max dates and the latest event date from loaded decks."""
    if not _decks:
        return {"min_date": None, "max_date": None, "last_event_date": None}
    dates = [d.get("date", "") for d in _decks if d.get("date")]
    valid = [d for d in dates if _parse_date_sortkey(d).isdigit()]
    if not valid:
        return {"min_date": None, "max_date": None, "last_event_date": None}
    sorted_keys = sorted(valid, key=_parse_date_sortkey)
    max_date = sorted_keys[-1]
    return {"min_date": sorted_keys[0], "max_date": max_date, "last_event_date": max_date}


@app.get("/api/v1/format-info")
def get_format_info():
    """Return the format(s) detected from loaded decks."""
    if not _decks:
        return {"format_id": None, "format_name": None}
    format_ids = {d.get("format_id", "") for d in _decks if d.get("format_id")}
    if len(format_ids) == 1:
        fid = next(iter(format_ids))
        return {"format_id": fid, "format_name": FORMATS.get(fid, fid)}
    return {"format_id": None, "format_name": "Multiple Formats"}


def _compute_events_list() -> list[dict]:
    """Build the events list (from DB or from _decks). Used by list_events with caching."""
    if _database_available():
        try:
            with _db.session_scope() as session:
                rows = _db.get_all_events(session)
            # Rows are already in canonical event dict shape via db.event_row_to_dict
            return rows
        except Exception as e:
            logger.exception("Failed to list events from DB: %s", e)
    return _events_from_decks(_decks)


@app.get("/api/v1/events", response_model=dict)
def list_events():
    """List unique events from current data (from DB events table when DB used, else from decks). Cached until events/decks change."""
    global _events_cache
    if _events_cache is not None:
        return {"events": [EventResponse(**e) for e in _events_cache]}
    _events_cache = _compute_events_list()
    return {"events": [EventResponse(**e) for e in _events_cache]}


# --- Admin-only: events and deck management (DB required for create/update/delete) ---


@app.post("/api/v1/events", dependencies=[Depends(require_admin), Depends(require_database)], response_model=EventResponse)
def create_event(body: CreateEventBody):
    """Create a new event (admin-only). Manual events get IDs in a separate namespace from MTGTop8."""
    if not body.player_count or body.player_count < 1:
        raise HTTPException(status_code=400, detail="Number of players is required and must be at least 1")
    try:
        with _db.session_scope() as session:
            row = _db.create_event(
                session,
                event_name=body.event_name.strip() or "Unnamed",
                date=body.date.strip() or "",
                format_id=body.format_id.strip() or "EDH",
                origin=_db.ORIGIN_MANUAL,
                event_id=body.event_id,
                player_count=body.player_count,
                store=(body.store or "").strip(),
                location=(body.location or "").strip(),
            )
            _invalidate_events_cache()
            return EventResponse(**_db.event_row_to_dict(row))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Create event failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create event")


@app.get("/api/v1/events/event-ids-with-discrepancies", dependencies=[Depends(require_admin), Depends(require_database)])
def get_event_ids_with_discrepancies():
    """Return event_ids that have at least one matchup discrepancy (admin)."""
    with _db.session_scope() as session:
        rows = _db.list_all_matchups_with_event_id(session)
    by_event: dict[str, list[dict]] = {}
    for r in rows:
        eid = (r.get("event_id") or "").strip()
        if not eid:
            continue
        by_event.setdefault(eid, []).append(r)
    event_ids_with_discrepancies: list[str] = []
    for eid, event_rows in by_event.items():
        by_pair: dict[tuple[int, int], list[dict]] = {}
        for r in event_rows:
            key = tuple(sorted([r["deck_id"], r["opponent_deck_id"]]))
            by_pair.setdefault(key, []).append(r)
        for (deck_a, deck_b), matchups in by_pair.items():
            if len(matchups) != 2:
                continue
            from_a = next((m for m in matchups if m["deck_id"] == deck_a), None)
            from_b = next((m for m in matchups if m["deck_id"] == deck_b), None)
            if from_a is None or from_b is None:
                continue
            r1 = from_a.get("result") or ""
            r2 = from_b.get("result") or ""
            if not _matchup_result_consistent(r1, r2):
                event_ids_with_discrepancies.append(eid)
                break
    return {"event_ids": event_ids_with_discrepancies}


@app.get("/api/v1/events/event-ids-with-missing-decks", dependencies=[Depends(require_admin), Depends(require_database)])
def get_event_ids_with_missing_decks():
    """Return event_ids where deck count < player_count (admin)."""
    with _db.session_scope() as session:
        event_ids = _db.list_event_ids_with_missing_decks(session)
    return {"event_ids": event_ids}


@app.get("/api/v1/events/event-ids-with-missing-matchups", dependencies=[Depends(require_admin), Depends(require_database)])
def get_event_ids_with_missing_matchups():
    """Return event_ids where every deck has the expected matchups (admin). Events NOT in this list have missing matchups."""
    with _db.session_scope() as session:
        event_ids = _db.list_event_ids_with_complete_matchups(session)
    return {"event_ids": event_ids}


def _event_row_to_merge_dict(row) -> dict:
    """Event row to dict keyed by EVENT_MERGE_FIELDS (name -> event_name)."""
    return {
        "event_name": row.name or "",
        "store": row.store or "",
        "location": row.location or "",
        "date": row.date or "",
        "format_id": row.format_id or "",
        "player_count": row.player_count or 0,
    }


def _normalize_board_for_compare(board: list) -> list[tuple[str, int]]:
    """Normalize mainboard/sideboard to comparable (canonical_card, total_qty) list.
    Double-faced cards are keyed by front face so 'Norman Osborn' and 'Norman Osborn // Green Goblin' match."""
    if not board or not isinstance(board, list):
        return []
    by_canonical: dict[str, int] = {}
    for entry in board:
        if isinstance(entry, dict):
            card = (entry.get("card") or "").strip()
            qty = int(entry.get("qty", 1)) if entry.get("qty") is not None else 1
            if card:
                key = _canonical_card_key(card)
                by_canonical[key] = by_canonical.get(key, 0) + qty
    out = sorted(by_canonical.items(), key=lambda x: (x[0].lower(), x[1]))
    return out


def _boards_content_equal(board_a: list, board_b: list) -> bool:
    """True if both boards have the same cards and quantities (order ignored)."""
    return _normalize_board_for_compare(board_a) == _normalize_board_for_compare(board_b)


def _format_commanders_archetype(deck: dict) -> str:
    """Display archetype only for EDH merge conflict (commanders not shown)."""
    arch = (deck.get("archetype") or "").strip()
    if arch:
        return arch
    cmd = deck.get("commanders") or []
    if cmd:
        return ", ".join(cmd)  # fallback if no archetype
    return "—"


def _deck_merge_conflicts(deck_keep: dict, deck_remove: dict) -> list[MergeConflictItem]:
    """Compare two deck dicts on DECK_MERGE_FIELDS. Only add conflict when both have data and values differ (prefer non-empty).
    For EDH, commanders and archetype are a single combined field."""
    conflicts = []
    format_keep = (deck_keep.get("format_id") or "").strip().upper()
    format_remove = (deck_remove.get("format_id") or "").strip().upper()
    is_edh_keep = format_keep in ("EDH", "COMMANDER", "CEDH")
    is_edh_remove = format_remove in ("EDH", "COMMANDER", "CEDH")
    is_edh_both = is_edh_keep and is_edh_remove

    for field in DECK_MERGE_FIELDS:
        if is_edh_both and field in ("commanders", "archetype"):
            continue  # handled below as commanders_archetype
        v_keep = deck_keep.get(field)
        v_remove = deck_remove.get(field)
        if field == "player_count":
            v_keep = 0 if v_keep is None else int(v_keep)
            v_remove = 0 if v_remove is None else int(v_remove)
        has_keep = (v_keep not in (None, "", [])) if field != "player_count" else (v_keep is not None and v_keep != 0)
        has_remove = (v_remove not in (None, "", [])) if field != "player_count" else (v_remove is not None and v_remove != 0)
        if not has_keep or not has_remove:
            continue  # prefer the one with data; no conflict to show
        if field in ("commanders", "mainboard", "sideboard"):
            if field == "commanders":
                if v_keep != v_remove:
                    conflicts.append(MergeConflictItem(field=field, value_keep=v_keep, value_remove=v_remove))
            else:
                # mainboard/sideboard: compare content (same cards and qty = no conflict)
                if not _boards_content_equal(v_keep if isinstance(v_keep, list) else [], v_remove if isinstance(v_remove, list) else []):
                    conflicts.append(MergeConflictItem(field=field, value_keep=v_keep, value_remove=v_remove))
        else:
            s_keep = (v_keep or "").strip() if isinstance(v_keep, str) else (v_keep if v_keep is not None else "")
            s_remove = (v_remove or "").strip() if isinstance(v_remove, str) else (v_remove if v_remove is not None else "")
            if s_keep != s_remove:
                conflicts.append(MergeConflictItem(field=field, value_keep=v_keep, value_remove=v_remove))

    # EDH: single combined commanders_archetype conflict when either commanders or archetype differs
    # Archetype is a commander card; treat double-faced same as front face (e.g. Norman Osborn === Norman Osborn // Green Goblin)
    if is_edh_both:
        cmd_keep = deck_keep.get("commanders") or []
        arch_keep = (deck_keep.get("archetype") or "").strip()
        cmd_remove = deck_remove.get("commanders") or []
        arch_remove = (deck_remove.get("archetype") or "").strip()
        has_keep = bool(cmd_keep or arch_keep)
        has_remove = bool(cmd_remove or arch_remove)
        if has_keep and has_remove:
            # Compare as sets of canonical card names (front face, case-insensitive); include archetype as a commander
            set_keep = {_canonical_card_key(c) for c in cmd_keep if (c or "").strip()}
            if arch_keep:
                set_keep.add(_canonical_card_key(arch_keep))
            set_remove = {_canonical_card_key(c) for c in cmd_remove if (c or "").strip()}
            if arch_remove:
                set_remove.add(_canonical_card_key(arch_remove))
            if set_keep != set_remove:
                conflicts.append(
                    MergeConflictItem(
                        field="commanders_archetype",
                        value_keep=_format_commanders_archetype(deck_keep),
                        value_remove=_format_commanders_archetype(deck_remove),
                    )
                )
    return conflicts


@app.get(
    "/api/v1/events/merge-preview",
    dependencies=[Depends(require_admin), Depends(require_database)],
    response_model=MergePreviewResponse,
)
def merge_preview(
    event_id_a: str = Query(..., alias="event_id_a"),
    event_id_b: str = Query(..., alias="event_id_b"),
    manual_pairs: str | None = Query(None, alias="manual_pairs", description="Comma-separated keep_id-remove_id for manual deck pairs to include conflict preview"),
):
    """Preview merging two events. Cannot merge two MTGTop8 events. Prefer MTGTop8 data when merging manual + MTGTop8.
    Optional manual_pairs=deck_id_keep-deck_id_remove,... includes those pairs in deck_pairs with same validations as auto-paired."""
    with _db.session_scope() as session:
        row_a = _db.get_event(session, event_id_a)
        row_b = _db.get_event(session, event_id_b)
    if not row_a:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id_a}")
    if not row_b:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id_b}")
    if row_a.event_id == row_b.event_id:
        raise HTTPException(status_code=400, detail="Cannot merge an event with itself")

    origin_a = row_a.origin or _db.ORIGIN_MTGTOP8
    origin_b = row_b.origin or _db.ORIGIN_MTGTOP8
    if origin_a == _db.ORIGIN_MTGTOP8 and origin_b == _db.ORIGIN_MTGTOP8:
        return MergePreviewResponse(
            can_merge=False,
            error="Cannot merge two events imported from MTGTop8.",
            event_a=_db.event_row_to_dict(row_a),
            event_b=_db.event_row_to_dict(row_b),
            conflicts=[],
            merged_preview={},
            keep_event_id="",
            remove_event_id="",
        )

    # Determine which event to keep: prefer MTGTop8; if both manual, keep A remove B
    if origin_a == _db.ORIGIN_MTGTOP8 and origin_b == _db.ORIGIN_MANUAL:
        keep, remove = row_a, row_b
    elif origin_a == _db.ORIGIN_MANUAL and origin_b == _db.ORIGIN_MTGTOP8:
        keep, remove = row_b, row_a
    else:
        keep, remove = row_a, row_b

    d_keep = _event_row_to_merge_dict(keep)
    d_remove = _event_row_to_merge_dict(remove)
    merged = {}
    conflicts = []
    for field in EVENT_MERGE_FIELDS:
        v_keep = d_keep.get(field)
        v_remove = d_remove.get(field)
        # Normalize empty
        if field == "player_count":
            v_keep = 0 if v_keep is None else int(v_keep)
            v_remove = 0 if v_remove is None else int(v_remove)
        else:
            v_keep = (v_keep or "").strip() if isinstance(v_keep, str) else (v_keep or "")
            v_remove = (v_remove or "").strip() if isinstance(v_remove, str) else (v_remove or "")
        has_keep = (v_keep != "" and v_keep is not None) if field != "player_count" else (v_keep is not None and v_keep != 0)
        has_remove = (v_remove != "" and v_remove is not None) if field != "player_count" else (v_remove is not None and v_remove != 0)
        if not has_keep and has_remove:
            merged[field] = v_remove
        elif has_keep and not has_remove:
            merged[field] = v_keep
        elif has_keep and has_remove:
            if v_keep == v_remove:
                merged[field] = v_keep
            else:
                merged[field] = v_keep  # default: prefer keep (MTGTop8 when mixed)
                conflicts.append(MergeConflictItem(field=field, value_keep=v_keep, value_remove=v_remove))
        else:
            merged[field] = v_keep if field != "player_count" else 0

    # Full merged_preview for API (include event_id of kept event)
    merged_preview = {
        "event_id": keep.event_id,
        "event_name": merged["event_name"],
        "store": merged["store"],
        "location": merged["location"],
        "date": merged["date"],
        "format_id": merged["format_id"],
        "player_count": merged["player_count"],
    }

    # Player/deck pairing: same player_id in both events -> merge decks
    deck_pairs: list[DeckPairPreview] = []
    decks_keep_only: list[dict] = []
    decks_remove_only: list[dict] = []
    with _db.session_scope() as session:
        decks_keep = _db.get_decks_by_event(session, keep.event_id)
        decks_remove = _db.get_decks_by_event(session, remove.event_id)
        keep_by_player_id: dict[int, dict] = {}
        for d in decks_keep:
            pid = d.get("player_id")
            if pid is not None:
                keep_by_player_id[pid] = d
        paired_keep_ids: set[int] = set()
        paired_remove_ids: set[int] = set()
        for d in decks_remove:
            pid = d.get("player_id")
            if pid is not None and pid in keep_by_player_id:
                k = keep_by_player_id[pid]
                paired_keep_ids.add(k["deck_id"])
                paired_remove_ids.add(d["deck_id"])
                pair_conflicts = _deck_merge_conflicts(k, d)
                # Add matchups conflict only when both have matchup data and counts differ (effective = as deck + as opponent)
                n_keep = _db.count_effective_matchups_for_deck(session, k["deck_id"])
                n_remove = _db.count_effective_matchups_for_deck(session, d["deck_id"])
                if n_keep > 0 and n_remove > 0 and n_keep != n_remove:
                    pair_conflicts.append(
                        MergeConflictItem(
                            field="matchups",
                            value_keep=f"{n_keep} matchups",
                            value_remove=f"{n_remove} matchups",
                        )
                    )
                deck_pairs.append(DeckPairPreview(deck_keep=k, deck_remove=d, conflicts=pair_conflicts))
        # Manual pairs: same validations (deck, rank, matchups, etc.) as auto-paired
        if manual_pairs and manual_pairs.strip():
            keep_by_id = {d["deck_id"]: d for d in decks_keep}
            remove_by_id = {d["deck_id"]: d for d in decks_remove}
            for part in manual_pairs.strip().split(","):
                part = part.strip()
                if "-" not in part:
                    continue
                a, b = part.split("-", 1)
                try:
                    keep_id = int(a.strip())
                    remove_id = int(b.strip())
                except ValueError:
                    continue
                k = keep_by_id.get(keep_id)
                d = remove_by_id.get(remove_id)
                if not k or not d:
                    continue
                pair_conflicts = _deck_merge_conflicts(k, d)
                n_keep = _db.count_effective_matchups_for_deck(session, k["deck_id"])
                n_remove = _db.count_effective_matchups_for_deck(session, d["deck_id"])
                if n_keep > 0 and n_remove > 0 and n_keep != n_remove:
                    pair_conflicts.append(
                        MergeConflictItem(
                            field="matchups",
                            value_keep=f"{n_keep} matchups",
                            value_remove=f"{n_remove} matchups",
                        )
                    )
                deck_pairs.append(DeckPairPreview(deck_keep=k, deck_remove=d, conflicts=pair_conflicts))
        decks_keep_only = [d for d in decks_keep if d["deck_id"] not in paired_keep_ids]
        decks_remove_only = [d for d in decks_remove if d["deck_id"] not in paired_remove_ids]

    return MergePreviewResponse(
        can_merge=True,
        event_a=_db.event_row_to_dict(row_a),
        event_b=_db.event_row_to_dict(row_b),
        conflicts=conflicts,
        merged_preview=merged_preview,
        keep_event_id=keep.event_id,
        remove_event_id=remove.event_id,
        deck_pairs=deck_pairs,
        decks_keep_only=decks_keep_only,
        decks_remove_only=decks_remove_only,
    )


@app.get("/api/v1/events/{event_id}", response_model=EventResponse)
def get_event_by_id(event_id: str):
    """Get a single event by ID. Returns 404 if not found."""
    if _database_available():
        try:
            with _db.session_scope() as session:
                row = _db.get_event(session, event_id)
                if row:
                    return EventResponse(**_db.event_row_to_dict(row))
        except Exception as e:
            logger.exception("Failed to get event: %s", e)
    # Fallback: find from _decks
    ev = _get_event_by_id_from_decks(event_id)
    if ev:
        return EventResponse(**ev)
    raise HTTPException(status_code=404, detail="Event not found")


@app.get(
    "/api/v1/events/{event_id}/export",
    dependencies=[Depends(require_admin_or_event_edit)],
)
def export_event(event_id: str):
    """Export an event and all related data (decks, matchups, player emails) as JSON."""
    event_dict: dict | None = None
    decks: list[dict] = []
    matchups: list[dict] = []
    player_emails: dict[str, str] = {}
    players_list: list[dict] = []

    if _database_available():
        try:
            with _db.session_scope() as session:
                row = _db.get_event(session, event_id)
                if not row:
                    raise HTTPException(status_code=404, detail="Event not found")
                event_dict = _db.event_row_to_dict(row)
                decks = _db.get_decks_by_event(session, event_id)

                # Collect matchups for all decks in this event
                for d in decks:
                    deck_id = d.get("deck_id")
                    if deck_id is None:
                        continue
                    rows = _db.list_matchups_by_deck(session, deck_id)
                    if rows:
                        matchups.extend(rows)

                # Collect player emails only for players in this event
                players = {
                    (d.get("player") or "").strip()
                    for d in decks
                    if (d.get("player") or "").strip()
                }
                if players:
                    player_emails = _db.get_emails_for_players(session, list(players))

                # Collect distinct player_ids from decks and matchups for optional players array
                player_ids: set[int] = set()
                for d in decks:
                    pid = d.get("player_id")
                    if pid is not None:
                        player_ids.add(pid)
                for m in matchups:
                    pid = m.get("opponent_player_id")
                    if pid is not None:
                        player_ids.add(pid)
                players_list.clear()
                for pid in sorted(player_ids):
                    row = _db.get_player_by_id(session, pid)
                    if row:
                        players_list.append({"id": row.id, "display_name": row.display_name or ""})
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Failed to export event from database: %s", e)
            raise HTTPException(status_code=500, detail="Failed to export event")
    else:
        ev = _get_event_by_id_from_decks(event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        event_dict = ev
        decks = [d for d in _decks if str(d.get("event_id")) == str(event_id)]
        matchups = []
        player_emails = {}

    payload = EventExportData(
        schema_version=1,
        event=EventResponse(**event_dict),
        decks=decks,
        matchups=matchups,
        player_emails=player_emails,
        players=players_list,
    )
    filename = f"event-{event_dict['event_id']}.json"
    return JSONResponse(
        content=payload.model_dump(),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.put("/api/v1/events/{event_id}", dependencies=[Depends(require_admin_or_event_edit), Depends(require_database)])
def update_event_endpoint(
    event_id: str,
    event_name: str | None = Query(None),
    date: str | None = Query(None),
    format_id: str | None = Query(None),
    player_count: int | None = Query(None),
    store: str | None = Query(None),
    location: str | None = Query(None),
):
    """Update event metadata (admin-only)."""
    try:
        with _db.session_scope() as session:
            ok = _db.update_event(session, event_id, event_name=event_name, date=date, format_id=format_id, player_count=player_count, store=store, location=location)
        if not ok:
            raise HTTPException(status_code=404, detail="Event not found")
        _load_decks_from_db()
        _invalidate_events_cache()
        return {"event_id": event_id, "message": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Update event failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/events/{event_id}", dependencies=[Depends(require_admin), Depends(require_database)])
def delete_event_endpoint(event_id: str):
    """Delete an event and all its decks (admin-only)."""
    try:
        with _db.session_scope() as session:
            ok = _db.delete_event(session, event_id, delete_decks=True)
        if not ok:
            raise HTTPException(status_code=404, detail="Event not found")
        _load_decks_from_db()
        _invalidate_events_cache()
        return {"event_id": event_id, "message": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Delete event failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/v1/events/import",
    dependencies=[Depends(require_admin), Depends(require_database)],
)
def import_event(body: EventExportData):
    """Import a new manual event (and all decks/matchups/emails) from an exported JSON payload."""
    if body.schema_version != 1:
        raise HTTPException(status_code=400, detail=f"Unsupported schema_version: {body.schema_version}")
    if not _database_available():
        raise HTTPException(status_code=503, detail="Database is required for importing events")

    try:
        with _db.session_scope() as session:
            # Create new manual event with a fresh ID
            new_event_id = _db.next_manual_event_id(session)
            ev = body.event
            row = _db.create_event(
                session,
                event_name=(ev.event_name or "").strip() or "Unnamed",
                date=(ev.date or "").strip(),
                format_id=(ev.format_id or "").strip() or "EDH",
                origin=_db.ORIGIN_MANUAL,
                event_id=new_event_id,
                player_count=ev.player_count or 0,
                store=(ev.store or "").strip(),
                location=(ev.location or "").strip(),
            )
            event_dict = _db.event_row_to_dict(row)

            # Map old deck_ids -> new manual deck_ids
            decks_data = body.decks or []
            deck_id_map: dict[int, int] = {}
            next_deck_id = _db.next_manual_deck_id(session)
            for deck_dict_raw in decks_data:
                if "deck_id" not in deck_dict_raw:
                    raise HTTPException(status_code=400, detail="Each deck must include a 'deck_id' field")
                try:
                    old_deck_id = int(deck_dict_raw.get("deck_id"))
                except Exception:
                    raise HTTPException(status_code=400, detail="Each deck 'deck_id' must be an integer")
                new_deck_id = next_deck_id
                next_deck_id += 1
                deck_id_map[old_deck_id] = new_deck_id

                deck_data = dict(deck_dict_raw)
                deck_data["deck_id"] = new_deck_id
                deck_data["event_id"] = new_event_id
                deck_data["event_name"] = event_dict.get("event_name") or deck_data.get("event_name") or ""
                deck_data["date"] = event_dict.get("date") or deck_data.get("date") or ""
                if not deck_data.get("format_id"):
                    deck_data["format_id"] = event_dict.get("format_id", "") or "EDH"

                _resolve_deck_player(session, deck_data)
                deck_row = _db.dict_to_deck_row(deck_data, origin=_db.ORIGIN_MANUAL)
                session.add(deck_row)

            # Insert matchups, remapping deck IDs
            matchups_data = body.matchups or []
            per_deck_matchups: dict[int, list[dict]] = {}
            for m_raw in matchups_data:
                if "deck_id" not in m_raw:
                    continue
                try:
                    old_deck_id = int(m_raw.get("deck_id"))
                except Exception:
                    continue
                new_deck_id = deck_id_map.get(old_deck_id)
                if new_deck_id is None:
                    continue

                opp_old = m_raw.get("opponent_deck_id")
                new_opp_id = None
                if opp_old is not None:
                    try:
                        new_opp_id = deck_id_map.get(int(opp_old))
                    except Exception:
                        new_opp_id = None

                item = {
                    "opponent_player": (m_raw.get("opponent_player") or "").strip(),
                    "opponent_deck_id": new_opp_id,
                    "opponent_archetype": m_raw.get("opponent_archetype"),
                    "result": (m_raw.get("result") or "loss").strip() or "loss",
                    "result_note": (m_raw.get("result_note") or None),
                    "round": m_raw.get("round"),
                }
                per_deck_matchups.setdefault(new_deck_id, []).append(item)

            for deck_id, items in per_deck_matchups.items():
                _db.upsert_matchups_for_deck(session, deck_id, items)

            # Restore player emails for players in this event
            for player, email in (body.player_emails or {}).items():
                _db.set_player_email(session, player, email)

        _load_decks_from_db()
        _invalidate_events_cache()
        return {"event_id": event_dict["event_id"], "message": "imported", "deck_count": len(decks_data)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Import event failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to import event")


@app.post(
    "/api/v1/events/merge",
    dependencies=[Depends(require_admin), Depends(require_database)],
)
def merge_events(body: MergeEventsBody):
    """Merge two events: move all decks and links to the kept event, update kept event with resolved data, delete the removed event."""
    with _db.session_scope() as session:
        keep_row = _db.get_event(session, body.event_id_keep)
        remove_row = _db.get_event(session, body.event_id_remove)
    if not keep_row:
        raise HTTPException(status_code=404, detail=f"Event not found: {body.event_id_keep!r}")
    if not remove_row:
        raise HTTPException(status_code=404, detail=f"Event not found: {body.event_id_remove!r}")
    if keep_row.event_id == remove_row.event_id:
        raise HTTPException(status_code=400, detail="Cannot merge an event with itself")
    origin_keep = keep_row.origin or _db.ORIGIN_MTGTOP8
    origin_remove = remove_row.origin or _db.ORIGIN_MANUAL
    if origin_keep == _db.ORIGIN_MTGTOP8 and origin_remove == _db.ORIGIN_MTGTOP8:
        raise HTTPException(status_code=400, detail="Cannot merge two events imported from MTGTop8.")

    # Build merged same as preview (prefer keep, fill missing from remove), then apply resolutions
    d_keep = _event_row_to_merge_dict(keep_row)
    d_remove = _event_row_to_merge_dict(remove_row)
    merged = {}
    for field in EVENT_MERGE_FIELDS:
        v_keep = d_keep.get(field)
        v_remove = d_remove.get(field)
        if field == "player_count":
            v_keep = 0 if v_keep is None else int(v_keep)
            v_remove = 0 if v_remove is None else int(v_remove)
        has_keep = (v_keep not in (None, "")) if field != "player_count" else (v_keep is not None and v_keep != 0)
        has_remove = (v_remove not in (None, "")) if field != "player_count" else (v_remove is not None and v_remove != 0)
        if not has_keep and has_remove:
            merged[field] = v_remove
        elif has_keep and not has_remove:
            merged[field] = v_keep
        elif has_keep and has_remove:
            merged[field] = v_keep if body.resolutions.get(field) != "remove" else v_remove
        else:
            merged[field] = v_keep if field != "player_count" else 0
    event_name = merged.get("event_name") or ""
    date = merged.get("date") or ""
    try:
        with _db.session_scope() as session:
            decks_keep = _db.get_decks_by_event(session, keep_row.event_id)
            decks_remove = _db.get_decks_by_event(session, remove_row.event_id)
        keep_by_player_id = {}
        for d in decks_keep:
            pid = d.get("player_id")
            if pid is not None:
                keep_by_player_id[pid] = d
        auto_pairs: list[tuple[dict, dict]] = []
        paired_remove_ids: set[int] = set()
        for d in decks_remove:
            pid = d.get("player_id")
            if pid is not None and pid in keep_by_player_id:
                auto_pairs.append((keep_by_player_id[pid], d))
                paired_remove_ids.add(d["deck_id"])
        all_pairs: list[tuple[int, int]] = [(k["deck_id"], r["deck_id"]) for k, r in auto_pairs]
        for pm in body.player_merges:
            if pm.deck_id_remove not in paired_remove_ids:
                all_pairs.append((pm.deck_id_keep, pm.deck_id_remove))
                paired_remove_ids.add(pm.deck_id_remove)
        deck_keep_by_id = {d["deck_id"]: d for d in decks_keep}
        deck_remove_by_id = {d["deck_id"]: d for d in decks_remove}

        with _db.session_scope() as session:
            for (deck_id_keep, deck_id_remove) in all_pairs:
                d_keep = deck_keep_by_id.get(deck_id_keep)
                d_remove = deck_remove_by_id.get(deck_id_remove)
                if not d_keep or not d_remove:
                    continue
                key = f"{deck_id_keep}-{deck_id_remove}"
                res = body.deck_resolutions.get(key, {})
                merged_deck = dict(d_keep)
                merged_deck["event_id"] = keep_row.event_id
                merged_deck["event_name"] = event_name
                merged_deck["date"] = date
                # EDH: apply commanders_archetype resolution to both commanders and archetype
                if res.get("commanders_archetype") == "remove":
                    merged_deck["commanders"] = d_remove.get("commanders") or []
                    merged_deck["archetype"] = d_remove.get("archetype") or ""
                elif res.get("commanders_archetype") == "keep":
                    merged_deck["commanders"] = d_keep.get("commanders") or []
                    merged_deck["archetype"] = d_keep.get("archetype") or ""
                for field in DECK_MERGE_FIELDS:
                    if field in ("commanders", "archetype") and "commanders_archetype" in res:
                        continue  # already set above
                    choice = res.get(field)
                    v_keep = d_keep.get(field)
                    v_remove = d_remove.get(field)
                    if choice == "remove":
                        merged_deck[field] = v_remove if field != "player_count" else (v_remove if v_remove is not None else 0)
                        if field in ("commanders", "mainboard", "sideboard") and merged_deck[field] is None:
                            merged_deck[field] = []
                    else:
                        has_keep = (v_keep not in (None, "", [])) if field != "player_count" else (v_keep is not None)
                        merged_deck[field] = v_keep if has_keep else v_remove
                        if merged_deck[field] is None:
                            merged_deck[field] = [] if field in ("commanders", "mainboard", "sideboard") else (0 if field == "player_count" else "")
                _db.upsert_deck(session, merged_deck, origin=keep_row.origin or _db.ORIGIN_MTGTOP8)
                matchups_choice = res.get("matchups")
                if matchups_choice == "keep":
                    # Keep only kept deck's matchups; remove deck's matchups are dropped when we delete it
                    pass
                elif matchups_choice == "remove":
                    # Use only removed deck's matchups: delete keep's, then reassign remove's to keep
                    _db.delete_matchups_for_deck(session, deck_id_keep)
                    _db.reassign_matchups_to_deck(session, deck_id_remove, deck_id_keep)
                else:
                    # Merge both (default)
                    _db.reassign_matchups_to_deck(session, deck_id_remove, deck_id_keep)
                _db.delete_deck(session, deck_id_remove)

            unpaired_remove_ids = [d["deck_id"] for d in decks_remove if d["deck_id"] not in paired_remove_ids]
            for deck_id in unpaired_remove_ids:
                _db.update_deck_event(session, deck_id, keep_row.event_id, event_name, date)

            _db.update_event(
                session,
                keep_row.event_id,
                event_name=event_name,
                date=date,
                format_id=merged.get("format_id"),
                player_count=merged.get("player_count"),
                store=merged.get("store"),
                location=merged.get("location"),
            )
            _db.reassign_upload_links_to_event(session, remove_row.event_id, keep_row.event_id)
            _db.delete_event(session, remove_row.event_id, delete_decks=False)
        _load_decks_from_db()
        _invalidate_events_cache()
        decks_merged = len(all_pairs)
        decks_moved = len(unpaired_remove_ids)
        return {
            "message": "Events merged.",
            "keep_event_id": keep_row.event_id,
            "remove_event_id": remove_row.event_id,
            "decks_merged": decks_merged,
            "decks_moved": decks_moved,
        }
    except Exception as e:
        logger.exception("Merge events failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to merge events.")


@app.post("/api/v1/events/{event_id}/decks", dependencies=[Depends(require_admin), Depends(require_database)])
async def upload_decks_to_event(
    event_id: str,
    body: UploadDecksBody | None = None,
    file: UploadFile | None = File(None),
):
    """Upload decks to an existing event (admin-only). Decks are assigned this event_id and event_name/date from the event."""
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        event_name = event_display_name(ev.name, ev.store or "", ev.location or "")
        date, format_id = ev.date, ev.format_id
    if file:
        content = await _read_upload_json_bytes_async(file)
        try:
            raw = json.loads(content.decode("utf-8"))
            decks = raw if isinstance(raw, list) else raw.get("decks", [])
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    elif body and body.decks is not None:
        decks = body.decks
    else:
        raise HTTPException(status_code=400, detail="Provide JSON body with 'decks' or file upload")
    decks = _normalize_split_cards(decks)
    try:
        with _db.session_scope() as session:
            next_id = _db.next_manual_deck_id(session)
        out = []
        for i, d in enumerate(decks):
            d = dict(d)
            d["event_id"] = event_id
            d["event_name"] = event_name
            d["date"] = date
            d["format_id"] = format_id
            if "deck_id" not in d or d.get("deck_id") is None:
                d["deck_id"] = next_id + i
            out.append(d)
        with _db.session_scope() as session:
            for d in out:
                _resolve_deck_player(session, d)
                _db.upsert_deck(session, d, origin=_db.ORIGIN_MANUAL)
        _load_decks_from_db()
        return {"event_id": event_id, "loaded": len(out), "message": f"Uploaded {len(out)} decks"}
    except Exception as e:
        logger.exception("Upload decks to event failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/events/{event_id}/decks/add", dependencies=[Depends(require_admin_or_event_edit), Depends(require_database)])
def add_blank_deck_to_event(event_id: str):
    """Add one blank deck to an event (admin-only). One deck per player per event; placeholder player used if blank."""
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        eid = _db._event_id_str(event_id)
        existing = session.query(_db.DeckRow).filter(_db.DeckRow.event_id == eid).all()
        player_count = getattr(ev, "player_count", None)
        if player_count is not None and player_count > 0 and len(existing) >= player_count:
            raise HTTPException(
                status_code=400,
                detail=f"Event allows at most {player_count} deck(s). It already has {len(existing)}.",
            )
        # One deck per player_id per event. Placeholder names like "Unnamed" can resolve via aliases
        # or normalized lookup to a player who already has a deck here — pick a name whose resolved
        # player_id is not yet in this event.
        existing_player_ids = {d.player_id for d in existing}
        for n in range(5000):
            player_try = "Unnamed" if n == 0 else f"Unnamed {n}"
            tmp = {"player": player_try}
            _resolve_deck_player(session, tmp)
            if tmp["player_id"] not in existing_player_ids:
                break
        else:
            tmp = {"player": f"Unnamed_{uuid.uuid4().hex[:10]}"}
            _resolve_deck_player(session, tmp)
        event_name = event_display_name(ev.name, ev.store or "", ev.location or "")
        deck_id = _db.next_manual_deck_id(session)
        blank = {
            "deck_id": deck_id,
            "event_id": event_id,
            "event_name": event_name,
            "date": ev.date,
            "format_id": ev.format_id,
            "name": "Unnamed",
            "player": tmp["player"],
            "player_id": tmp["player_id"],
            "rank": "",
            "player_count": 0,
            "commanders": [],
            "mainboard": [],
            "sideboard": [],
        }
        _db.upsert_deck(session, blank, origin=_db.ORIGIN_MANUAL)
    _load_decks_from_db()
    return {"event_id": event_id, "deck_id": deck_id, "message": "Deck added"}


# --- One-time upload links (admin create; public submit) ---


def _upload_link_base_url(request: Request) -> str:
    """Base URL for upload links (e.g. https://app.example.com)."""
    base = os.getenv("PUBLIC_APP_URL", "").strip()
    if base:
        return base.rstrip("/")
    return str(request.base_url).rstrip("/")


def _get_validated_upload_link(
    session,
    token: str,
    *,
    expected_link_type: str | None = None,
    forbid_event_edit: bool = False,
    require_deck: bool = False,
    missing_deck_detail: str = "Feedback link has no deck",
    mark_used: bool = False,
):
    """Load and validate a one-time upload link and its event.

    Common checks:
    - Link exists and matches expected_link_type (if provided)
    - Optionally forbid event-edit links (for regular upload endpoints)
    - Optionally require an attached deck_id
    - Not already used and not expired
    - Associated event still exists
    """
    row = _db.get_upload_link(session, token)
    if not row:
        raise HTTPException(status_code=404, detail="Link not found or invalid")

    link_type = getattr(row, "link_type", _db.LINK_TYPE_DECK_UPLOAD)

    if forbid_event_edit and link_type == _db.LINK_TYPE_EVENT_EDIT:
        raise HTTPException(status_code=404, detail="Use event edit link on the event page")

    if expected_link_type and link_type != expected_link_type:
        if expected_link_type == _db.LINK_TYPE_EVENT_EDIT:
            detail = "Not an event edit link"
        elif expected_link_type == _db.LINK_TYPE_FEEDBACK:
            detail = "Not a feedback link"
        else:
            detail = "Invalid link type"
        raise HTTPException(status_code=404, detail=detail)

    if require_deck and getattr(row, "deck_id", None) is None:
        raise HTTPException(status_code=404, detail=missing_deck_detail)

    if row.used_at is not None:
        raise HTTPException(status_code=404, detail="Link already used")

    if row.expires_at is not None and row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=404, detail="Link expired")

    ev = _db.get_event(session, row.event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    if mark_used:
        _db.mark_upload_link_used(session, token)

    return row, ev


@app.post("/api/v1/events/{event_id}/upload-links", dependencies=[Depends(require_admin), Depends(require_database)])
def create_upload_links(event_id: str, request: Request, body: CreateUploadLinksBody | None = None):
    """Create one or more one-time upload links for an event (admin-only). Pass deck_id to create a link that updates that deck."""
    body = body or CreateUploadLinksBody()
    expires_at = None
    if body.expires_in_days is not None and body.expires_in_days > 0:
        expires_at = datetime.utcnow() + timedelta(days=body.expires_in_days)
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        base_url = _upload_link_base_url(request)
        links = []
        if body.type == "event_edit":
            # One-time link to edit event and decks (no delete event, no new links)
            _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_EVENT_EDIT)
            token = secrets.token_urlsafe(32)
            _db.create_upload_link(
                session, token, event_id, expires_at=expires_at, link_type=_db.LINK_TYPE_EVENT_EDIT
            )
            links.append({
                "token": token,
                "url": f"{base_url}/events/{event_id}?token={token}",
                "expires_at": expires_at.isoformat() if expires_at else None,
            })
        elif body.type == "feedback" and body.deck_id is not None:
            # One-time feedback link for this deck (Event page). Form submits to POST /api/upload/{token}/feedback
            deck_row = session.query(_db.DeckRow).filter(
                _db.DeckRow.deck_id == body.deck_id,
                _db.DeckRow.event_id == _db._event_id_str(event_id),
            ).first()
            if not deck_row:
                raise HTTPException(status_code=404, detail="Deck not found in this event")
            _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_FEEDBACK, deck_id=body.deck_id)
            token = secrets.token_urlsafe(32)
            _db.create_upload_link(
                session, token, event_id, expires_at=expires_at, deck_id=body.deck_id, link_type=_db.LINK_TYPE_FEEDBACK
            )
            links.append({
                "token": token,
                "url": f"{base_url}/upload/{token}",
                "expires_at": expires_at.isoformat() if expires_at else None,
                "deck_id": body.deck_id,
            })
        elif body.deck_id is not None:
            # One-time link to update an existing deck
            deck_row = session.query(_db.DeckRow).filter(
                _db.DeckRow.deck_id == body.deck_id,
                _db.DeckRow.event_id == _db._event_id_str(event_id),
            ).first()
            if not deck_row:
                raise HTTPException(status_code=404, detail="Deck not found in this event")
            _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_DECK_UPDATE, deck_id=body.deck_id)
            token = secrets.token_urlsafe(32)
            _db.create_upload_link(session, token, event_id, expires_at=expires_at, deck_id=body.deck_id)
            links.append({
                "token": token,
                "url": f"{base_url}/upload/{token}",
                "expires_at": expires_at.isoformat() if expires_at else None,
                "deck_id": body.deck_id,
            })
        else:
            count = max(1, min(body.count, 50))
            for _ in range(count):
                token = secrets.token_urlsafe(32)
                _db.create_upload_link(session, token, event_id, expires_at=expires_at)
                links.append({
                    "token": token,
                    "url": f"{base_url}/upload/{token}",
                    "expires_at": expires_at.isoformat() if expires_at else None,
                })
        return {"links": links}


@app.get("/api/v1/upload/{token}", dependencies=[Depends(require_database)])
def get_upload_link_info(token: str):
    """Return event info for a valid one-time upload link (public). For update links, also return current deck."""
    with _db.session_scope() as session:
        row, ev = _get_validated_upload_link(
            session,
            token,
            forbid_event_edit=True,
        )
        event_name = event_display_name(ev.name, ev.store or "", ev.location or "")
        link_type = getattr(row, "link_type", _db.LINK_TYPE_DECK_UPLOAD)
        purpose = "feedback" if link_type == _db.LINK_TYPE_FEEDBACK else "deck"
        out = {
            "event_id": row.event_id,
            "event_name": event_name,
            "format_id": ev.format_id or "",
            "date": ev.date or "",
            "mode": "update" if getattr(row, "deck_id", None) else "create",
            "purpose": purpose,
        }
        if getattr(row, "deck_id", None) is not None:
            deck = _get_deck_by_id(row.deck_id)
            if deck:
                out["deck_id"] = deck["deck_id"]
                deck_out = {
                    "deck_id": deck["deck_id"],
                    "name": deck.get("name", ""),
                    "player": deck.get("player", ""),
                    "rank": deck.get("rank", ""),
                    "mainboard": deck.get("mainboard", []),
                    "sideboard": deck.get("sideboard", []),
                    "commanders": deck.get("commanders", []),
                    "archetype": deck.get("archetype"),
                }
                if purpose == "feedback":
                    matchup_rows = _db.list_matchups_by_deck(session, row.deck_id)
                    deck_out["matchups"] = [
                        {
                            "opponent_player": m.get("opponent_player", ""),
                            "result": m.get("result", "1-1"),
                            "intentional_draw": _is_intentional_draw_result(m.get("result") or ""),
                        }
                        for m in matchup_rows
                    ]
                    # Other players in this event (for opponent dropdown), excluding this deck's player
                    current_player = (deck.get("player") or "").strip()
                    event_players_set = set()
                    for d in _decks:
                        if str(d.get("event_id")) != str(row.event_id):
                            continue
                        p = (d.get("player") or "").strip()
                        if p and p != current_player:
                            event_players_set.add(p)
                    deck_out["event_players"] = sorted(event_players_set)
                    # Matchups others reported vs this player (prepopulate: their win = our loss)
                    current_player_norm = _normalize_player((deck.get("player") or "").strip())
                    reported_against_me = _db.list_matchups_reported_against_player(
                        session, row.event_id, current_player_norm
                    )
                    inverted = []
                    for r in reported_against_me:
                        res = (r.get("result") or "").strip().lower()
                        if res == "win":
                            inv_result = "loss"
                        elif res == "loss":
                            inv_result = "win"
                        elif res == "intentional_draw_win":
                            inv_result = "intentional_draw_loss"
                        elif res == "intentional_draw_loss":
                            inv_result = "intentional_draw_win"
                        else:
                            inv_result = "draw" if res == "intentional_draw" else "draw"
                        # Use normalized name so it matches opponent dropdown (event_players / deck list)
                        reporting_player = _normalize_player((r.get("reporting_player") or "").strip())
                        if reporting_player and reporting_player != "(unknown)":
                            inverted.append({
                                "opponent_player": reporting_player,
                                "result": inv_result,
                                "intentional_draw": _is_intentional_draw_result(res),
                            })
                    deck_out["opponent_reported_matchups"] = inverted
                out["deck"] = deck_out
            else:
                out["deck_id"] = row.deck_id
                out["deck"] = None
        return out


@app.get("/api/v1/event-edit/{token}", dependencies=[Depends(require_database)])
def get_event_edit_link_info(token: str):
    """Validate a one-time event-edit link, mark it as used, and return event_id. Public (no auth)."""
    with _db.session_scope() as session:
        row, _ = _get_validated_upload_link(
            session,
            token,
            expected_link_type=_db.LINK_TYPE_EVENT_EDIT,
            mark_used=True,
        )
        return {"event_id": row.event_id}


def _validate_deck_payload(body: SubmitDeckBody) -> None:
    """Raise HTTPException if payload is invalid."""
    if not (body.player or "").strip():
        raise HTTPException(status_code=400, detail="player is required")
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    main = body.mainboard or []
    side = body.sideboard or []
    if len(main) > 500:
        raise HTTPException(status_code=400, detail="mainboard has too many entries (max 500)")
    if len(side) > 100:
        raise HTTPException(status_code=400, detail="sideboard has too many entries (max 100)")
    if not main:
        raise HTTPException(status_code=400, detail="mainboard is required and must not be empty")
    for card in main:
        if not isinstance(card, dict) or "card" not in card:
            raise HTTPException(status_code=400, detail="mainboard entries must be { qty, card }")
    if not any(str(c.get("card", "")).strip() for c in main):
        raise HTTPException(status_code=400, detail="mainboard must have at least one non-empty card")
    for card in side:
        if not isinstance(card, dict) or "card" not in card:
            raise HTTPException(status_code=400, detail="sideboard entries must be { qty, card }")


def _submit_create_with_upload_link(session, row, ev, event_name: str, body: SubmitDeckBody):
    """Create a new deck via upload link. Returns (deck_id, status_code)."""
    deck_id = _db.next_manual_deck_id(session)
    commanders = body.commanders if body.commanders is not None else []
    if not isinstance(commanders, list):
        commanders = []
    mainboard = _build_board(body.mainboard)
    sideboard = _build_board(body.sideboard)
    commanders = _normalize_commanders(commanders)
    format_id = (ev.format_id or "").upper()
    if format_id == "EDH" and not commanders and mainboard:
        commanders = [mainboard[0]["card"]]
    deck = {
        "deck_id": deck_id,
        "event_id": row.event_id,
        "event_name": event_name,
        "date": ev.date or "",
        "format_id": ev.format_id or "",
        "name": (body.name or "").strip(),
        "player": _normalize_player((body.player or "").strip()),
        "rank": (body.rank or "").strip(),
        "player_count": 0,
        "commanders": commanders,
        "mainboard": mainboard,
        "sideboard": sideboard,
    }
    deck_list = _normalize_split_cards([deck])
    _resolve_deck_player(session, deck_list[0])
    _db.upsert_deck(session, deck_list[0], origin=_db.ORIGIN_MANUAL)
    return deck_id


@app.post("/api/v1/upload/{token}", dependencies=[Depends(require_database)])
def submit_deck_with_upload_link(token: str, body: SubmitDeckBody):
    """Submit or update a deck using a one-time upload link (public). Update links modify the linked deck."""
    _validate_deck_payload(body)
    with _db.session_scope() as session:
        row, ev = _get_validated_upload_link(
            session,
            token,
            forbid_event_edit=True,
        )
        event_name = event_display_name(ev.name, ev.store or "", ev.location or "")

        deck_id = getattr(row, "deck_id", None)
        if deck_id is not None:
            # Update existing deck
            current = _get_deck_by_id(deck_id)
            if not current:
                raise HTTPException(status_code=400, detail="Deck not found")
            current = dict(current)
            commanders = body.commanders if body.commanders is not None else []
            if not isinstance(commanders, list):
                commanders = []
            mainboard = _build_board(body.mainboard)
            sideboard = _build_board(body.sideboard)
            commanders = _normalize_commanders(commanders)
            format_id = (current.get("format_id") or "").upper()
            if format_id == "EDH" and not commanders and mainboard:
                commanders = [mainboard[0]["card"]]
            current["name"] = (body.name or "").strip()
            current["player"] = _normalize_player((body.player or "").strip())
            current["rank"] = (body.rank or "").strip()
            current["mainboard"] = mainboard
            current["sideboard"] = sideboard
            current["commanders"] = commanders
            deck_list = _normalize_split_cards([current])
            _resolve_deck_player(session, deck_list[0])
            _db.upsert_deck(session, deck_list[0], origin=current.get("origin", _db.ORIGIN_MANUAL))
            _db.mark_upload_link_used(session, token)
            _load_decks_from_db()
            return {"deck_id": deck_id, "message": "Deck updated successfully"}
        else:
            # Create new deck
            deck_id = _submit_create_with_upload_link(session, row, ev, event_name, body)
            _db.mark_upload_link_used(session, token)
            _load_decks_from_db()
            return Response(
                content=json.dumps({"deck_id": deck_id, "message": "Deck submitted successfully"}),
                status_code=201,
                media_type="application/json",
            )


@app.post("/api/v1/upload/{token}/feedback", dependencies=[Depends(require_database)])
def submit_feedback_with_upload_link(token: str, body: EventFeedbackBody):
    """Submit event feedback (archetype + matchups) via one-time feedback link. Deck must exist; deck list not required."""
    if not (body.archetype or "").strip():
        raise HTTPException(status_code=400, detail="archetype is required")
    if len(body.matchups or []) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 matchups allowed")
    with _db.session_scope() as session:
        row, ev = _get_validated_upload_link(
            session,
            token,
            expected_link_type=_db.LINK_TYPE_FEEDBACK,
            require_deck=True,
            missing_deck_detail="Feedback link has no deck",
        )
        deck_id = row.deck_id
        deck_dict = _get_deck_by_id(deck_id)
        if not deck_dict:
            raise HTTPException(status_code=400, detail="Deck not found")
        deck_dict = dict(deck_dict)
        deck_dict["archetype"] = (body.archetype or "").strip()
        if body.deck_name is not None:
            deck_dict["name"] = (body.deck_name or "").strip()
        if body.rank is not None:
            deck_dict["rank"] = (body.rank or "").strip()
        _db.upsert_deck(session, deck_dict, origin=deck_dict.get("origin", _db.ORIGIN_MANUAL))
        feedback_event_id = _db._event_id_str(deck_dict.get("event_id", ""))
        matchup_rows = []
        for m in body.matchups or []:
            result_raw = (m.result or "1-1").strip().lower()
            if result_raw in ("bye", "drop"):
                opponent_player = "Bye" if result_raw == "bye" else "(drop)"
                matchup_rows.append({
                    "opponent_player": opponent_player,
                    "opponent_deck_id": None,
                    "opponent_archetype": None,
                    "result": result_raw,
                    "result_note": None,
                    "round": None,
                })
                continue
            opp_player = _normalize_player((m.opponent_player or "").strip())
            if not opp_player or opp_player == "(unknown)":
                continue
            opp_deck = _db.get_deck_by_event_and_player(session, feedback_event_id, opp_player)
            opp_deck_id = opp_deck.deck_id if opp_deck else None
            opp_archetype = _db.deck_archetype_for_deck_id(session, opp_deck_id)
            matchup_rows.append({
                "opponent_player": opp_player,
                "opponent_deck_id": opp_deck_id,
                "opponent_archetype": opp_archetype,
                "result": (m.result or "1-1").strip(),
                "result_note": None,
                "round": None,
            })
        _db.upsert_matchups_for_deck(session, deck_id, matchup_rows)
        _db.mark_upload_link_used(session, token)
    _load_decks_from_db()
    return {"deck_id": deck_id, "message": "Feedback submitted successfully"}


@app.post("/api/v1/upload/{token}/decklist", dependencies=[Depends(require_database)])
def submit_decklist_with_upload_link(token: str, body: DeckListBody):
    """Update deck list (mainboard/sideboard/commanders) via one-time feedback link. Does not mark the link as used."""
    with _db.session_scope() as session:
        row, _ = _get_validated_upload_link(
            session,
            token,
            expected_link_type=_db.LINK_TYPE_FEEDBACK,
            require_deck=True,
            missing_deck_detail="No deck linked",
        )
        deck_id = row.deck_id
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    mainboard = _build_board(body.mainboard)
    if not mainboard:
        raise HTTPException(status_code=400, detail="mainboard must have at least one card")
    sideboard = _build_board(body.sideboard)
    commanders = _normalize_commanders(body.commanders or [])
    current = dict(deck_dict)
    current["mainboard"] = mainboard
    current["sideboard"] = sideboard
    current["commanders"] = commanders if commanders else None
    if (current.get("format_id") or "").upper() == "EDH" and not current.get("commanders") and current.get("mainboard"):
        current["commanders"] = [current["mainboard"][0]["card"]]
    try:
        with _db.session_scope() as session:
            _db.upsert_deck(session, current, origin=current.get("origin", _db.ORIGIN_MTGTOP8))
    except Exception as e:
        logger.exception("Deck list update failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    _load_decks_from_db()
    return {"deck_id": deck_id, "message": "Deck list updated"}


@app.put("/api/v1/decks/{deck_id}", dependencies=[Depends(require_admin_or_event_edit_deck), Depends(require_database)])
def update_deck_endpoint(deck_id: int, body: UpdateDeckBody):
    """Update deck metadata (admin-only)."""
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    current = dict(deck_dict)
    # DB player row before this edit (used to merge away Unnamed* rows when renaming to a real player)
    prior_player_id = deck_dict.get("player_id")
    # Merge body into current
    if body.name is not None:
        current["name"] = body.name
    if body.player is not None:
        current["player"] = _normalize_player(body.player.strip())
        # deck_dict always includes player_id; force re-resolve so player_id matches the new name
        current.pop("player_id", None)
    if body.rank is not None:
        current["rank"] = body.rank
    if body.archetype is not None:
        current["archetype"] = body.archetype
    if body.event_id is not None:
        with _db.session_scope() as session:
            ev = _db.get_event(session, body.event_id)
            if not ev:
                raise HTTPException(status_code=400, detail="Event not found")
            current["event_id"] = _db._event_id_str(body.event_id)
            current["event_name"] = event_display_name(ev.name, ev.store or "", ev.location or "")
            current["date"] = ev.date
            current["format_id"] = ev.format_id
    if body.commanders is not None:
        current["commanders"] = _normalize_commanders(body.commanders)
    if body.mainboard is not None:
        current["mainboard"] = _build_board(body.mainboard)
    if body.sideboard is not None:
        current["sideboard"] = _build_board(body.sideboard)
    # EDH: if no commander present, use first mainboard card as commander
    if (current.get("format_id") or "").upper() == "EDH" and not current.get("commanders") and current.get("mainboard"):
        current["commanders"] = [current["mainboard"][0]["card"]]
    # No duplicate player per event: another deck in same event cannot have the same player_id
    event_id = current.get("event_id")
    try:
        with _db.session_scope() as session:
            if "player_id" not in current:
                _resolve_deck_player(session, current)
            new_pid = current.get("player_id")
            if event_id and (body.player is not None or current.get("player")):
                if new_pid is not None:
                    event_decks = _db.get_decks_by_event(session, event_id)
                    for d in event_decks:
                        if d.get("deck_id") != deck_id and d.get("player_id") == new_pid:
                            raise HTTPException(
                                status_code=400,
                                detail="Player already in this event. Each player can only have one deck per event.",
                            )
            # Drop orphan Unnamed* PlayerRow: GET /players/id/{id} shows decks.player (denormalized), not
            # players.display_name, so renames looked correct while the placeholder row lingered.
            if (
                body.player is not None
                and prior_player_id is not None
                and new_pid is not None
                and prior_player_id != new_pid
                and _db.player_row_is_unnamed_placeholder(session, prior_player_id)
            ):
                _db.merge_players(
                    session,
                    prior_player_id,
                    new_pid,
                    canonical_name=(current.get("player") or "").strip() or None,
                )
                current["player_id"] = new_pid
                to_row = _db.get_player_by_id(session, new_pid)
                if to_row and (to_row.display_name or "").strip():
                    current["player"] = to_row.display_name
            if new_pid is not None:
                _db.sync_matchup_opponent_identity_for_deck(
                    session, deck_id, new_pid, current.get("player", "")
                )
            _db.upsert_deck(session, current, origin=current.get("origin", _db.ORIGIN_MTGTOP8))
        _load_decks_from_db()
        return {"deck_id": deck_id, "message": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Update deck failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/decks/{deck_id}", dependencies=[Depends(require_admin_or_event_edit_deck), Depends(require_database)])
def delete_deck_endpoint(deck_id: int):
    """Delete a single deck (admin-only)."""
    try:
        with _db.session_scope() as session:
            ok = _db.delete_deck(session, deck_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Deck not found")
        _load_decks_from_db()
        return {"deck_id": deck_id, "message": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Delete deck failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/decks/{deck_id}/matchups", dependencies=[Depends(require_admin_or_event_edit_deck), Depends(require_database)])
def get_deck_matchups(deck_id: int):
    """List matchups for a deck (admin or event-edit). Also returns opponent_reported_matchups:
    matchups others reported vs this deck's player (inverted: their win = our loss), for prepopulating the form."""
    deck = _get_deck_by_id(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    event_id = str(deck.get("event_id", ""))
    current_player = (deck.get("player") or "").strip()
    with _db.session_scope() as session:
        rows = _db.list_matchups_by_deck(session, deck_id)
        opponent_reported_matchups = []
        if event_id and current_player:
            # Use normalized current player so we match MatchupRow.opponent_player (stored normalized)
            current_player_norm = _normalize_player(current_player)
            reported_against_me = _db.list_matchups_reported_against_player(session, event_id, current_player_norm)
            for r in reported_against_me:
                res = (r.get("result") or "").strip().lower()
                if res == "win":
                    inv_result = "loss"
                elif res == "loss":
                    inv_result = "win"
                elif res == "intentional_draw_win":
                    inv_result = "intentional_draw_loss"
                elif res == "intentional_draw_loss":
                    inv_result = "intentional_draw_win"
                else:
                    inv_result = "draw" if res == "intentional_draw" else "draw"
                # Use normalized name so it matches opponent dropdown (deck list uses normalized player)
                reporting_player = _normalize_player((r.get("reporting_player") or "").strip())
                if reporting_player and reporting_player != "(unknown)":
                    opponent_reported_matchups.append({
                        "opponent_player": reporting_player,
                        "result": inv_result,
                        "intentional_draw": _is_intentional_draw_result(res),
                    })
    return {"matchups": rows, "opponent_reported_matchups": opponent_reported_matchups}


@app.put("/api/v1/decks/{deck_id}/matchups", dependencies=[Depends(require_admin_or_event_edit_deck), Depends(require_database)])
def update_deck_matchups(deck_id: int, body: AdminMatchupsBody):
    """Replace all matchups for a deck (admin or event-edit)."""
    deck_dict = _get_deck_by_id(deck_id)
    if not deck_dict:
        raise HTTPException(status_code=404, detail="Deck not found")
    if len(body.matchups or []) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 matchups allowed")
    event_id = str(deck_dict.get("event_id", ""))
    if not event_id:
        raise HTTPException(status_code=400, detail="Deck has no event")
    with _db.session_scope() as session:
        matchup_rows = []
        seen_opponent_round: set[tuple[str, int | None]] = set()
        for m in body.matchups or []:
            result_raw = (m.result or "draw").strip().lower()
            if result_raw in ("bye", "drop"):
                # Bye and drop don't require an opponent; count as a round for validation
                opponent_player = "Bye" if result_raw == "bye" else "(drop)"
                matchup_rows.append({
                    "opponent_player": opponent_player,
                    "opponent_deck_id": None,
                    "opponent_archetype": None,
                    "result": result_raw,
                    "result_note": None,
                    "round": None,
                })
                continue
            opp_player = _normalize_player((m.opponent_player or "").strip())
            if not opp_player or opp_player == "(unknown)":
                continue
            round_num = getattr(m, "round", None)
            key = (opp_player, round_num)
            if key in seen_opponent_round:
                continue
            seen_opponent_round.add(key)
            opp_deck = _db.get_deck_by_event_and_player(session, event_id, opp_player)
            opp_deck_id = opp_deck.deck_id if opp_deck else None
            opp_archetype = _db.deck_archetype_for_deck_id(session, opp_deck_id)
            matchup_rows.append({
                "opponent_player": opp_player,
                "opponent_deck_id": opp_deck_id,
                "opponent_archetype": opp_archetype,
                "result": (m.result or "draw").strip(),
                "result_note": None,
                "round": round_num,
            })
        _db.upsert_matchups_for_deck(session, deck_id, matchup_rows)
    _load_decks_from_db()
    return {"deck_id": deck_id, "message": "Matchups updated"}


def _parse_moxfield_board(obj) -> list[dict]:
    """Turn Moxfield board (dict of id -> {quantity/qty, card: {name} or string}) into [{qty, card}]."""
    if not obj:
        return []
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            if not isinstance(v, dict):
                continue
            qty = v.get("quantity") or v.get("qty", 1) or 1
            try:
                qty = max(1, int(qty) if isinstance(qty, (int, float)) else 1)
            except (TypeError, ValueError):
                qty = 1
            card = v.get("card")
            if card is None:
                continue
            if isinstance(card, dict):
                name = (card.get("name") or card.get("cardName") or "").strip()
            else:
                name = str(card or "").strip()
            if name:
                out.append({"qty": qty, "card": name})
    return out


def _parse_moxfield_commanders(obj) -> list[str]:
    """Turn Moxfield commanders into list of card names."""
    entries = _parse_moxfield_board(obj)
    return [e["card"] for e in entries for _ in range(e["qty"])]


@app.post("/api/v1/decks/import-moxfield", dependencies=[Depends(require_admin)])
def import_moxfield_deck(body: ImportMoxfieldBody):
    """Fetch a public Moxfield deck by URL and return commanders, mainboard, sideboard for the editor."""
    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    match = re.search(r"moxfield\.com/decks/([a-zA-Z0-9_-]+)", url, re.IGNORECASE)
    if not match:
        match = re.match(r"^([a-zA-Z0-9_-]+)$", url.strip())
    deck_id = match.group(1) if match else None
    if not deck_id:
        raise HTTPException(status_code=400, detail="Invalid Moxfield URL or deck ID")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.moxfield.com/",
    }
    # Try v2 first; some environments get 403 (e.g. Cloudflare). v3 may work as fallback.
    urls_to_try = [
        f"https://api.moxfield.com/v2/decks/all/{deck_id}",
        f"https://api.moxfield.com/v3/decks/all/{deck_id}",
    ]
    data = None
    last_error = None
    for api_url in urls_to_try:
        try:
            r = requests.get(api_url, timeout=15, headers=headers)
            if r.status_code == 403:
                last_error = "Moxfield blocked the request (403)."
                continue
            r.raise_for_status()
            data = r.json()
            break
        except requests.RequestException as e:
            last_error = str(e)
            logger.warning("Moxfield fetch %s failed: %s", api_url, e)
            continue
    if data is None:
        logger.warning("Moxfield import failed for deck %s: %s", deck_id, last_error)
        raise HTTPException(
            status_code=502,
            detail="Could not fetch deck from Moxfield. The deck may be private, or Moxfield may be blocking requests. Try again later or paste the deck list manually (Export from Moxfield → Moxfield format).",
        )
    try:
        commanders = _parse_moxfield_commanders(data.get("commanders"))
        mainboard = _parse_moxfield_board(data.get("mainboard"))
        sideboard = _parse_moxfield_board(data.get("sideboard"))
        return {
            "commanders": commanders,
            "mainboard": mainboard,
            "sideboard": sideboard,
            "name": (data.get("name") or "").strip() or None,
            "format": (data.get("format") or "").strip() or None,
        }
    except (ValueError, TypeError) as e:
        logger.warning("Moxfield parse error for deck %s: %s", deck_id, e)
        raise HTTPException(status_code=502, detail="Invalid response from Moxfield")


@app.get("/api/v1/metagame")
def get_metagame(
    placement_weighted: bool = Query(False),
    ignore_lands: bool = Query(False),
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    event_id: str | None = Query(None, description="Filter by event ID (single, backward compat)"),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    top8_only: bool = Query(False, description="Only include decks that made top 8"),
    include_top8_breakdown: bool = Query(False, description="Also return summary_top8 and archetype_distribution_top8"),
):
    """Full metagame report."""
    if not _decks:
        out = {
            "summary": {"total_decks": 0, "unique_players": 0, "unique_archetypes": 0},
            "commander_distribution": [],
            "archetype_distribution": [],
            "color_distribution": [],
            "color_count_distribution": [],
            "top_cards_main": [],
            "top_players": [],
            "placement_weighted": placement_weighted,
            "ignore_lands": ignore_lands,
        }
        if include_top8_breakdown:
            out["summary_top8"] = {"total_decks": 0, "unique_players": 0, "unique_archetypes": 0}
            out["archetype_distribution_top8"] = []
        return out
    filtered = _filter_decks_for_query(_decks, event_id, event_ids, date_from, date_to)
    decks_all = [Deck.from_dict(d) for d in filtered]
    if top8_only:
        decks = [d for d in decks_all if is_top8(d.rank)]
    else:
        decks = decks_all
    ignore_lands_cards = set(settings_service.get_ignore_lands_cards()) if ignore_lands else None
    rank_weights = settings_service.get_rank_weights()
    result = analyze(
        decks,
        placement_weighted=placement_weighted,
        ignore_lands=ignore_lands,
        ignore_lands_cards=ignore_lands_cards,
        rank_weights=rank_weights,
    )
    if include_top8_breakdown:
        decks_top8 = [d for d in decks_all if is_top8(d.rank)]
        report_top8 = analyze(
            decks_top8,
            placement_weighted=placement_weighted,
            ignore_lands=ignore_lands,
            ignore_lands_cards=ignore_lands_cards,
            rank_weights=rank_weights,
        )
        result["summary_top8"] = report_top8["summary"]
        result["archetype_distribution_top8"] = report_top8["archetype_distribution"]
    # Most played colors: each deck counts for each of its colors (multicolor = counted in each)
    _COLOR_LABEL = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
    _COLOR_ORDER = ["W", "U", "B", "R", "G", "Colorless"]
    commander_names = list({c for d in decks for c in effective_commanders(d) if c})
    lookup = lookup_cards(commander_names) if commander_names else {}
    color_counts: dict[str, int] = {k: 0 for k in _COLOR_ORDER}
    # Per-color commander counts (or weighted score) for tooltip "top decks in this color"
    color_deck_scores: dict[str, dict[str, float]] = {k: {} for k in _COLOR_ORDER}
    # Decks by number of colors (0=colorless, 1=mono, 2=2-color, ...)
    color_count_buckets: dict[int, float] = {n: 0.0 for n in range(6)}
    # Per color-count commander scores for tooltip "top decks in this bucket"
    color_count_deck_scores: dict[int, dict[str, float]] = {n: {} for n in range(6)}
    # Per-archetype color identity derived from commanders (for UI mana symbols).
    archetype_color_sets: dict[str, set[str]] = {}

    for d in decks:
        ec = effective_commanders(d)
        if not ec:
            continue
        ci: set[str] = set()
        for name in ec:
            entry = lookup.get(name)
            if entry and "error" not in entry:
                for c in entry.get("color_identity") or entry.get("colors") or []:
                    if c in _COLOR_LABEL:
                        ci.add(c)
        is_colorless = len(ci) == 0
        if is_colorless:
            color_counts["Colorless"] += 1
            colors_for_deck = ["Colorless"]
        else:
            for c in ci:
                color_counts[c] += 1
            colors_for_deck = list(ci)

        # Track colors per archetype for archetype list UI.
        arch = (d.archetype or "").strip()
        if arch:
            s = archetype_color_sets.setdefault(arch, set())
            if is_colorless:
                s.add("C")
            else:
                for c in ci:
                    s.add(c)
        w = rank_weights.get(normalize_rank(d.rank or ""), 1.0) if placement_weighted else 1.0
        commander_key = " / ".join(sorted(ec))
        for c in colors_for_deck:
            color_deck_scores[c][commander_key] = color_deck_scores[c].get(commander_key, 0.0) + w
        n_colors = 0 if len(ci) == 0 else len(ci)
        color_count_buckets[n_colors] += w
        color_count_deck_scores[n_colors][commander_key] = color_count_deck_scores[n_colors].get(commander_key, 0.0) + w
    total = sum(color_counts.values())
    _COLOR_COUNT_LABELS = {0: "Colorless", 1: "Monocolor", 2: "2-color", 3: "3-color", 4: "4-color", 5: "5-color"}
    color_count_total = sum(color_count_buckets.values()) or 1
    _MAX_TOP_DECKS_PER_COLOR = 5
    result["color_count_distribution"] = [
        {
            "label": _COLOR_COUNT_LABELS[n],
            "count": round(color_count_buckets[n], 1),
            "pct": round(100 * color_count_buckets[n] / color_count_total, 1),
            "top_decks": [
                {"name": name, "count": round(cnt, 1)}
                for name, cnt in sorted(color_count_deck_scores[n].items(), key=lambda x: -x[1])[
                    :_MAX_TOP_DECKS_PER_COLOR
                ]
            ],
        }
        for n in range(6)
        if color_count_buckets[n] > 0
    ]
    result["color_distribution"] = [
        {
            "color": _COLOR_LABEL.get(k, k),
            "count": color_counts[k],
            "pct": round(100 * color_counts[k] / total, 1) if total else 0,
            "top_decks": [
                {"name": name, "count": round(cnt, 1)}
                for name, cnt in sorted(
                    color_deck_scores[k].items(), key=lambda x: -x[1]
                )[: _MAX_TOP_DECKS_PER_COLOR]
            ],
        }
        for k in _COLOR_ORDER
        if color_counts[k] > 0
    ]

    # Attach commander-based color identity to archetype_distribution entries so the
    # frontend can render mana symbols and filter by color without extra calls.
    if "archetype_distribution" in result and archetype_color_sets:
        color_code_order = ["W", "U", "B", "R", "G", "C"]
        for row in result["archetype_distribution"]:
            arch = (row.get("archetype") or "").strip()
            colors = archetype_color_sets.get(arch)
            if not colors:
                continue
            ordered = [c for c in color_code_order if c in colors]
            if ordered:
                row["colors"] = ordered
    full_leaderboard = player_leaderboard(
        decks, normalize_player=_normalize_player, rank_weights=rank_weights
    )
    result["top_players"] = full_leaderboard[:5]
    # Unique players must match leaderboard (alias-aware): count distinct canonical players
    result["summary"]["unique_players"] = len(full_leaderboard)
    return result


@app.get("/api/v1/archetypes/{archetype_name:path}/weekly-stats")
def get_archetype_weekly_stats(
    archetype_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    event_id: str | None = Query(None),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
):
    """Week-over-week popularity and top-8 conversion for this archetype.

    Returns one row per ISO week in which the archetype has at least one deck,
    plus the total deck count across all archetypes that week (for share %).
    """
    if not _decks:
        raise HTTPException(status_code=404, detail="No data loaded")
    decoded = unquote(archetype_name)
    if (decoded or "").strip().lower() == "(unknown)":
        raise HTTPException(status_code=404, detail="Archetype not found")
    want_key = _db.archetype_canonical_key(decoded)
    scoped = _filter_decks_for_query(_decks, event_id, event_ids, date_from, date_to)

    def _week_key(d: dict) -> str | None:
        key = _parse_date_sortkey(d.get("date", "") or "")
        parts = _date_yymmdd_to_parts(key)
        if not parts:
            return None
        yy, mm, dd = parts
        try:
            dt = date(2000 + yy, mm, dd)
        except ValueError:
            return None
        iso = dt.isocalendar()
        return f"{iso[0]:04d}-W{iso[1]:02d}"

    def _week_monday(week_label: str) -> str | None:
        try:
            yr, wk = week_label.split("-W")
            dt = date.fromisocalendar(int(yr), int(wk), 1)
            return f"{dt.day:02d}/{dt.month:02d}/{dt.year % 100:02d}"
        except Exception:
            return None

    total_per_week: dict[str, int] = {}
    archetype_per_week: dict[str, int] = {}
    top8_per_week: dict[str, int] = {}
    matched_any = False
    for d in scoped:
        wk = _week_key(d)
        if wk is None:
            continue
        total_per_week[wk] = total_per_week.get(wk, 0) + 1
        if _db.archetype_canonical_key(d.get("archetype")) == want_key:
            matched_any = True
            archetype_per_week[wk] = archetype_per_week.get(wk, 0) + 1
            if is_top8(d.get("rank") or ""):
                top8_per_week[wk] = top8_per_week.get(wk, 0) + 1
    if not matched_any:
        raise HTTPException(status_code=404, detail="Archetype not found or no decks in range")

    weeks = sorted(archetype_per_week.keys())
    out = []
    for wk in weeks:
        a = archetype_per_week.get(wk, 0)
        t = total_per_week.get(wk, 0)
        t8 = top8_per_week.get(wk, 0)
        share = round(100 * a / t, 1) if t else 0.0
        top8_rate = round(100 * t8 / a, 1) if a else 0.0
        out.append({
            "week": wk,
            "week_start": _week_monday(wk),
            "archetype_decks": a,
            "archetype_top8": t8,
            "total_decks": t,
            "share_pct": share,
            "top8_rate_pct": top8_rate,
        })

    display_arch = _db.normalize_archetype_display(decoded.strip()) or decoded.strip()
    return {
        "archetype": display_arch,
        "weeks": out,
    }


@app.get("/api/v1/archetypes/{archetype_name:path}/card-trends")
def get_archetype_card_trends(
    archetype_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    event_id: str | None = Query(None),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    ignore_lands: bool = Query(False),
    recency_mode: str = Query("events", pattern="^(events|days|ratio|custom)$"),
    recency_value: int = Query(3, ge=1, le=365),
    recent_from: str | None = Query(None, description="DD/MM/YY; used when recency_mode=custom"),
    recent_to: str | None = Query(None, description="DD/MM/YY; used when recency_mode=custom"),
    min_recent_play_rate: float = Query(20.0, ge=0.0, le=100.0),
    max_older_play_rate: float = Query(5.0, ge=0.0, le=100.0),
    limit: int = Query(20, ge=1, le=200),
):
    """Return cards newly appearing and cards falling out of this archetype.

    Splits the archetype's scoped decks into a "recent" window and an "older"
    window (per `recency_mode`) and compares per-card play rates.
    """
    import math

    if not _decks:
        raise HTTPException(status_code=404, detail="No data loaded")
    decoded = unquote(archetype_name)
    if (decoded or "").strip().lower() == "(unknown)":
        raise HTTPException(status_code=404, detail="Archetype not found")
    want_key = _db.archetype_canonical_key(decoded)
    filtered = _filter_decks_for_query(_decks, event_id, event_ids, date_from, date_to)
    filtered = [
        d for d in filtered
        if _db.archetype_canonical_key(d.get("archetype")) == want_key
    ]
    if not filtered:
        raise HTTPException(status_code=404, detail="Archetype not found or no decks in range")

    sorted_dicts = sorted(
        filtered,
        key=lambda d: _parse_date_sortkey(d.get("date", "") or "") or "",
    )
    total = len(sorted_dicts)

    warning: str | None = None
    recent_dicts: list[dict] = []
    older_dicts: list[dict] = []

    if recency_mode == "events":
        event_latest: dict[str, str] = {}
        for d in sorted_dicts:
            eid = str(d.get("event_id"))
            k = _parse_date_sortkey(d.get("date", "") or "")
            if not k.isdigit():
                continue
            if eid not in event_latest or k > event_latest[eid]:
                event_latest[eid] = k
        ordered_events = sorted(event_latest.items(), key=lambda kv: kv[1])
        n = max(1, min(recency_value, len(ordered_events)))
        recent_event_ids = {eid for eid, _ in ordered_events[-n:]}
        recent_dicts = [d for d in sorted_dicts if str(d.get("event_id")) in recent_event_ids]
        older_dicts = [d for d in sorted_dicts if str(d.get("event_id")) not in recent_event_ids]
        if ordered_events and n >= len(ordered_events):
            warning = "No older events to compare against."
    elif recency_mode == "days":
        max_ord = None
        for d in sorted_dicts:
            o = _yymmdd_to_ordinal(_parse_date_sortkey(d.get("date", "") or ""))
            if o is not None and (max_ord is None or o > max_ord):
                max_ord = o
        if max_ord is None:
            warning = "Deck dates could not be parsed."
            recent_dicts = list(sorted_dicts)
        else:
            cutoff = max_ord - recency_value
            for d in sorted_dicts:
                o = _yymmdd_to_ordinal(_parse_date_sortkey(d.get("date", "") or ""))
                if o is None:
                    older_dicts.append(d)
                elif o >= cutoff:
                    recent_dicts.append(d)
                else:
                    older_dicts.append(d)
    elif recency_mode == "ratio":
        pct = max(1, min(recency_value, 99))
        take = max(1, math.ceil(total * pct / 100))
        take = min(take, total)
        older_dicts = sorted_dicts[: total - take]
        recent_dicts = sorted_dicts[total - take:]
    else:  # custom
        if not recent_from and not recent_to:
            raise HTTPException(
                status_code=400,
                detail="recency_mode=custom requires recent_from or recent_to",
            )
        for d in sorted_dicts:
            if _date_in_range(d.get("date", "") or "", recent_from, recent_to):
                recent_dicts.append(d)
            else:
                older_dicts.append(d)

    if not recent_dicts:
        warning = warning or "No decks in the recent window."
    if not older_dicts:
        warning = warning or "No decks in the older window; nothing to compare against."

    ignore_lands_cards = (
        set(settings_service.get_ignore_lands_cards()) if ignore_lands else None
    )
    rank_weights = settings_service.get_rank_weights()

    def _rates_for(dicts: list[dict]) -> dict[str, dict]:
        if not dicts:
            return {}
        decks_objs = [Deck.from_dict(d) for d in dicts]
        top = top_cards_main(
            decks_objs,
            placement_weighted=False,
            ignore_lands=ignore_lands,
            ignore_lands_cards=ignore_lands_cards,
            rank_weights=rank_weights,
            include_basic_lands=True,
        )
        return {row["card"]: row for row in top}

    recent_map = _rates_for(recent_dicts)
    older_map = _rates_for(older_dicts)

    all_cards = set(recent_map.keys()) | set(older_map.keys())

    new_cards: list[dict] = []
    legacy_cards: list[dict] = []
    for card in all_cards:
        r = recent_map.get(card) or {}
        o = older_map.get(card) or {}
        r_rate = float(r.get("play_rate_pct") or 0.0)
        o_rate = float(o.get("play_rate_pct") or 0.0)
        r_decks = int(r.get("decks") or 0)
        o_decks = int(o.get("decks") or 0)
        if r_rate >= min_recent_play_rate and o_rate <= max_older_play_rate:
            new_cards.append({
                "card": card,
                "recent_play_rate_pct": round(r_rate, 1),
                "older_play_rate_pct": round(o_rate, 1),
                "delta_pct": round(r_rate - o_rate, 1),
                "recent_decks": r_decks,
                "older_decks": o_decks,
            })
        if o_rate >= min_recent_play_rate and r_rate <= max_older_play_rate:
            legacy_cards.append({
                "card": card,
                "recent_play_rate_pct": round(r_rate, 1),
                "older_play_rate_pct": round(o_rate, 1),
                "delta_pct": round(o_rate - r_rate, 1),
                "recent_decks": r_decks,
                "older_decks": o_decks,
            })

    new_cards.sort(key=lambda x: (-x["delta_pct"], -x["recent_play_rate_pct"], x["card"]))
    legacy_cards.sort(key=lambda x: (-x["delta_pct"], -x["older_play_rate_pct"], x["card"]))
    new_cards = new_cards[:limit]
    legacy_cards = legacy_cards[:limit]

    display_arch = _db.normalize_archetype_display(decoded.strip()) or decoded.strip()
    return {
        "archetype": display_arch,
        "recent": _window_summary_from_dicts(recent_dicts),
        "older": _window_summary_from_dicts(older_dicts),
        "new_cards": new_cards,
        "legacy_cards": legacy_cards,
        "warning": warning,
    }


@app.get("/api/v1/archetypes/{archetype_name:path}")
def get_archetype_detail(
    archetype_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    event_id: str | None = Query(None, description="Filter by event ID (single)"),
    event_ids: str | None = Query(None, description="Filter by event IDs (comma-separated)"),
    ignore_lands: bool = Query(False),
):
    """Archetype detail: average analysis and top cards for decks with this archetype."""
    if not _decks:
        raise HTTPException(status_code=404, detail="No data loaded")
    decoded = unquote(archetype_name)
    if (decoded or "").strip().lower() == "(unknown)":
        raise HTTPException(status_code=404, detail="Archetype not found")
    want_key = _db.archetype_canonical_key(decoded)
    filtered = _filter_decks_for_query(_decks, event_id, event_ids, date_from, date_to)
    filtered = [
        d for d in filtered
        if _db.archetype_canonical_key(d.get("archetype")) == want_key
    ]
    if not filtered:
        raise HTTPException(status_code=404, detail="Archetype not found or no decks in range")
    decks = [Deck.from_dict(d) for d in filtered]
    card_names = set()
    for d in decks:
        for _, c in d.mainboard:
            card_names.add(c)
        for _, c in d.sideboard:
            card_names.add(c)
        # Include archetype (commander) for empty EDH decks so we fetch metadata
        if not d.mainboard and (d.format_id or "").upper() in ("EDH", "COMMANDER", "CEDH") and (d.archetype or "").strip():
            card_names.add((d.archetype or "").strip())
    metadata = lookup_cards(list(card_names))
    merged: dict = {}
    for name in card_names:
        if name in metadata and "error" not in metadata.get(name, {}):
            merged[name] = metadata[name]
        else:
            for k, v in metadata.items():
                if "error" not in v and k.lower() == name.lower():
                    merged[name] = v
                    break
    ignore_lands_cards = set(settings_service.get_ignore_lands_cards()) if ignore_lands else None
    rank_weights = settings_service.get_rank_weights()
    average_analysis = archetype_aggregate_analysis(decks, merged)
    top_main = top_cards_main(
        decks,
        placement_weighted=False,
        ignore_lands=ignore_lands,
        ignore_lands_cards=ignore_lands_cards,
        rank_weights=rank_weights,
        include_basic_lands=True,
    )
    top_players = player_leaderboard(
        decks, normalize_player=_normalize_player, rank_weights=rank_weights
    )[:10]
    typical_list = card_stat_buckets(
        decks,
        ignore_lands=ignore_lands,
        ignore_lands_cards=ignore_lands_cards,
        include_basic_lands=True,
    )
    deck_count_top8 = sum(1 for d in decks if is_top8(d.rank))
    display_arch = _db.normalize_archetype_display(decoded.strip()) or decoded.strip()
    return {
        "archetype": display_arch,
        "deck_count": len(decks),
        "deck_count_top8": deck_count_top8,
        "average_analysis": average_analysis,
        "top_cards_main": top_main,
        "top_players": top_players,
        "typical_list": typical_list,
    }


@app.get("/api/v1/settings/ignore-lands-cards")
def get_ignore_lands_cards(_: str = Depends(require_admin)):
    """Return list of card names excluded when 'Ignore lands' is checked (admin-only)."""
    return {"cards": settings_service.get_ignore_lands_cards()}


@app.put("/api/v1/settings/ignore-lands-cards")
def put_ignore_lands_cards(body: IgnoreLandsCardsBody, _: str = Depends(require_admin)):
    """Update list of cards excluded when 'Ignore lands' is checked (admin-only)."""
    return {"cards": settings_service.set_ignore_lands_cards(body.cards)}


@app.get("/api/v1/settings/rank-weights")
def get_rank_weights(_: str = Depends(require_admin)):
    """Return points per placement (1st, 2nd, 3-4, etc.). Admin-only."""
    return {"weights": settings_service.get_rank_weights()}


@app.put("/api/v1/settings/rank-weights")
def put_rank_weights(body: RankWeightsBody, _: str = Depends(require_admin)):
    """Update points per placement (admin-only)."""
    return {"weights": settings_service.set_rank_weights(body.weights)}


@app.get("/api/v1/settings/matchups-min-matches", dependencies=[Depends(require_admin), Depends(require_database)])
def get_matchups_min_matches_setting():
    """Legacy stored setting; the Matchups page uses ``GET /matchups/summary?min_matches=`` instead."""
    return {"value": settings_service.get_matchups_min_matches()}


@app.put("/api/v1/settings/matchups-min-matches", dependencies=[Depends(require_admin), Depends(require_database)])
def put_matchups_min_matches_setting(body: MatchupsMinMatchesBody):
    """Legacy stored setting (e.g. scripts); summary endpoints do not read this value."""
    n = settings_service.set_matchups_min_matches(body.value)
    return {"value": n}


@app.get("/api/v1/settings/matchups-players-min-matches", dependencies=[Depends(require_admin), Depends(require_database)])
def get_matchups_players_min_matches_setting():
    """Legacy stored setting; the Matchups page uses ``GET /matchups/players-summary?min_matches=`` instead."""
    return {"value": settings_service.get_matchups_players_min_matches()}


@app.put("/api/v1/settings/matchups-players-min-matches", dependencies=[Depends(require_admin), Depends(require_database)])
def put_matchups_players_min_matches_setting(body: MatchupsMinMatchesBody):
    """Legacy stored setting (e.g. scripts); players-summary does not read this value."""
    n = settings_service.set_matchups_players_min_matches(body.value)
    return {"value": n}


@app.post("/api/v1/settings/clear-cache")
def post_clear_scryfall_cache(_: str = Depends(require_admin)):
    """Clear Scryfall card lookup cache (in-memory and .scryfall_cache.json). Admin-only."""
    clear_scryfall_cache()
    return {"message": "Scryfall cache cleared"}


@app.post("/api/v1/settings/clear-decks", dependencies=[Depends(require_database)])
def post_clear_decks(_: str = Depends(require_admin)):
    """Clear all decks in the database. Admin-only. Requires PostgreSQL."""
    global _decks
    _decks = []
    _invalidate_metagame()
    _clear_decks_in_db()
    return {"message": "Decks cleared"}


@app.get("/api/v1/settings/upload-links")
def get_settings_upload_links(_: str = Depends(require_admin), __: None = Depends(require_database)):
    """List all one-time upload links (admin-only). Requires database."""
    with _db.session_scope() as session:
        links = _db.get_all_upload_links(session)
    return {"links": links}


@app.delete("/api/v1/settings/upload-links")
def delete_settings_upload_links(
    used_only: bool = Query(False, description="If true, only delete links that have been used"),
    _: str = Depends(require_admin),
    __: None = Depends(require_database),
):
    """Clear one-time upload links (admin-only). used_only=true clears only used links. Requires database."""
    with _db.session_scope() as session:
        deleted = _db.delete_all_upload_links(session, used_only=used_only)
    return {"deleted": deleted, "message": f"Cleared {deleted} link(s)"}


@app.put("/api/v1/player-emails", dependencies=[Depends(require_admin), Depends(require_database)])
def put_player_email(body: PlayerEmailBody):
    """Set or replace the email for a player (admin-only). Empty email deletes. Response never contains email."""
    player = (body.player or "").strip()
    if not player:
        raise HTTPException(status_code=400, detail="player is required")
    canonical = _normalize_player(player)
    with _db.session_scope() as session:
        _db.set_player_email(session, canonical, body.email or "")
    return {"ok": True}


@app.post("/api/v1/players/{player_name:path}/send-missing-deck-links", dependencies=[Depends(require_admin), Depends(require_database)])
def send_player_missing_deck_links(player_name: str, request: Request):
    """Email one-time deck upload links for all of this player's missing (empty) decks. Uses DB-stored email. 503 if email not configured."""
    try:
        from api import email as _email
    except ImportError:
        raise HTTPException(status_code=503, detail="Email not configured")
    if not _email.is_email_configured():
        raise HTTPException(
            status_code=503,
            detail="Email not configured: set Brevo SMTP (SMTP_HOST, SMTP_USER, SMTP_PASSWORD) or Brevo API (BREVO_API_KEY + SMTP_FROM). See .env.example.",
        )
    name = (player_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Player name required")
    canonical = _resolve_player_name_to_canonical(name)
    players_to_match = [canonical] + [k for k, v in _player_aliases.items() if v == canonical]
    base_url = _upload_link_base_url(request)
    with _db.session_scope() as session:
        addr = _db.get_player_email(session, canonical)
        if not addr or not addr.strip():
            raise HTTPException(status_code=400, detail="No email set for this player. Set email on this page first.")
        decks = session.query(_db.DeckRow).filter(_db.DeckRow.player.in_(players_to_match)).all()
        missing = []
        for d in decks:
            main = getattr(d, "mainboard", None) or []
            if not (isinstance(main, list) and len(main) > 0):
                missing.append(d)
        if not missing:
            return {"sent": 0, "message": "No missing decks for this player"}
        links_by_event = {}
        for deck_row in missing:
            eid = deck_row.event_id
            _db.invalidate_upload_links_for_slot(session, eid, _db.LINK_TYPE_DECK_UPDATE, deck_id=deck_row.deck_id)
            token = secrets.token_urlsafe(32)
            _db.create_upload_link(
                session, token, eid, deck_id=deck_row.deck_id, link_type=_db.LINK_TYPE_DECK_UPDATE
            )
            url = f"{base_url}/upload/{token}"
            if eid not in links_by_event:
                ev = _db.get_event(session, eid)
                event_name = event_display_name(
                    ev.name or "", getattr(ev, "store", "") or "", getattr(ev, "location", "") or ""
                ) if ev else eid
                links_by_event[eid] = {"event_name": event_name, "links": []}
            links_by_event[eid]["links"].append(url)
        body_parts = ["You have missing deck lists. Use the link(s) below (each is one-time):", ""]
        for eid, info in links_by_event.items():
            body_parts.append(f"{info['event_name']}:")
            for url in info["links"]:
                body_parts.append(url)
            body_parts.append("")
        subject = "Deck upload links (missing decks)"
        body = "\n".join(body_parts).strip()
        try:
            _email.send_email(addr, subject, body)
        except Exception as e:
            logger.exception("Send player missing-deck email failed for %s", canonical)
            raise HTTPException(status_code=500, detail="Failed to send email") from e
        return {"sent": 1}


@app.post("/api/v1/events/{event_id}/send-missing-deck-links", dependencies=[Depends(require_admin), Depends(require_database)])
def send_missing_deck_links(event_id: str, request: Request):
    """Email one-time deck links to players with missing (empty) decks. Uses DB-stored emails only. 503 if email not configured."""
    try:
        from api import email as _email
    except ImportError:
        raise HTTPException(status_code=503, detail="Email not configured")
    if not _email.is_email_configured():
        raise HTTPException(
            status_code=503,
            detail="Email not configured: set Brevo SMTP (SMTP_HOST, SMTP_USER, SMTP_PASSWORD) or Brevo API (BREVO_API_KEY + SMTP_FROM). See .env.example.",
        )
    base_url = _upload_link_base_url(request)
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        decks = session.query(_db.DeckRow).filter(_db.DeckRow.event_id == _db._event_id_str(event_id)).all()
        missing_by_player = {}
        for d in decks:
            main = getattr(d, "mainboard", None) or []
            if not (isinstance(main, list) and len(main) > 0):
                p = (d.player or "").strip()
                if p not in missing_by_player:
                    missing_by_player[p] = []
                missing_by_player[p].append(d)
        players = list(missing_by_player.keys())
        if not players:
            return {"sent": 0, "failed": []}
        email_map = _db.get_emails_for_players(session, players)
        sent = 0
        failed = []
        for canonical, addr in email_map.items():
            deck_list = missing_by_player.get(canonical, [])
            if not deck_list or not addr:
                continue
            links_for_player = []
            for deck_row in deck_list:
                _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_DECK_UPDATE, deck_id=deck_row.deck_id)
                token = secrets.token_urlsafe(32)
                _db.create_upload_link(
                    session, token, event_id, deck_id=deck_row.deck_id, link_type=_db.LINK_TYPE_DECK_UPDATE
                )
                links_for_player.append(f"{base_url}/upload/{token}")
            event_name = event_display_name(ev.name or "", getattr(ev, "store", "") or "", getattr(ev, "location", "") or "")
            subject = f"Deck upload link: {event_name}"
            body = f"Please submit your deck list for {event_name}.\n\nUse this link (one-time):\n\n" + "\n".join(links_for_player)
            try:
                _email.send_email(addr, subject, body)
                sent += 1
            except Exception:
                logger.exception("Send missing-deck email failed for %s", canonical)
                failed.append(canonical)
        return {"sent": sent, "failed": failed}


@app.post("/api/v1/events/{event_id}/send-feedback-links", dependencies=[Depends(require_admin), Depends(require_database)])
def send_feedback_links(event_id: str, request: Request):
    """Email one feedback link per deck to each player (DB-stored emails only). 503 if email not configured."""
    try:
        from api import email as _email
    except ImportError:
        raise HTTPException(status_code=503, detail="Email not configured")
    if not _email.is_email_configured():
        raise HTTPException(
            status_code=503,
            detail="Email not configured: set Brevo SMTP (SMTP_HOST, SMTP_USER, SMTP_PASSWORD) or Brevo API (BREVO_API_KEY + SMTP_FROM). See .env.example.",
        )
    base_url = _upload_link_base_url(request)
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        decks = session.query(_db.DeckRow).filter(_db.DeckRow.event_id == _db._event_id_str(event_id)).all()
        if not decks:
            return {"sent": 0}
        players = list({(d.player or "").strip() for d in decks})
        email_map = _db.get_emails_for_players(session, players)
        sent = 0
        for deck_row in decks:
            canonical = (deck_row.player or "").strip()
            addr = email_map.get(canonical)
            if not addr:
                continue
            _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_FEEDBACK, deck_id=deck_row.deck_id)
            token = secrets.token_urlsafe(32)
            _db.create_upload_link(
                session, token, event_id, deck_id=deck_row.deck_id, link_type=_db.LINK_TYPE_FEEDBACK
            )
            event_name = event_display_name(ev.name or "", getattr(ev, "store", "") or "", getattr(ev, "location", "") or "")
            subject = f"Event feedback: {event_name}"
            body = f"Please submit your match results for {event_name}.\n\nLink (one-time): {base_url}/upload/{token}"
            try:
                _email.send_email(addr, subject, body)
                sent += 1
            except Exception:
                logger.exception("Send feedback email failed for %s", canonical)
        return {"sent": sent}


@app.post("/api/v1/events/{event_id}/send-feedback-link-to-player", dependencies=[Depends(require_admin), Depends(require_database)])
def send_feedback_link_to_player(event_id: str, request: Request, body: SendFeedbackLinkToPlayerBody):
    """Email one feedback link to a single player for this event. Invalidates any previous feedback link for that player's deck. 503 if email not configured."""
    try:
        from api import email as _email
    except ImportError:
        raise HTTPException(status_code=503, detail="Email not configured")
    if not _email.is_email_configured():
        raise HTTPException(
            status_code=503,
            detail="Email not configured: set Brevo SMTP (SMTP_HOST, SMTP_USER, SMTP_PASSWORD) or Brevo API (BREVO_API_KEY + SMTP_FROM). See .env.example.",
        )
    player = (body.player or "").strip()
    if not player:
        raise HTTPException(status_code=400, detail="player is required")
    canonical = _normalize_player(player)
    base_url = _upload_link_base_url(request)
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        deck_row = _db.get_deck_by_event_and_player(session, event_id, canonical)
        if not deck_row:
            raise HTTPException(status_code=404, detail="No deck for this player in this event")
        addr = _db.get_player_email(session, canonical)
        if not addr or not addr.strip():
            raise HTTPException(status_code=400, detail="No email set for this player. Set email on the player's page first.")
        _db.invalidate_upload_links_for_slot(session, event_id, _db.LINK_TYPE_FEEDBACK, deck_id=deck_row.deck_id)
        token = secrets.token_urlsafe(32)
        _db.create_upload_link(
            session, token, event_id, deck_id=deck_row.deck_id, link_type=_db.LINK_TYPE_FEEDBACK
        )
        event_name = event_display_name(ev.name or "", getattr(ev, "store", "") or "", getattr(ev, "location", "") or "")
        subject = f"Event feedback: {event_name}"
        body_text = f"Please submit your match results for {event_name}.\n\nLink (one-time): {base_url}/upload/{token}"
        try:
            _email.send_email(addr, subject, body_text)
        except Exception as e:
            logger.exception("Send feedback email failed for %s", canonical)
            raise HTTPException(status_code=500, detail="Failed to send email") from e
    return {"sent": 1}


def _matchup_result_to_canonical(result: str) -> str:
    """Map result string to canonical win/loss/draw/intentional_draw/bye/drop for consistency check."""
    r = (result or "").strip().lower()
    if r in ("bye", "drop"):
        return r
    if r in ("intentional_draw", "id"):
        return "intentional_draw"
    if r == "intentional_draw_win":
        return "win"
    if r == "intentional_draw_loss":
        return "loss"
    if r in ("2-1", "1-0"):
        return "win"
    if r in ("1-2", "0-1"):
        return "loss"
    if r in ("1-1", "0-0"):
        return "draw"
    if r in ("win", "loss", "draw"):
        return r
    return "draw"


def _is_intentional_draw_result(result: str) -> bool:
    """True if result is any intentional-draw variant (stored as distinct state; used as win/loss/draw in calcs)."""
    r = (result or "").strip().lower()
    return r in ("intentional_draw", "intentional_draw_win", "intentional_draw_loss")


def _front_face_name(name: str) -> str:
    """Dual-faced style 'Front // Back' -> 'Front'. Unifies e.g. Norman Osborn and Norman Osborn // Green Goblin."""
    s = (name or "").strip()
    if not s or s in ("Bye", "(drop)"):
        return s or "(unknown)"
    if " // " in s:
        return s.split(" // ", 1)[0].strip() or s
    return s


def _matchup_result_consistent(result_a: str, result_b: str) -> bool:
    """True if the pair is consistent: one win + one loss, or both draw/intentional_draw. Bye/drop have no pair."""
    a = _matchup_result_to_canonical(result_a)
    b = _matchup_result_to_canonical(result_b)
    if a in ("bye", "drop") or b in ("bye", "drop"):
        return True
    if a in ("draw", "intentional_draw") and b in ("draw", "intentional_draw"):
        return True
    if (a == "win" and b == "loss") or (a == "loss" and b == "win"):
        return True
    return False


def _parse_deck_date(s: str) -> tuple[int, int, int] | None:
    """Parse DD/MM/YY or DD/MM/YYYY to (year, month, day) for comparison. Returns None if invalid."""
    if not s or not s.strip():
        return None
    parts = s.strip().split("/")
    if len(parts) != 3:
        return None
    try:
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        if year < 100:
            year += 2000 if year < 50 else 1900
        if 1 <= month <= 12 and 1 <= day <= 31:
            return (year, month, day)
    except (ValueError, IndexError):
        pass
    return None


def _date_in_range(deck_date_str: str, from_date: str | None, to_date: str | None) -> bool:
    if not from_date and not to_date:
        return True
    parsed = _parse_deck_date(deck_date_str)
    if not parsed:
        return True
    y, m, d = parsed
    if from_date:
        f = _parse_deck_date(from_date)
        if not f:
            try:
                from datetime import datetime as _dt
                _d = _dt.fromisoformat(from_date.replace("Z", "+00:00")[:10])
                f = (_d.year, _d.month, _d.day)
            except Exception:
                f = None
        if f and (y, m, d) < f:
            return False
    if to_date:
        t = _parse_deck_date(to_date)
        if not t:
            try:
                from datetime import datetime as _dt
                _d = _dt.fromisoformat(to_date.replace("Z", "+00:00")[:10])
                t = (_d.year, _d.month, _d.day)
            except Exception:
                t = None
        if t and (y, m, d) > t:
            return False
    return True


@app.get("/api/v1/matchups/summary", dependencies=[Depends(require_database)], tags=["Matchups"])
def get_matchups_summary(
    format_id: str | None = Query(None),
    event_ids: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    archetype: list[str] | None = Query(None, description="Filter by archetype(s); repeated param per name; include matchups where both deck and opponent archetype are in this list"),
    min_matches: int = Query(0, ge=0, le=1_000_000, description="Minimum aggregated matches per archetype pair to include in list and matrix"),
    include_opponents_below_min: bool = Query(
        False,
        description="When min_matches > 0, still include pairs with at least one match but fewer than min_matches (matrix + list)",
    ),
):
    """Aggregated matchup summary by archetype. Optional filters.

    Query parameters:
    - format_id: filter by format (e.g. EDH)
    - event_ids: comma-separated event IDs
    - date_from/date_to: DD/MM/YY range filter
    - min_matches: hide pairs with fewer than this many aggregated matches (default 0)
    - include_opponents_below_min: if true and min_matches > 0, also show pairs with 1 .. min_matches-1 games
    """
    with _db.session_scope() as session:
        rows = _db.list_matchups_with_deck_info(session)

    event_id_set = None
    if event_ids:
        event_id_set = {x.strip() for x in event_ids.split(",") if x.strip()}

    archetype_set = None
    if archetype:
        archetype_set = {x.strip().lower() for x in archetype if (x or "").strip()}

    filtered = []
    for r in rows:
        if format_id and (r.get("format_id") or "").strip().upper() != format_id.strip().upper():
            continue
        if event_id_set is not None and (r.get("event_id") or "").strip() not in event_id_set:
            continue
        if not _date_in_range(r.get("date") or "", date_from, date_to):
            continue
        if archetype_set is not None:
            arch = (r.get("archetype") or "").strip()
            opp = (r.get("opponent_archetype") or "").strip()
            if arch.lower() not in archetype_set:
                continue
            # When multiple archetypes selected: only matchups between those archetypes. When single: show that archetype vs all.
            if len(archetype_set) > 1 and opp.lower() not in archetype_set:
                continue
        # Bye and drop count as rounds for validation but are not used in matchup calculations
        if (r.get("result") or "").strip().lower() in ("bye", "drop"):
            continue
        filtered.append(r)

    # One canonical display name per case-insensitive archetype to avoid duplicate matrix rows
    canonical_archetype: dict[str, str] = {}
    for r in filtered:
        for raw in [(r.get("archetype") or "").strip(), (r.get("opponent_archetype") or "").strip()]:
            if raw and raw.lower() not in ("bye", "drop"):
                canonical_archetype.setdefault(raw.lower(), raw)

    def to_effective_wld(row):
        raw = (row.get("result") or "loss").strip().lower()
        if raw == "intentional_draw":
            return (0, 0, 1)
        if raw == "intentional_draw_win":
            return (1, 0, 0)
        if raw == "intentional_draw_loss":
            return (0, 1, 0)
        canonical = _matchup_result_to_canonical(row.get("result") or "loss")
        if canonical == "win":
            return (1, 0, 0)
        if canonical == "loss":
            return (0, 1, 0)
        return (0, 0, 1)  # draw

    def norm_arch(name: str) -> str:
        return canonical_archetype.get((name or "").lower(), name or "(unknown)")

    def add_to_agg(arch: str, opp: str, wins: int, losses: int, draws: int, is_intentional_draw: bool, matches: int):
        arch, opp = norm_arch(arch), norm_arch(opp)
        for (a, o), (aw, al, ad) in [((arch, opp), (wins, losses, draws)), ((opp, arch), (losses, wins, draws))]:
            key = (a.lower(), o.lower())
            if key not in agg:
                agg[key] = {"wins": 0, "losses": 0, "draws": 0, "intentional_draws": 0, "matches": 0, "archetype": a, "opponent_archetype": o}
            agg[key]["wins"] += aw
            agg[key]["losses"] += al
            agg[key]["draws"] += ad
            if is_intentional_draw:
                agg[key]["intentional_draws"] += 1
            agg[key]["matches"] += matches

    agg = {}
    # Rows we can pair by (deck_id, opponent_deck_id) for consistent A vs B / B vs A
    paired_rows = [r for r in filtered if r.get("opponent_deck_id") is not None]
    unpaired_rows = [r for r in filtered if r.get("opponent_deck_id") is None]

    by_match: dict[tuple[int, int], list[dict]] = {}
    for r in paired_rows:
        key = tuple(sorted([r["deck_id"], r["opponent_deck_id"]]))
        by_match.setdefault(key, []).append(r)

    for match_key, match_rows in by_match.items():
        d_a, d_b = match_key
        from_ab = [r for r in match_rows if (r["deck_id"], r["opponent_deck_id"]) == (d_a, d_b)]
        from_ba = [r for r in match_rows if (r["deck_id"], r["opponent_deck_id"]) == (d_b, d_a)]
        from_ab.sort(key=lambda x: (x.get("round") or 0, x.get("deck_id")))
        from_ba.sort(key=lambda x: (x.get("round") or 0, x.get("deck_id")))
        n_paired = min(len(from_ab), len(from_ba))
        for i in range(n_paired):
            ra, rb = from_ab[i], from_ba[i]
            c1 = _matchup_result_to_canonical((ra.get("result") or "").strip())
            c2 = _matchup_result_to_canonical((rb.get("result") or "").strip())
            if (c1 == "win" and c2 == "loss") or (c1 == "loss" and c2 == "win") or (c1 in ("draw", "intentional_draw") and c2 in ("draw", "intentional_draw")):
                row = ra
            else:
                row = ra
            arch = (row.get("archetype") or "(unknown)").strip()
            opp = (row.get("opponent_archetype") or "(unknown)").strip()
            wins, losses, draws = to_effective_wld(row)
            is_id = _is_intentional_draw_result(row.get("result") or "")
            add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)
        for i in range(n_paired, len(from_ab)):
            row = from_ab[i]
            arch = (row.get("archetype") or "(unknown)").strip()
            opp = (row.get("opponent_archetype") or "(unknown)").strip()
            wins, losses, draws = to_effective_wld(row)
            is_id = _is_intentional_draw_result(row.get("result") or "")
            add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)
        for i in range(n_paired, len(from_ba)):
            row = from_ba[i]
            arch = (row.get("archetype") or "(unknown)").strip()
            opp = (row.get("opponent_archetype") or "(unknown)").strip()
            wins, losses, draws = to_effective_wld(row)
            is_id = _is_intentional_draw_result(row.get("result") or "")
            add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)

    for r in unpaired_rows:
        arch = (r.get("archetype") or "(unknown)").strip()
        opp = (r.get("opponent_archetype") or "(unknown)").strip()
        wins, losses, draws = to_effective_wld(r)
        is_id = _is_intentional_draw_result(r.get("result") or "")
        add_to_agg(arch, opp, wins, losses, draws, is_id, matches=1)

    def _pair_included_in_summary(mcount: int) -> bool:
        if mcount <= 0:
            return False
        if min_matches <= 0:
            return True
        if mcount >= min_matches:
            return True
        return include_opponents_below_min

    list_out = []
    for (_arch_lower, _opp_lower), v in agg.items():
        if not _pair_included_in_summary(v["matches"]):
            continue
        wr = (v["wins"] + 0.5 * v["draws"]) / v["matches"] if v["matches"] else 0
        list_out.append({
            "archetype": v["archetype"],
            "opponent_archetype": v["opponent_archetype"],
            "wins": v["wins"],
            "losses": v["losses"],
            "draws": v["draws"],
            "intentional_draws": v["intentional_draws"],
            "matches": v["matches"],
            "win_rate": round(wr, 4),
        })

    archetypes_sorted = sorted({r["archetype"] for r in list_out} | {r["opponent_archetype"] for r in list_out})
    matrix = []
    for i, a in enumerate(archetypes_sorted):
        row = []
        for j, b in enumerate(archetypes_sorted):
            if i == j:
                row.append(None)
                continue
            key = (a.lower(), b.lower())
            v = agg.get(key, {"matches": 0, "wins": 0, "draws": 0})
            if not _pair_included_in_summary(v["matches"]):
                row.append(None)
                continue
            wr = (v["wins"] + 0.5 * v["draws"]) / v["matches"] if v["matches"] else None
            row.append(round(wr, 4) if wr is not None else None)
        matrix.append(row)

    return {
        "list": list_out,
        "archetypes": archetypes_sorted,
        "matrix": matrix,
        "min_matches": min_matches,
        "include_opponents_below_min": include_opponents_below_min,
    }


@app.get("/api/v1/matchups/players-summary", dependencies=[Depends(require_database)], tags=["Matchups"])
def get_matchups_players_summary(
    format_id: str | None = Query(None),
    event_ids: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    player: list[str] | None = Query(None),
    min_matches: int = Query(0, ge=0, le=1_000_000, description="Minimum aggregated matches per player pair to include in list and matrix"),
    include_opponents_below_min: bool = Query(
        False,
        description="When min_matches > 0, still include pairs with at least one match but fewer than min_matches (matrix + list)",
    ),
):
    """Aggregated matchup summary by player. Optional filters."""
    with _db.session_scope() as session:
        rows = _db.list_matchups_with_deck_and_players(session)

    event_id_set = None
    if event_ids:
        event_id_set = {x.strip() for x in event_ids.split(",") if x.strip()}

    filtered = []
    for r in rows:
        if format_id and (r.get("format_id") or "").strip().upper() != format_id.strip().upper():
            continue
        if event_id_set is not None and (r.get("event_id") or "").strip() not in event_id_set:
            continue
        if not _date_in_range(r.get("date") or "", date_from, date_to):
            continue
        if (r.get("result") or "").strip().lower() in ("bye", "drop"):
            continue
        filtered.append(r)

    def to_effective_wld(row):
        raw = (row.get("result") or "loss").strip().lower()
        if raw == "intentional_draw":
            return (0, 0, 1)
        if raw == "intentional_draw_win":
            return (1, 0, 0)
        if raw == "intentional_draw_loss":
            return (0, 1, 0)
        canonical = _matchup_result_to_canonical(row.get("result") or "loss")
        if canonical == "win":
            return (1, 0, 0)
        if canonical == "loss":
            return (0, 1, 0)
        return (0, 0, 1)

    # Aggregate by (player, opponent_player). Use front-face name so "Norman Osborn" and
    # "Norman Osborn // Green Goblin" are one row (dual-faced names unified across the app).
    agg: dict[tuple[str, str], dict] = {}
    for r in filtered:
        if r.get("opponent_player_id") is None:
            continue
        pname = (r.get("player") or "(unknown)").strip()
        opp = (r.get("opponent_player") or "(unknown)").strip()
        player_canonical = _front_face_name(pname)
        opp_canonical = _front_face_name(opp)
        key = (player_canonical.lower(), opp_canonical.lower())
        if key not in agg:
            agg[key] = {
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "intentional_draws": 0,
                "matches": 0,
                "player": player_canonical,
                "opponent_player": opp_canonical,
            }
        wins, losses, draws = to_effective_wld(r)
        agg[key]["wins"] += wins
        agg[key]["losses"] += losses
        agg[key]["draws"] += draws
        if _is_intentional_draw_result(r.get("result") or ""):
            agg[key]["intentional_draws"] += 1
        agg[key]["matches"] += 1

    # Canonical display names (first occurrence)
    canonical_player: dict[str, str] = {}
    for (pl, op), v in agg.items():
        for raw in [v["player"], v["opponent_player"]]:
            if raw and raw.lower() not in ("bye", "drop"):
                canonical_player.setdefault(raw.lower(), raw)

    def norm_player(name: str) -> str:
        return canonical_player.get((name or "").lower(), name or "(unknown)")

    def _player_pair_included(mcount: int) -> bool:
        if mcount <= 0:
            return False
        if min_matches <= 0:
            return True
        if mcount >= min_matches:
            return True
        return include_opponents_below_min

    players_list_out = []
    for (_pl_lower, _op_lower), v in agg.items():
        if not _player_pair_included(v["matches"]):
            continue
        wr = (v["wins"] + 0.5 * v["draws"]) / v["matches"] if v["matches"] else 0
        players_list_out.append({
            "player": norm_player(v["player"]),
            "opponent_player": norm_player(v["opponent_player"]),
            "wins": v["wins"],
            "losses": v["losses"],
            "draws": v["draws"],
            "intentional_draws": v["intentional_draws"],
            "matches": v["matches"],
            "win_rate": round(wr, 4),
        })

    all_players_sorted = sorted(
        {r["player"] for r in players_list_out} | {r["opponent_player"] for r in players_list_out}
    )
    players_matrix = []
    for i, pa in enumerate(all_players_sorted):
        row = []
        for j, pb in enumerate(all_players_sorted):
            if i == j:
                row.append(None)
                continue
            key = (pa.lower(), pb.lower())
            v = agg.get(key, {"matches": 0, "wins": 0, "draws": 0})
            if not _player_pair_included(v["matches"]):
                row.append(None)
                continue
            wr = (v["wins"] + 0.5 * v["draws"]) / v["matches"] if v["matches"] else None
            row.append(round(wr, 4) if wr is not None else None)
        players_matrix.append(row)

    matchups_list_out = [
        {
            "player_a": _front_face_name(r.get("player") or "(unknown)"),
            "player_b": _front_face_name(r.get("opponent_player") or "(unknown)"),
            "result": r.get("result") or "",
            "event_id": r.get("event_id") or "",
            "date": r.get("date") or "",
            "round": r.get("round"),
            "archetype_a": r.get("archetype") or "",
            "archetype_b": r.get("opponent_archetype") or "",
        }
        for r in filtered
    ]

    # Optional filter by player name(s): keep only pairs where at least one side is in the selection
    if player and len(player) > 0:
        selected_lower = {p.strip().lower() for p in player if p and p.strip()}
        if selected_lower:
            players_list_out = [
                r for r in players_list_out
                if (r["player"] or "").lower() in selected_lower or (r["opponent_player"] or "").lower() in selected_lower
            ]
            all_players_sorted = sorted(
                {r["player"] for r in players_list_out} | {r["opponent_player"] for r in players_list_out}
            )
            players_matrix = []
            for i, pa in enumerate(all_players_sorted):
                row = []
                for j, pb in enumerate(all_players_sorted):
                    if i == j:
                        row.append(None)
                        continue
                    key = (pa.lower(), pb.lower())
                    v = agg.get(key, {"matches": 0, "wins": 0, "draws": 0})
                    if not _player_pair_included(v["matches"]):
                        row.append(None)
                        continue
                    wr = (v["wins"] + 0.5 * v["draws"]) / v["matches"] if v["matches"] else None
                    row.append(round(wr, 4) if wr is not None else None)
                players_matrix.append(row)
            filtered_pairs_lower = {
                ((r["player"] or "").lower(), (r["opponent_player"] or "").lower()) for r in players_list_out
            }
            matchups_list_out = [
                m for m in matchups_list_out
                if (
                    ((m["player_a"] or "").strip().lower(), (m["player_b"] or "").strip().lower()) in filtered_pairs_lower
                    or ((m["player_b"] or "").strip().lower(), (m["player_a"] or "").strip().lower()) in filtered_pairs_lower
                )
            ]

    return {
        "players_list": players_list_out,
        "players": all_players_sorted,
        "players_matrix": players_matrix,
        "matchups_list": matchups_list_out,
        "min_matches": min_matches,
        "include_opponents_below_min": include_opponents_below_min,
    }


@app.get("/api/v1/events/{event_id}/missing-matchups", dependencies=[Depends(require_admin), Depends(require_database)])
def get_missing_matchups(event_id: str):
    """List players (decks) in this event that have fewer matchups than expected (admin).
    Expected = number of decks in event minus one."""
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        missing = _db.list_missing_matchups_for_event(session, event_id)
    return {"missing": missing}


@app.get("/api/v1/events/{event_id}/matchup-discrepancies", dependencies=[Depends(require_admin), Depends(require_database)])
def get_matchup_discrepancies(event_id: str):
    """List matchup pairs where both players reported and results disagree (admin)."""
    with _db.session_scope() as session:
        ev = _db.get_event(session, event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        rows = _db.list_matchups_for_event(session, event_id)
        by_pair = {}
        for r in rows:
            key = tuple(sorted([r["deck_id"], r["opponent_deck_id"]]))
            if key not in by_pair:
                by_pair[key] = []
            by_pair[key].append(r)
        discrepancies = []
        for (deck_a, deck_b), matchups in by_pair.items():
            if len(matchups) != 2:
                continue
            from_a = next((m for m in matchups if m["deck_id"] == deck_a), None)
            from_b = next((m for m in matchups if m["deck_id"] == deck_b), None)
            if from_a is None or from_b is None:
                continue
            r1 = from_a["result"]
            r2 = from_b["result"]
            if not _matchup_result_consistent(r1, r2):
                discrepancies.append({
                    "deck_id_a": deck_a,
                    "deck_id_b": deck_b,
                    "matchup_a": from_a,
                    "matchup_b": from_b,
                    "result_a": r1,
                    "result_b": r2,
                })
        deck_ids = set()
        for d in discrepancies:
            deck_ids.add(d["deck_id_a"])
            deck_ids.add(d["deck_id_b"])
        player_by_deck = {}
        if deck_ids:
            rows = session.query(_db.DeckRow).filter(_db.DeckRow.deck_id.in_(deck_ids)).all()
            for r in rows:
                player_by_deck[r.deck_id] = (r.player or "").strip() or "(unknown)"
        for d in discrepancies:
            d["player_a"] = player_by_deck.get(d["deck_id_a"], "(unknown)")
            d["player_b"] = player_by_deck.get(d["deck_id_b"], "(unknown)")
        return {"discrepancies": discrepancies}


@app.patch("/api/v1/matchups/{matchup_id}", dependencies=[Depends(require_admin), Depends(require_database)])
def patch_matchup(matchup_id: int, body: PatchMatchupBody):
    """Update a matchup result (admin fix for discrepancies or one-sided reports)."""
    with _db.session_scope() as session:
        ok = _db.update_matchup(
            session,
            matchup_id,
            result=body.result,
            result_note=body.result_note,
            round=body.round,
        )
    if not ok:
        raise HTTPException(status_code=404, detail="Matchup not found")
    return {"ok": True}


@app.get("/api/v1/player-aliases")
def get_player_aliases():
    """List player alias mappings (alias -> canonical)."""
    return {"aliases": _player_aliases}


@app.post("/api/v1/player-aliases")
def add_player_alias(body: PlayerAliasBody, _: str = Depends(require_admin)):
    """Merge player: map alias to canonical name. E.g. {'alias': 'Pablo Tomas Pesci', 'canonical': 'Tomas Pesci'}."""
    alias = body.alias.strip()
    canonical = body.canonical.strip()
    if not alias or not canonical:
        raise HTTPException(status_code=400, detail="alias and canonical required")
    _player_aliases[alias] = canonical
    _save_player_aliases()
    # If DB is available, also persist alias + merge historical data there
    if _database_available():
        try:
            with _db.session_scope() as session:
                _db.set_player_alias(session, alias, canonical)
                _db.merge_players_by_names(session, alias, canonical)
        except Exception as e:
            logger.exception("Failed to save/merge player alias to DB: %s", e)
        else:
            _load_player_aliases()
            _load_decks_from_db()
    return {"aliases": _player_aliases}


@app.delete("/api/v1/player-aliases/{alias:path}")
def remove_player_alias(alias: str, _: str = Depends(require_admin)):
    """Remove a player alias."""
    a = unquote(alias).strip()
    if a in _player_aliases:
        del _player_aliases[a]
        if _database_available():
            try:
                with _db.session_scope() as session:
                    _db.remove_player_alias(session, a)
            except Exception as e:
                logger.exception("Failed to remove player alias from DB: %s", e)
            else:
                _load_player_aliases()
                _load_decks_from_db()
        _save_player_aliases()
    return {"aliases": _player_aliases}


@app.get("/api/v1/players/similar")
def get_similar_players(
    name: str = Query(..., description="Player name to find similar"),
    limit: int = Query(10, ge=1, le=50),
):
    """Suggest players with similar names (for merging)."""
    name_norm = _normalize_search(name)
    names = set((d.get("player") or "").strip() for d in _decks if (d.get("player") or "").strip())
    names.discard("")
    names.discard("(unknown)")
    # Simple similarity: same last word, or one contains the other (accent-insensitive)
    def score(n: str) -> int:
        nn = _normalize_search(n)
        if nn == name_norm:
            return 0
        if name_norm in nn or nn in name_norm:
            return 1
        name_words = set(name_norm.split())
        n_words = set(nn.split())
        overlap = len(name_words & n_words)
        return 10 - overlap if overlap > 0 else 99
    sorted_names = sorted(names, key=score)
    return {"similar": [n for n in sorted_names if score(n) < 99][:limit]}


@app.get("/api/v1/players")
def get_players(
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
    player_id: int | None = Query(None, description="Filter to a single player by ID (exact)"),
):
    """Player leaderboard (wins, top-2, top-4, points). Merges aliased players. Includes player_id for stable links."""
    if not _decks:
        return {"players": []}
    filtered = _filter_decks_by_date(_decks, date_from, date_to)
    if player_id is not None:
        filtered = [d for d in filtered if d.get("player_id") == player_id]
    decks = [Deck.from_dict(d) for d in filtered]
    rank_weights = settings_service.get_rank_weights()
    players = player_leaderboard(decks, normalize_player=_normalize_player, rank_weights=rank_weights)
    for p in players:
        canonical = p.get("player") or ""
        p["player_id"] = next((d.get("player_id") for d in filtered if _normalize_player(d.get("player") or "") == canonical), None)
    if player_id is not None:
        players = [p for p in players if p.get("player_id") == player_id]
    return {"players": players}


def _empty_player_stats() -> dict:
    return {"wins": 0, "top2": 0, "top4": 0, "top8": 0, "points": 0.0, "deck_count": 0}


def _player_detail_payload(
    all_player_decks: list[dict],
    display: str,
    player_id: int | None,
    date_from: str | None,
    date_to: str | None,
) -> dict:
    """Build the shared payload for both /players/id/{id} and /players/{name} endpoints.

    When date filters are provided, stats are computed on the filtered subset. If
    the player exists but has no decks in range, returns zero-valued stats with
    an empty decks list (instead of 404).
    """
    player_decks = _filter_decks_by_date(all_player_decks, date_from, date_to)
    rank_weights = settings_service.get_rank_weights()
    decks = [Deck.from_dict(d) for d in player_decks]
    stats_list = player_leaderboard(decks, rank_weights=rank_weights) if decks else []
    stat = stats_list[0] if stats_list else _empty_player_stats()
    deck_summaries = [
        {"deck_id": d.get("deck_id"), "name": d.get("name"), "event_name": d.get("event_name"), "date": d.get("date"), "rank": d.get("rank")}
        for d in player_decks
    ]
    deck_summaries.sort(key=lambda x: _deck_sort_key(x))
    return {
        "player": display,
        "player_id": player_id,
        "wins": stat["wins"],
        "top2": stat["top2"],
        "top4": stat["top4"],
        "top8": stat["top8"],
        "points": stat["points"],
        "deck_count": stat["deck_count"],
        "decks": deck_summaries,
    }


@app.get("/api/v1/players/id/{player_id:int}")
def get_player_detail_by_id(
    player_id: int,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Player stats and their decks by stable player_id. Optional date range."""
    all_player_decks = [d for d in _decks if d.get("player_id") == player_id]
    if not all_player_decks:
        raise HTTPException(status_code=404, detail="Player not found")
    display = _normalize_player((all_player_decks[0].get("player") or "").strip())
    out = _player_detail_payload(all_player_decks, display, player_id, date_from, date_to)
    if _database_available():
        with _db.session_scope() as session:
            prow = _db.get_player_by_id(session, player_id)
            if prow and (prow.display_name or "").strip():
                display = (prow.display_name or "").strip()
                out["player"] = display
            email = _db.get_player_email(session, display)
            out["has_email"] = bool(email and email.strip())
    return out


def _resolve_player_name_to_canonical(name: str) -> str:
    """Resolve a requested player name (e.g. from URL) to the canonical display name, accent-insensitive.
    So 'matias' finds the player whose canonical name is 'Matías'."""
    if not name or not name.strip():
        return name or ""
    name = name.strip()
    canonicals = {_normalize_player(d.get("player") or "") for d in _decks if (d.get("player") or "").strip()}
    canonical = _normalize_player(name)
    if canonical in canonicals:
        return canonical
    name_norm = _normalize_search(name)
    for c in canonicals:
        if _normalize_search(c) == name_norm:
            return c
    return canonical


@app.get("/api/v1/players/id/{player_id:int}/analysis", response_model=PlayerAnalysisResponse)
def get_player_analysis_by_id(
    player_id: int,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Aggregated analytics for the player dashboard by stable player_id. Optional date range."""
    player_decks = [d for d in _decks if d.get("player_id") == player_id]
    if not player_decks:
        raise HTTPException(status_code=404, detail="Player not found")
    display = _normalize_player((player_decks[0].get("player") or "").strip())
    if _database_available():
        try:
            with _db.session_scope() as session:
                prow = _db.get_player_by_id(session, player_id)
                if prow and (prow.display_name or "").strip():
                    display = (prow.display_name or "").strip()
        except Exception:
            logger.exception("DB lookup failed for player analysis display name")
    return _player_analysis_cached(player_decks, display, player_id, date_from, date_to)


@app.get("/api/v1/players/{player_name:path}/analysis", response_model=PlayerAnalysisResponse)
def get_player_analysis_by_name(
    player_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Aggregated analytics for the player dashboard by name (alias-resolved). Optional date range."""
    name = unquote(player_name).strip()
    # If the name ends with "/analysis" because of path matching quirks, strip it.
    if name.endswith("/analysis"):
        name = name[: -len("/analysis")].strip()
    canonical = _resolve_player_name_to_canonical(name)
    player_decks = [d for d in _decks if _normalize_player(d.get("player") or "") == canonical]
    if not player_decks:
        raise HTTPException(status_code=404, detail="Player not found")
    pid = player_decks[0].get("player_id") if player_decks else None
    display = _normalize_player(canonical)
    if _database_available() and pid is not None:
        try:
            with _db.session_scope() as session:
                prow = _db.get_player_by_id(session, pid)
                if prow and (prow.display_name or "").strip():
                    display = (prow.display_name or "").strip()
        except Exception:
            logger.exception("DB lookup failed for player analysis display name")
    return _player_analysis_cached(player_decks, display, pid, date_from, date_to)


@app.get("/api/v1/players/{player_name:path}")
def get_player_detail(
    player_name: str,
    date_from: str | None = Query(None, description="Filter from date (DD/MM/YY)"),
    date_to: str | None = Query(None, description="Filter to date (DD/MM/YY)"),
):
    """Player stats and their decks. Merges aliased players (e.g. Pablo Tomas Pesci = Tomas Pesci). Accent-insensitive: matias finds Matías."""
    name = unquote(player_name).strip()
    canonical = _resolve_player_name_to_canonical(name)
    all_player_decks = [d for d in _decks if _normalize_player(d.get("player") or "") == canonical]
    if not all_player_decks:
        raise HTTPException(status_code=404, detail="Player not found")
    pid = all_player_decks[0].get("player_id") if all_player_decks else None
    display = _normalize_player(canonical)
    out = _player_detail_payload(all_player_decks, display, pid, date_from, date_to)
    if _database_available():
        with _db.session_scope() as session:
            if pid is not None:
                prow = _db.get_player_by_id(session, pid)
                if prow and (prow.display_name or "").strip():
                    display = (prow.display_name or "").strip()
                    out["player"] = display
            email = _db.get_player_email(session, display)
            out["has_email"] = bool(email and email.strip())
    return out


# ---------- Player analysis (dashboard) -------------------------------------

_NORMALIZED_RANK_MID = {
    "1": 1.0,
    "2": 2.0,
    "3-4": 3.5,
    "5-8": 6.5,
    "9-16": 12.5,
    "17-32": 24.5,
    "33-64": 48.5,
    "65-128": 96.5,
}

_COLOR_KEYS_FULL = ("W", "U", "B", "R", "G", "C")

_BASIC_LAND_NAMES = {
    "Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
    "Snow-Covered Mountain", "Snow-Covered Forest",
}


def _rank_numeric(rank: str) -> float | None:
    """Midpoint of the normalized rank band (e.g. '3-4' -> 3.5), or None."""
    nr = normalize_rank(rank or "")
    return _NORMALIZED_RANK_MID.get(nr)


def _best_rank(ranks: list[str]) -> str:
    """Return the best (lowest-numbered) rank string from a list."""
    best = None
    best_val = None
    for r in ranks:
        v = _rank_numeric(r)
        if v is None:
            continue
        if best_val is None or v < best_val:
            best = normalize_rank(r)
            best_val = v
    return best or ""


def _deck_color_identity(deck_obj: Deck, card_metadata: dict[str, dict]) -> list[str]:
    """Color identity for a deck, ordered WUBRG+C.

    EDH: derived from commander color identity (colorless EDH -> ['C']).
    Non-EDH: derived from mainboard cards' color identities.
    """
    is_edh = (deck_obj.format_id or "").upper() in {"EDH", "CEDH", "COMMANDER"}
    ci: set[str] = set()
    if is_edh:
        for name in effective_commanders(deck_obj):
            entry = card_metadata.get(name)
            if entry and "error" not in entry:
                for c in entry.get("color_identity") or entry.get("colors") or []:
                    if c in {"W", "U", "B", "R", "G"}:
                        ci.add(c)
        if not ci:
            ci.add("C")
    else:
        for _qty, card in effective_mainboard(deck_obj):
            entry = card_metadata.get(card)
            if not entry or "error" in entry:
                continue
            for c in entry.get("color_identity") or entry.get("colors") or []:
                if c in {"W", "U", "B", "R", "G"}:
                    ci.add(c)
        if not ci:
            ci.add("C")
    order = ["W", "U", "B", "R", "G", "C"]
    return [c for c in order if c in ci]


def _lookup_player_card_metadata(player_deck_objs: list[Deck]) -> dict[str, dict]:
    """Single Scryfall lookup for every unique card (commander + mainboard) across a player's decks."""
    names: set[str] = set()
    for d in player_deck_objs:
        for c in effective_commanders(d):
            if c:
                names.add(c)
        for _qty, card in effective_mainboard(d):
            if card:
                names.add(card)
    if not names:
        return {}
    try:
        return lookup_cards(list(names))
    except Exception:
        logger.exception("Card metadata lookup failed for player analysis")
        return {}


def _archetype_performance(player_deck_dicts: list[dict]) -> list[dict]:
    """Per-archetype: count, avg finish, best finish, top-8 %, win %."""
    buckets: dict[str, dict] = {}
    display_name: dict[str, str] = {}
    for d in player_deck_dicts:
        arch_raw = (d.get("archetype") or "").strip()
        if not arch_raw or arch_raw.lower() == "(unknown)":
            continue
        key = arch_raw.lower()
        display_name.setdefault(key, arch_raw)
        b = buckets.setdefault(key, {"ranks": [], "top8": 0, "wins": 0})
        b["ranks"].append(d.get("rank") or "")
        if is_top8(d.get("rank") or ""):
            b["top8"] += 1
        if normalize_rank(d.get("rank") or "") == "1":
            b["wins"] += 1
    rows: list[dict] = []
    for key, b in buckets.items():
        count = len(b["ranks"])
        nums = [v for v in (_rank_numeric(r) for r in b["ranks"]) if v is not None]
        avg_finish = round(sum(nums) / len(nums), 1) if nums else None
        rows.append({
            "archetype": display_name[key],
            "count": count,
            "avg_finish": avg_finish,
            "best_finish": _best_rank(b["ranks"]),
            "top8_pct": round(100 * b["top8"] / count, 1) if count else 0.0,
            "win_pct": round(100 * b["wins"] / count, 1) if count else 0.0,
        })
    rows.sort(key=lambda r: (-r["count"], r["archetype"].lower()))
    return rows


def _color_count_distribution(color_identities: list[list[str]]) -> dict[str, int]:
    """Bucket decks by number of distinct non-colorless colors. Colorless decks bucket to 0."""
    out: dict[str, int] = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    for ci in color_identities:
        non_c = [c for c in ci if c != "C"]
        n = len(non_c)
        if n > 5:
            n = 5
        out[str(n)] += 1
    return out


def _format_distribution(player_deck_dicts: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for d in player_deck_dicts:
        fid = (d.get("format_id") or "").strip() or "?"
        counts[fid] = counts.get(fid, 0) + 1
    total = sum(counts.values()) or 1
    rows = [
        {"format_id": fid, "count": c, "pct": round(100 * c / total, 1)}
        for fid, c in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
    return rows


def _commander_distribution_edh(player_deck_objs: list[Deck]) -> list[dict]:
    """Top commanders, EDH-only. Empty for non-EDH players."""
    counts: dict[str, int] = {}
    for d in player_deck_objs:
        if (d.format_id or "").upper() not in {"EDH", "CEDH", "COMMANDER"}:
            continue
        ec = effective_commanders(d)
        key = " / ".join(sorted(ec)) if ec else "(no commander)"
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values()) or 1
    return [
        {"commander": c, "count": n, "pct": round(100 * n / total, 1)}
        for c, n in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


def _top_cards_for_player(
    player_deck_objs: list[Deck],
    ignore_cards: set[str],
    limit: int = 20,
) -> tuple[list[dict], list[dict]]:
    """Returns (top_cards, pet_cards) across the player's mainboards (excluding basic lands & ignore list)."""
    deck_count = len(player_deck_objs)
    card_decks: dict[str, set[int]] = {}
    card_copies: dict[str, int] = {}
    for d in player_deck_objs:
        seen_in_deck: set[str] = set()
        for qty, card in effective_mainboard(d):
            if card in _BASIC_LAND_NAMES:
                continue
            if card in ignore_cards:
                continue
            card_copies[card] = card_copies.get(card, 0) + int(qty)
            seen_in_deck.add(card)
        for card in seen_in_deck:
            card_decks.setdefault(card, set()).add(d.deck_id)
    rows = [
        {"card": c, "deck_count": len(card_decks[c]), "total_copies": card_copies[c]}
        for c in card_decks
    ]
    rows.sort(key=lambda r: (-r["deck_count"], -r["total_copies"], r["card"].lower()))
    top_cards = rows[:limit]
    pet_threshold = max(3, math.ceil(deck_count * 0.3)) if deck_count else 3
    pet_cards = [r for r in rows if r["deck_count"] >= pet_threshold][:30]
    return top_cards, pet_cards


def _field_size_buckets(player_deck_dicts: list[dict]) -> list[dict]:
    bucket_defs = [("<32", 0, 31), ("32-100", 32, 100), ("100+", 101, 10**9)]
    buckets: dict[str, dict] = {b[0]: {"ranks": [], "top8": 0} for b in bucket_defs}
    for d in player_deck_dicts:
        pc = int(d.get("player_count") or 0)
        rank = d.get("rank") or ""
        for label, lo, hi in bucket_defs:
            if lo <= pc <= hi:
                buckets[label]["ranks"].append(rank)
                if is_top8(rank):
                    buckets[label]["top8"] += 1
                break
    rows: list[dict] = []
    for label, _lo, _hi in bucket_defs:
        b = buckets[label]
        count = len(b["ranks"])
        nums = [v for v in (_rank_numeric(r) for r in b["ranks"]) if v is not None]
        rows.append({
            "bucket": label,
            "count": count,
            "avg_finish": round(sum(nums) / len(nums), 1) if nums else None,
            "top8_pct": round(100 * b["top8"] / count, 1) if count else 0.0,
        })
    return rows


def _metagame_comparison(
    player_dist: list[dict],
    global_dist: list[dict],
    limit: int = 10,
) -> list[dict]:
    """For the player's top archetypes, return side-by-side player vs global pct."""
    global_by_key: dict[str, float] = {
        (row.get("archetype") or "").lower(): float(row.get("pct") or 0)
        for row in global_dist
    }
    out: list[dict] = []
    for row in player_dist[:limit]:
        name = row.get("archetype") or ""
        out.append({
            "archetype": name,
            "player_pct": float(row.get("pct") or 0),
            "global_pct": global_by_key.get(name.lower(), 0.0),
        })
    return out


def _highlights(per_event: list[dict]) -> dict:
    """Best finish, longest top-8 streak, biggest-field win, total events, cadence."""
    if not per_event:
        return {
            "best_finish": "",
            "longest_top8_streak": 0,
            "biggest_field_win": None,
            "total_events": 0,
            "avg_days_between_events": None,
            "first_event_date": None,
            "last_event_date": None,
        }
    ranks = [e.get("rank") or "" for e in per_event]
    best = _best_rank(ranks)
    # Longest top-8 streak across chronologically ordered events
    longest = current = 0
    for e in per_event:
        if is_top8(e.get("rank") or ""):
            current += 1
            if current > longest:
                longest = current
        else:
            current = 0
    # Biggest-field win: largest player_count where rank normalizes to "1"
    biggest_field_win: int | None = None
    for e in per_event:
        if normalize_rank(e.get("rank") or "") == "1":
            pc = int(e.get("player_count") or 0)
            if biggest_field_win is None or pc > biggest_field_win:
                biggest_field_win = pc
    # Cadence: avg days between distinct event dates
    date_strs = sorted({e.get("date") or "" for e in per_event if e.get("date")}, key=_parse_date_sortkey)
    avg_days: float | None = None
    if len(date_strs) >= 2:
        def _to_dt(ds: str) -> datetime | None:
            try:
                parts = ds.split("/")
                if len(parts) != 3:
                    return None
                dd, mm, yy = int(parts[0]), int(parts[1]), int(parts[2])
                year = 2000 + yy if yy < 100 else yy
                return datetime(year, mm, dd)
            except Exception:
                return None
        dts = [dt for dt in (_to_dt(s) for s in date_strs) if dt is not None]
        if len(dts) >= 2:
            gaps = [(dts[i] - dts[i - 1]).days for i in range(1, len(dts))]
            avg_days = round(sum(gaps) / len(gaps), 1) if gaps else None
    return {
        "best_finish": best,
        "longest_top8_streak": longest,
        "biggest_field_win": biggest_field_win,
        "total_events": len({e.get("event_id") for e in per_event if e.get("event_id") is not None}) or len(per_event),
        "avg_days_between_events": avg_days,
        "first_event_date": date_strs[0] if date_strs else None,
        "last_event_date": date_strs[-1] if date_strs else None,
    }


def _leaderboard_history_for_player(
    canonical: str,
    all_decks: list[dict],
    rank_weights: dict[str, float],
) -> list[dict]:
    """Snapshot the player's leaderboard rank at each date they had an event.

    Streaming algorithm: walk all decks in date order, accumulating per-player
    stats; after processing each date we snapshot the rank at target dates.
    O(D log D + E * P log P).
    """
    # Group decks by date in chronological order
    date_order = sorted(
        {d.get("date") or "" for d in all_decks if d.get("date")},
        key=_parse_date_sortkey,
    )
    target_dates = {
        d.get("date") or ""
        for d in all_decks
        if _normalize_player(d.get("player") or "") == canonical and d.get("date")
    }
    if not target_dates:
        return []
    by_date: dict[str, list[dict]] = {}
    for d in all_decks:
        ds = d.get("date") or ""
        if not ds:
            continue
        by_date.setdefault(ds, []).append(d)
    stats: dict[str, dict[str, float]] = {}
    snapshots: list[dict] = []
    for ds in date_order:
        for d in by_date.get(ds, []):
            raw = (d.get("player") or "").strip()
            if not raw or raw.lower() == "(unknown)":
                continue
            player = _normalize_player(raw)
            s = stats.setdefault(player, {"wins": 0.0, "points": 0.0})
            nr = normalize_rank(d.get("rank") or "")
            s["points"] += rank_weights.get(nr, 1.0)
            if nr == "1":
                s["wins"] += 1
        if ds in target_dates:
            sorted_players = sorted(
                stats.items(),
                key=lambda kv: (-kv[1]["wins"], -kv[1]["points"]),
            )
            rank = next(
                (i + 1 for i, (p, _s) in enumerate(sorted_players) if p == canonical),
                0,
            )
            snapshots.append({
                "date": ds,
                "rank": rank,
                "total_players": len(sorted_players),
            })
    return snapshots


def _build_player_analysis(
    player_deck_dicts: list[dict],
    all_decks: list[dict],
    canonical_display: str,
    player_id: int | None,
) -> dict:
    """Aggregate everything required by the Player Detail analytics dashboard."""
    deck_objs = [Deck.from_dict(d) for d in player_deck_dicts]
    rank_weights = settings_service.get_rank_weights()

    card_metadata = _lookup_player_card_metadata(deck_objs)

    # Per-event (deck) rows, sorted chronologically (ascending for time-series charts)
    per_event_rows: list[dict] = []
    color_identities: list[list[str]] = []
    for d, deck_obj in zip(player_deck_dicts, deck_objs):
        ci = _deck_color_identity(deck_obj, card_metadata)
        color_identities.append(ci)
        nr = normalize_rank(d.get("rank") or "")
        per_event_rows.append({
            "deck_id": d.get("deck_id"),
            "event_id": d.get("event_id"),
            "event_name": d.get("event_name") or "",
            "date": d.get("date") or "",
            "rank": d.get("rank") or "",
            "normalized_rank": nr,
            "normalized_rank_num": _rank_numeric(d.get("rank") or ""),
            "points": rank_weights.get(nr, 1.0),
            "player_count": int(d.get("player_count") or 0),
            "format_id": d.get("format_id") or "",
            "archetype": d.get("archetype"),
            "color_identity": ci,
            "commanders": list(d.get("commanders") or []),
        })
    per_event_rows.sort(key=lambda r: _parse_date_sortkey(r.get("date") or ""))

    # Distributions
    arch_dist = archetype_distribution(deck_objs)
    arch_perf = _archetype_performance(player_deck_dicts)

    color_count_dist = _color_count_distribution(color_identities)

    fmt_dist = _format_distribution(player_deck_dicts)
    cmd_dist = _commander_distribution_edh(deck_objs)

    # Average mana curve and color distribution across decks (reuse analyzer helper)
    aggregate = archetype_aggregate_analysis(deck_objs, card_metadata) if deck_objs else {}
    avg_mana_curve_raw = aggregate.get("mana_curve") or {}
    average_mana_curve = {str(k): float(v) for k, v in avg_mana_curve_raw.items()}
    color_distribution = {k: float(v) for k, v in (aggregate.get("color_distribution") or {}).items()}
    for k in _COLOR_KEYS_FULL:
        color_distribution.setdefault(k, 0.0)

    # Top cards / pet cards (exclude basics and configured ignore list)
    ignore_cards = set(settings_service.get_ignore_lands_cards() or [])
    top_cards, pet_cards = _top_cards_for_player(deck_objs, ignore_cards)

    field_buckets = _field_size_buckets(player_deck_dicts)

    # Global archetype distribution for comparison (full dataset)
    try:
        global_arch_dist = archetype_distribution([Deck.from_dict(d) for d in all_decks])
    except Exception:
        logger.exception("Global archetype distribution failed for player analysis")
        global_arch_dist = []
    meta_comparison = _metagame_comparison(arch_dist, global_arch_dist)

    highlights = _highlights(per_event_rows)

    # Leaderboard rank history (streaming)
    try:
        leaderboard_history = _leaderboard_history_for_player(
            canonical_display, all_decks, rank_weights,
        )
    except Exception:
        logger.exception("Leaderboard history failed for player %s", canonical_display)
        leaderboard_history = []

    return {
        "player": canonical_display,
        "player_id": player_id,
        "per_event": per_event_rows,
        "leaderboard_history": leaderboard_history,
        "archetype_distribution": [
            {"archetype": r["archetype"], "count": int(round(float(r["count"]))), "pct": float(r["pct"])}
            for r in arch_dist
        ],
        "archetype_performance": arch_perf,
        "color_distribution": color_distribution,
        "color_count_distribution": color_count_dist,
        "format_distribution": fmt_dist,
        "commander_distribution": cmd_dist,
        "average_mana_curve": average_mana_curve,
        "top_cards": top_cards,
        "pet_cards": pet_cards,
        "field_size_buckets": field_buckets,
        "metagame_comparison": meta_comparison,
        "highlights": highlights,
    }


# Cache analysis responses between requests. Key includes a stable signature of
# the current `_decks` list and rank weights so we invalidate automatically when
# data changes.
_player_analysis_cache: dict[tuple, dict] = {}


def _player_analysis_cache_signature() -> tuple:
    weights = settings_service.get_rank_weights()
    weights_sig = tuple(sorted((str(k), float(v)) for k, v in (weights or {}).items()))
    # id(_decks) plus len gives cheap invalidation on reload (new list) or append.
    return (id(_decks), len(_decks), weights_sig)


def _player_analysis_cached(
    player_deck_dicts: list[dict],
    canonical_display: str,
    player_id: int | None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    key = (
        _player_analysis_cache_signature(),
        player_id if player_id is not None else canonical_display,
        date_from or "",
        date_to or "",
    )
    cached = _player_analysis_cache.get(key)
    if cached is not None:
        return cached
    # Apply date filter consistently: the per_event rows, distributions, metagame
    # comparison and leaderboard-rank history are all computed relative to the
    # selected window so the dashboard stays internally consistent.
    filtered_player = _filter_decks_by_date(player_deck_dicts, date_from, date_to)
    filtered_all = _filter_decks_by_date(_decks, date_from, date_to)
    result = _build_player_analysis(
        filtered_player, filtered_all, canonical_display, player_id,
    )
    # Bound cache size to avoid unbounded memory growth.
    if len(_player_analysis_cache) > 128:
        _player_analysis_cache.clear()
    _player_analysis_cache[key] = result
    return result


@app.post("/api/v1/load", dependencies=[Depends(require_database)])
async def load_decks(
    request: Request,
    file: UploadFile | None = File(None),
    _: str = Depends(require_admin),
):
    """Load decks from JSON into the database. Body: { "decks": [...] } or { "path": "decks.json" }, or upload file. Requires PostgreSQL.

    JSON body cannot be declared alongside ``File()`` in the same handler (OpenAPI limitation); we read ``application/json`` from the request when no file part is sent.
    """
    global _decks
    body: LoadBody | None = None
    has_upload = file is not None and bool(getattr(file, "filename", None))

    if has_upload:
        try:
            content = await _read_upload_json_bytes_async(file)
            _decks = _normalize_split_cards(json.loads(content.decode("utf-8")))
        except json.JSONDecodeError as e:
            logger.warning("Load decks: invalid JSON from upload: %s", e)
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    else:
        ct = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ct != "application/json":
            raise HTTPException(status_code=400, detail="Provide JSON body or file upload")
        try:
            raw = await request.json()
        except json.JSONDecodeError as e:
            logger.warning("Load decks: invalid JSON body: %s", e)
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        try:
            body = LoadBody.model_validate(raw)
        except Exception as e:
            logger.warning("Load decks: invalid load payload: %s", e)
            raise HTTPException(status_code=422, detail=str(e)) from e
        path_str = (body.path or "").strip()
        if path_str:
            path = _resolve_load_path_under_data_dir(path_str)
            if not path.exists():
                raise HTTPException(status_code=404, detail=f"File not found: {path}")
            try:
                _load_from_file(str(path))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Load decks from path %s failed: %s", path, e)
                raise HTTPException(status_code=400, detail=f"Failed to load file: {e}") from e
        elif body.decks is not None:
            _decks = _normalize_split_cards(body.decks)
        else:
            raise HTTPException(status_code=400, detail="Provide 'decks' array, 'path', or file upload")
    _invalidate_metagame()
    if _database_available():
        if body and (body.event_id is not None or body.new_event is not None):
            event_id = body.event_id
            event_name = date = format_id = None
            if body.new_event:
                with _db.session_scope() as session:
                    row = _db.create_event(
                        session,
                        event_name=body.new_event.event_name.strip() or "Unnamed",
                        date=body.new_event.date.strip() or "",
                        format_id=body.new_event.format_id.strip() or "EDH",
                        origin=_db.ORIGIN_MANUAL,
                        event_id=None,
                    )
                    event_id, event_name, date, format_id = row.event_id, row.name, row.date, row.format_id
            elif body.event_id is not None:
                with _db.session_scope() as session:
                    ev = _db.get_event(session, body.event_id)
                    if not ev:
                        raise HTTPException(status_code=404, detail="Event not found")
                    event_id, event_name, date, format_id = ev.event_id, ev.name, ev.date, ev.format_id
            if event_id is not None and event_name is not None:
                next_id = None
                with _db.session_scope() as session:
                    next_id = _db.next_manual_deck_id(session)
                for i, d in enumerate(_decks):
                    d = dict(d)
                    d["event_id"] = event_id
                    d["event_name"] = event_name or d.get("event_name", "")
                    d["date"] = date or d.get("date", "")
                    d["format_id"] = format_id or d.get("format_id", "")
                    if d.get("deck_id") is None or (isinstance(d.get("deck_id"), int) and d["deck_id"] < _db.MANUAL_DECK_ID_START):
                        d["deck_id"] = next_id + i
                    _decks[i] = d
        _persist_decks_to_db(_decks, origin=_db.ORIGIN_MANUAL if (body and (body.event_id is not None or body.new_event)) else _db.ORIGIN_MTGTOP8)
    return {"loaded": len(_decks), "message": f"Loaded {len(_decks)} decks"}


@app.get("/api/v1/export")
def export_decks(_: str = Depends(require_admin)):
    """Download current scraped/loaded data as JSON (same format as load accepts)."""
    if not _decks:
        raise HTTPException(status_code=404, detail="No data to export. Scrape or load data first.")
    body = json.dumps(_decks, indent=2, ensure_ascii=False).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="decks.json"'},
    )


@app.post("/api/v1/analyze")
def run_analyze():
    """Re-run analysis (no-op, metagame is computed on demand)."""
    _invalidate_metagame()
    return {"message": "Analysis will be recomputed on next /api/metagame request"}


@app.post("/api/v1/scrape")
async def run_scrape(body: ScrapeBody, _: str = Depends(require_admin)):
    """Trigger scrape with SSE progress streaming."""
    import queue
    import re

    format_id = body.format_id
    period = body.period
    store = body.store
    event_ids = body.event_ids
    if isinstance(event_ids, str):
        event_ids = [x.strip() for x in event_ids.split(",") if x.strip()] or None
    # Scraper expects list[int]; ignore non-numeric IDs (e.g. manual "m1")
    scrape_event_ids: list[int] | None = None
    if event_ids:
        scrape_event_ids = [int(x) for x in event_ids if str(x).isdigit()]
        if not scrape_event_ids:
            scrape_event_ids = None

    # When not forcing, skip events already in DB (or in _decks when no DB)
    skip_event_ids: set[int] | None = None
    if not body.force_replace and body.ignore_existing_events:
        if _database_available():
            try:
                with _db.session_scope() as session:
                    skip_event_ids = _db.get_mtgtop8_event_ids(session)
            except Exception as e:
                logger.warning("Could not load existing event IDs for skip list: %s", e)
        elif _decks:
            skip_event_ids = {
                int(eid)
                for eid in {d.get("event_id") for d in _decks}
                if eid is not None and str(eid).isdigit()
            }

    global _scrape_cancel_event
    _scrape_cancel_event = threading.Event()
    start_time = time.time()
    logger.info(
        "Scrape started: format=%s period=%s store=%s event_ids=%s ignore_existing=%s force_replace=%s db_available=%s skip_count=%s",
        format_id, period, store, scrape_event_ids, body.ignore_existing_events, body.force_replace,
        _database_available(), len(skip_event_ids) if skip_event_ids else 0,
    )

    q: queue.Queue[str | None] = queue.Queue()
    result_holder: list = []
    error_holder: list = []

    def on_progress(msg: str) -> None:
        q.put(msg)

    def run_scraper() -> None:
        try:
            decks = scrape(
                format_id=format_id,
                period=period,
                store=store,
                event_ids=scrape_event_ids,
                on_progress=on_progress,
                skip_event_ids=None if body.force_replace or scrape_event_ids else skip_event_ids,
                should_stop=lambda: _scrape_cancel_event.is_set() if _scrape_cancel_event else False,
            )
            result_holder.append(decks)
        except Exception as e:
            logger.exception(
                "Scrape failed: format=%s period=%s event_ids=%s error=%s",
                format_id, period, scrape_event_ids, e,
            )
            error_holder.append(str(e))
        finally:
            q.put(None)

    thread = threading.Thread(target=run_scraper, daemon=True)
    thread.start()

    def event_stream():
        global _decks
        total_events = 0
        current_event = 0
        total_decks_in_event = 0
        current_deck_in_event = 0
        while True:
            try:
                msg = q.get(timeout=300)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Timeout'})}\n\n"
                return
            if msg is None:
                break

            pct = 0
            events_match = re.search(r"Found (\d+) events", msg)
            if events_match:
                total_events = int(events_match.group(1))

            event_match = re.match(r"\[(\d+)/(\d+)\]", msg)
            if event_match:
                current_event = int(event_match.group(1))
                total_events = int(event_match.group(2))

            deck_found = re.search(r"Found (\d+) decks", msg)
            if deck_found:
                total_decks_in_event = int(deck_found.group(1))
                current_deck_in_event = 0

            deck_parse = re.search(r"Parsing deck (\d+)/(\d+)", msg)
            if deck_parse:
                current_deck_in_event = int(deck_parse.group(1))
                total_decks_in_event = int(deck_parse.group(2))

            if total_events > 0:
                event_pct = ((current_event - 1) / total_events) * 100 if current_event > 0 else 0
                if total_decks_in_event > 0 and current_event > 0:
                    deck_pct = (current_deck_in_event / total_decks_in_event) * (100 / total_events)
                    pct = event_pct + deck_pct
                else:
                    pct = event_pct
                pct = min(pct, 99)

            yield f"data: {json.dumps({'type': 'progress', 'message': msg, 'pct': round(pct, 1)})}\n\n"

        if error_holder:
            duration = time.time() - start_time
            logger.warning("Scrape failed after %.1fs: %s", duration, error_holder[0])
            yield f"data: {json.dumps({'type': 'error', 'message': error_holder[0]})}\n\n"
        elif result_holder:
            decks = result_holder[0]
            deck_dicts = [d.to_dict() for d in decks]
            events_in_run = {str(d.get("event_id")) for d in deck_dicts if d.get("event_id") is not None}
            if _database_available():
                try:
                    with _db.session_scope() as session:
                        if body.force_replace:
                            # Hybrid forced replace: update event metadata, delete MTGTop8 decks per event, then upsert fresh decks
                            for eid in events_in_run:
                                sample = next((d for d in deck_dicts if str(d.get("event_id")) == eid), None)
                                if not sample:
                                    continue
                                ev_name_raw = sample.get("event_name", "")
                                ev_name, ev_store, ev_location = parse_event_display(ev_name_raw)
                                existing = _db.get_event(session, eid)
                                if existing is None:
                                    _db.create_event(
                                        session,
                                        event_name=ev_name or ev_name_raw or "Unnamed",
                                        date=sample.get("date", ""),
                                        format_id=sample.get("format_id", ""),
                                        origin=_db.ORIGIN_MTGTOP8,
                                        event_id=eid,
                                        player_count=int(sample.get("player_count", 0)),
                                        store=ev_store,
                                        location=ev_location,
                                    )
                                else:
                                    _db.update_event(
                                        session,
                                        eid,
                                        event_name=ev_name or ev_name_raw or existing.name,
                                        date=sample.get("date", existing.date),
                                        format_id=sample.get("format_id", existing.format_id),
                                        player_count=int(sample.get("player_count", 0) or existing.player_count or 0),
                                        store=ev_store or existing.store,
                                        location=ev_location or existing.location,
                                    )
                                session.query(_db.DeckRow).filter(
                                    _db.DeckRow.event_id == eid,
                                    _db.DeckRow.origin == _db.ORIGIN_MTGTOP8,
                                ).delete(synchronize_session=False)
                            for d in deck_dicts:
                                _resolve_deck_player(session, d)
                                _db.upsert_deck(session, d, origin=_db.ORIGIN_MTGTOP8)
                        else:
                            # Default: create events only if missing, upsert decks by deck_id
                            seen_event_ids = set()
                            for d in deck_dicts:
                                ev_id = d.get("event_id")
                                if ev_id is not None and ev_id not in seen_event_ids:
                                    seen_event_ids.add(ev_id)
                                    if _db.get_event(session, ev_id) is None:
                                        ev_name_raw = d.get("event_name", "")
                                        ev_name, ev_store, ev_location = parse_event_display(ev_name_raw)
                                        _db.create_event(
                                            session,
                                            event_name=ev_name or ev_name_raw or "Unnamed",
                                            date=d.get("date", ""),
                                            format_id=d.get("format_id", ""),
                                            origin=_db.ORIGIN_MTGTOP8,
                                            event_id=ev_id,
                                            player_count=int(d.get("player_count", 0)),
                                            store=ev_store,
                                            location=ev_location,
                                        )
                            for d in deck_dicts:
                                _resolve_deck_player(session, d)
                                _db.upsert_deck(session, d, origin=_db.ORIGIN_MTGTOP8)
                    _load_decks_from_db()
                    duration = time.time() - start_time
                    logger.info(
                        "Scrape completed: decks=%s events=%s duration_sec=%.1f force_replace=%s",
                        len(decks), len(events_in_run), duration, body.force_replace,
                    )
                except Exception as e:
                    logger.exception("Failed to persist scraped decks to DB: %s", e)
                    _decks = deck_dicts
                    _invalidate_metagame()
            else:
                _decks = deck_dicts
                _invalidate_metagame()
                duration = time.time() - start_time
                logger.info(
                    "Scrape completed: decks=%s events=%s duration_sec=%.1f (no DB)",
                    len(decks), len(events_in_run), duration,
                )
            loaded = len(_decks)
            num_events = len(events_in_run)
            cancelled = _scrape_cancel_event is not None and _scrape_cancel_event.is_set()
            message = f"Scraped {len(decks)} decks from {num_events} event{'s' if num_events != 1 else ''}"
            if cancelled:
                message = f"Stopped. {message}"
            yield f"data: {json.dumps({'type': 'cancelled' if cancelled else 'done', 'message': message, 'loaded': loaded, 'pct': 100})}\n\n"
        else:
            duration = time.time() - start_time
            logger.warning("Scrape ended with unknown error after %.1fs", duration)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Unknown error'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/v1/scrape/stop")
def stop_scrape(_: str = Depends(require_admin)):
    """Request the current scrape to stop. Takes effect after the next progress check."""
    global _scrape_cancel_event
    if _scrape_cancel_event is not None:
        _scrape_cancel_event.set()
    return {"message": "Stop requested"}


# Serve built frontend (production); static dir is populated by Dockerfile
STATIC_DIR = _project_root / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
    _index_path = STATIC_DIR / "index.html"

    @app.get("/", include_in_schema=False)
    def serve_index():
        if _index_path.exists():
            return FileResponse(_index_path)
        raise StarletteHTTPException(status_code=404)

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            raise StarletteHTTPException(status_code=404)
        if _index_path.exists():
            return FileResponse(_index_path)
        raise StarletteHTTPException(status_code=404)
