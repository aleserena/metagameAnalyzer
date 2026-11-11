"""Settings service for analyzer-related configuration and thresholds.

This module centralizes how rank weights, ignore-lands cards, and matchup
thresholds are stored and retrieved, so the rest of the codebase does not
need to know whether values come from JSON files or the database.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Dict, List

from src.mtgtop8.analyzer import DEFAULT_IGNORE_LANDS_SET, RANK_WEIGHTS as DEFAULT_RANK_WEIGHTS
from src.mtgtop8.storage import load_json, save_json

try:
    # Optional database dependency: only used for matchups_min_matches
    from api import db as _db
except ImportError:  # pragma: no cover - during tooling/import edge cases
    _db = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = Path(os.getenv("DATA_DIR", str(_PROJECT_ROOT)))
if not _DATA_DIR.is_absolute():
    _DATA_DIR = _PROJECT_ROOT / _DATA_DIR
_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _settings_dir() -> Path:
    """Directory for JSON-backed analyzer settings (rank weights, ignore-lands list)."""
    return _DATA_DIR / "settings"


def _ignore_lands_cards_path() -> Path:
    return _settings_dir() / "ignore_lands_cards.json"


def _rank_weights_path() -> Path:
    return _settings_dir() / "rank_weights.json"


_version = 0
_version_lock = threading.Lock()


def version() -> int:
    """Counter bumped whenever rank weights or the ignore-lands list change (cache key component)."""
    return _version


def _bump_version() -> None:
    global _version
    with _version_lock:
        _version += 1


RANK_WEIGHTS_KEY = "rank_weights"
IGNORE_LANDS_KEY = "ignore_lands_cards"

_cache: Dict[str, object] = {}
_cache_lock = threading.Lock()


def _reset_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()


def _cache_get(key: str):
    with _cache_lock:
        return _cache.get(key)


def _cache_put(key: str, value) -> None:
    with _cache_lock:
        _cache[key] = value


def _cache_drop(key: str) -> None:
    with _cache_lock:
        _cache.pop(key, None)


def _clean_weights(weights) -> Dict[str, float] | None:
    if isinstance(weights, dict):
        return {k: float(v) for k, v in weights.items() if isinstance(v, (int, float))}
    return None


def _clean_cards(cards) -> List[str] | None:
    if isinstance(cards, list) and all(isinstance(c, str) for c in cards):
        return sorted({c.strip() for c in cards if c and c.strip()})
    return None


def _file_value(path: Path, field: str, clean):
    """(file exists, cleaned value or None) from a legacy JSON settings file."""
    if not path.exists():
        return False, None
    data = load_json(path, default={}, suppress_errors=True) or {}
    return True, clean(data.get(field)) if isinstance(data, dict) else None


def _db_get(key: str, path: Path, field: str, clean, default):
    """Cache -> settings row -> legacy file (imported once) -> default.

    Errors and malformed files yield the default without caching or storing it, so a later read retries.
    """
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        with _db.session_scope() as session:
            stored = clean(_db.get_setting(session, key))
            if stored is not None:
                _cache_put(key, stored)
                return stored
            exists, value = _file_value(path, field, clean)
            if value is not None:
                _db.set_setting(session, key, value)
                _cache_put(key, value)
                return value
            if not exists:
                _cache_put(key, default)
            return default
    except Exception:
        logger.exception("Could not read setting %s from the database; using defaults", key, extra={"email": False})
        return default


def _db_set(key: str, value) -> None:
    with _db.session_scope() as session:
        _db.set_setting(session, key, value)
    _cache_drop(key)


def get_rank_weights() -> Dict[str, float]:
    """Load rank -> points mapping, falling back to analyzer defaults."""
    default = dict(DEFAULT_RANK_WEIGHTS)
    if _db_available():
        return dict(_db_get(RANK_WEIGHTS_KEY, _rank_weights_path(), "weights", _clean_weights, default))
    _, value = _file_value(_rank_weights_path(), "weights", _clean_weights)
    return value if value is not None else default


def set_rank_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Persist rank weights and return the canonical stored mapping."""
    # Filter out None values and coerce to float for consistency
    cleaned = {k: float(v) for k, v in weights.items() if v is not None}
    if _db_available():
        _db_set(RANK_WEIGHTS_KEY, cleaned)
    else:
        save_json(_rank_weights_path(), {"weights": cleaned}, indent=2, ensure_ascii=False)
    _bump_version()
    return get_rank_weights()


def get_ignore_lands_cards() -> List[str]:
    """Load ignore-lands card list, falling back to the default set."""
    default = sorted(DEFAULT_IGNORE_LANDS_SET)
    if _db_available():
        return list(_db_get(IGNORE_LANDS_KEY, _ignore_lands_cards_path(), "cards", _clean_cards, default))
    _, value = _file_value(_ignore_lands_cards_path(), "cards", _clean_cards)
    return value if value is not None else default


def set_ignore_lands_cards(cards: List[str]) -> List[str]:
    """Persist ignore-lands card list and return the canonical stored list."""
    cleaned = [c.strip() for c in cards if isinstance(c, str) and c.strip()]
    unique_sorted = sorted({c for c in cleaned})
    if _db_available():
        _db_set(IGNORE_LANDS_KEY, unique_sorted)
    else:
        save_json(_ignore_lands_cards_path(), {"cards": unique_sorted}, indent=2, ensure_ascii=False)
    _bump_version()
    return get_ignore_lands_cards()


def _db_available() -> bool:
    return _db is not None and _db.is_database_available()


def get_matchups_min_matches() -> int:
    """Return minimum matches threshold for matchup summary (0 when DB is unavailable)."""
    if not _db_available():
        return 0
    with _db.session_scope() as session:
        return _db.get_matchups_min_matches(session)


def set_matchups_min_matches(value: int) -> int:
    """Persist minimum matches threshold for matchup summary (no-op when DB is unavailable)."""
    value = max(0, int(value))
    if not _db_available():
        return value
    with _db.session_scope() as session:
        _db.set_matchups_min_matches(session, value)
    return value


def get_matchups_players_min_matches() -> int:
    """Return minimum matches threshold for player matchup summary (0 when DB is unavailable)."""
    if not _db_available():
        return 0
    with _db.session_scope() as session:
        return _db.get_matchups_players_min_matches(session)


def set_matchups_players_min_matches(value: int) -> int:
    """Persist minimum matches threshold for player matchup summary (no-op when DB is unavailable)."""
    value = max(0, int(value))
    if not _db_available():
        return value
    with _db.session_scope() as session:
        _db.set_matchups_players_min_matches(session, value)
    return value

