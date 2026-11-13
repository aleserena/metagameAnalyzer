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

logger = logging.getLogger(__name__)

# Set when api.db fails to import, so the startup DB check can report it instead of the
# app silently running without a database.
db_import_error: str | None = None
try:
    from api import db as _db
except ImportError as e:
    _db = None
    db_import_error = f"Could not import api.db: {e}"
    logger.error("%s. Database features disabled.", db_import_error, extra={"event": "db_unavailable"})


class AppState:
    """Process-wide mutable state for the API (in-memory deck list + caches)."""

    def __init__(self) -> None:
        self.decks: list[dict] = []
        self.decks_version: int = 0  # bumped by set_decks so version-keyed caches can detect changes
        self.metagame_cache: dict[tuple, dict] = {}  # finished /metagame responses keyed by version + query
        self.events_cache: list[dict] | None = None  # cached list for GET /api/events
        self.player_aliases: dict[str, str] = {}  # alias -> canonical
        self._version_lock = threading.Lock()

    def set_decks(self, decks: list[dict]) -> None:
        """Replace the in-memory deck list and drop everything derived from it."""
        self.decks = decks
        self.touch()

    def touch(self) -> None:
        """Drop everything derived from the decks (e.g. after card data changes) without replacing them."""
        with self._version_lock:
            self.decks_version += 1
        self.metagame_cache = {}
        self.events_cache = None

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
    state.touch()


def _invalidate_events_cache() -> None:
    """Clear cached events list so next GET /api/events recomputes."""
    state.events_cache = None


def _read_decks_file(path: str) -> list[dict]:
    """Read and normalize a decks JSON file without touching ``state``."""
    data = load_json(path, default=[], suppress_errors=False)
    return _normalize_split_cards(data or [])


def _load_decks_from_db(*, strict: bool = False) -> None:
    """Load all decks from DB into state.decks. No-op if DB not available.

    state.decks is only replaced after the query succeeds. With ``strict`` a failure is
    re-raised (so a caller can report it) instead of being logged and swallowed.
    """
    if not _database_available():
        return
    try:
        with _db.session_scope() as session:
            state.set_decks(_db.get_all_decks(session))
    except Exception as e:
        logger.exception("Failed to load decks from DB: %s", e)
        if strict:
            raise


def log_split_player_identities() -> None:
    """Warn when an alias string still has a ``players`` row of its own.

    That duplicate splits one person across two ids: the leaderboard merges them by
    name, but the matchup matrix keys off the id and shows two separate rows, so
    neither carries the player's full record. Detection only — the merge is applied
    deliberately via ``scripts.merge_alias_duplicate_players``.
    """
    if not state.database_available():
        return
    try:
        with _db.session_scope() as session:
            dupes = _db.collect_alias_duplicate_player_merges(session)
    except Exception as e:
        logger.warning("Could not check for split player identities: %s", e)
        return
    if not dupes:
        return
    detail = "; ".join(f"{alias!r} (id={dup_id}) -> id={canon_id}" for dup_id, canon_id, alias in dupes)
    logger.warning(
        "Split player identities detected (%d): %s. These players appear twice on the "
        "matchup matrix. Fix with: python3 -m scripts.merge_alias_duplicate_players --apply",
        len(dupes),
        detail,
        extra={"event": "split_player_identities", "count": len(dupes)},
    )


def _persist_decks_to_db(decks: list[dict], origin: str = None, *, assign_manual_ids: bool = False) -> None:
    """Write decks to DB (upsert each). Resolve player name to player_id before each upsert. Then reload state.decks from DB.

    With ``assign_manual_ids``, decks whose deck_id is missing or below MANUAL_DECK_ID_START get consecutive
    manual IDs, allocated in the persisting transaction (advisory lock held until the decks are committed).
    """
    if not _database_available() or _db is None:
        return
    if origin is None:
        origin = _db.ORIGIN_MTGTOP8
    try:
        with _db.session_scope() as session:
            if assign_manual_ids:
                needs_id = [
                    d
                    for d in decks
                    if d.get("deck_id") is None
                    or (isinstance(d.get("deck_id"), int) and d["deck_id"] < _db.MANUAL_DECK_ID_START)
                ]
                if needs_id:
                    next_id = _db.next_manual_deck_id(session)
                    explicit = [d["deck_id"] for d in decks if isinstance(d.get("deck_id"), int) and d not in needs_id]
                    if explicit:
                        next_id = max(next_id, max(explicit) + 1)
                    for d in needs_id:
                        d["deck_id"] = next_id
                        next_id += 1
            for d in decks:
                if "player_id" not in d:
                    _resolve_deck_player(session, d)
                _db.upsert_deck(session, d, origin=origin)
    except Exception:
        logger.exception("Failed to persist decks to DB")
        raise
    _load_decks_from_db()


def _clear_decks_in_db() -> None:
    """Snapshot every event that has decks, delete all decks in DB, then clear state.decks."""
    if not _database_available() or _db is None:
        return
    from api.services.snapshots import REASON_CLEAR_DECKS, take_snapshot  # imports api.db only; kept local

    try:
        with _db.session_scope() as session:
            event_ids = [eid for (eid,) in session.query(_db.DeckRow.event_id).distinct()]
            for event_id in event_ids:
                take_snapshot(session, event_id, REASON_CLEAR_DECKS)
            session.query(_db.DeckRow).delete()
    except Exception:
        logger.exception("Failed to clear decks in DB")
        raise
    state.set_decks([])


# Load player aliases and decks on startup (DB only; no JSON fallback for decks).
_load_player_aliases()

if _database_available():
    try:
        _load_decks_from_db()
    except Exception as e:
        logger.exception("Failed to load decks from DB at startup: %s", e)
