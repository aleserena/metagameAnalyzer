"""Shared in-memory application state and the helpers that read/mutate it.

`state` is a single holder object (stable reference) so that routers in other
modules always see the current decks/caches even after they are reassigned —
unlike a plain module global, which a `from api.state import _decks` would
capture once and never see updated.
"""

import logging
import threading
from pathlib import Path

from src.mtgtop8.models import Deck
from src.mtgtop8.storage import load_json, save_json

from api.config import DATA_DIR
from api.helpers import _event_from_deck_dict, _normalize_split_cards

try:
    from api import db as _db
except ImportError:
    _db = None

logger = logging.getLogger(__name__)


class AppState:
    """Process-wide mutable state for the API (in-memory deck list + caches)."""

    def __init__(self) -> None:
        self.decks: list[dict] = []
        self.metagame_cache: dict | None = None
        self.events_cache: list[dict] | None = None  # cached list for GET /api/events
        self.player_aliases: dict[str, str] = {}  # alias -> canonical
        self.scrape_cancel_event: threading.Event | None = None

    def database_available(self) -> bool:
        """Whether the DB is configured and reachable.

        Routes call this via the shared `state` singleton so tests can patch a
        single point (`state.database_available`) regardless of which router a
        handler lives in.
        """
        return _database_available()


state = AppState()


def _database_available() -> bool:
    return _db is not None and _db.is_database_available()


def _aliases_path() -> Path:
    return DATA_DIR / "player_aliases.json"


def _load_player_aliases() -> None:
    if _database_available():
        try:
            with _db.session_scope() as session:
                state.player_aliases = _db.get_player_aliases(session)
        except Exception as e:
            logger.exception("Failed to load player aliases from DB: %s", e)
            state.player_aliases = {}
        return
    data = load_json(_aliases_path(), default={}, suppress_errors=True)
    state.player_aliases = data or {}


def _save_player_aliases() -> None:
    if _database_available():
        try:
            with _db.session_scope() as session:
                for alias, canonical in state.player_aliases.items():
                    _db.set_player_alias(session, alias, canonical)
        except Exception as e:
            logger.exception("Failed to save player aliases to DB: %s", e)
        return
    save_json(_aliases_path(), state.player_aliases, indent=2, ensure_ascii=False)


def _normalize_player(name: str) -> str:
    """Return canonical player name (alias -> canonical mapping). Follows chains so nested aliases resolve."""
    if not name or not name.strip():
        return "(unknown)"
    n = name.strip()
    seen: set[str] = set()
    while n in state.player_aliases and n not in seen:
        seen.add(n)
        n = (state.player_aliases[n] or "").strip() or n
    return n


def _resolve_deck_player(session, d: dict) -> None:
    """Set d['player_id'] and d['player'] (display name) from d['player'] (name). Resolve via aliases/players; create player if missing."""
    name = (d.get("player") or "").strip() or "(unknown)"
    pid, display = _db.resolve_name_to_player_id(session, name)
    if pid is None:
        pid, display = _db.get_or_create_player(session, name)
    d["player_id"] = pid
    d["player"] = display


def _get_decks() -> list[Deck]:
    return [Deck.from_dict(d) for d in state.decks]


def _get_deck_by_id(deck_id: int) -> dict | None:
    """Return deck dict by deck_id or None if not found."""
    for d in state.decks:
        if d.get("deck_id") == deck_id:
            return d
    return None


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
    for d in state.decks:
        if str(d.get("event_id")) == str(event_id):
            return _event_from_deck_dict(d)
    return None


def _invalidate_metagame() -> None:
    state.metagame_cache = None
    state.events_cache = None


def _invalidate_events_cache() -> None:
    """Clear cached events list so next GET /api/events recomputes."""
    state.events_cache = None


def _load_from_file(path: str) -> None:
    data = load_json(path, default=[], suppress_errors=False)
    state.decks = _normalize_split_cards(data or [])
    _invalidate_metagame()


def _load_decks_from_db() -> None:
    """Load all decks from DB into state.decks. No-op if DB not available."""
    if not _database_available():
        return
    try:
        with _db.session_scope() as session:
            state.decks = _db.get_all_decks(session)
        _invalidate_metagame()
    except Exception as e:
        logger.exception("Failed to load decks from DB: %s", e)


def _persist_decks_to_db(decks: list[dict], origin: str = None) -> None:
    """Write decks to DB (upsert each). Resolve player name to player_id before each upsert. Then reload state.decks from DB."""
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
    """Delete all decks in DB, then clear state.decks."""
    if not _database_available() or _db is None:
        return
    try:
        with _db.session_scope() as session:
            session.query(_db.DeckRow).delete()
        state.decks = []
        _invalidate_metagame()
    except Exception as e:
        logger.exception("Failed to clear decks in DB: %s", e)


# Load player aliases and decks on startup (DB only; no JSON fallback for decks).
_load_player_aliases()

if _database_available():
    try:
        _load_decks_from_db()
    except Exception as e:
        logger.exception("Failed to load decks from DB at startup: %s", e)
