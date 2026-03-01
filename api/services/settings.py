"""Settings service for analyzer-related configuration and thresholds.

This module centralizes how rank weights, ignore-lands cards, and matchup
thresholds are stored and retrieved, so the rest of the codebase does not
need to know whether values come from JSON files or the database.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

from src.mtgtop8.analyzer import DEFAULT_IGNORE_LANDS_SET, RANK_WEIGHTS as DEFAULT_RANK_WEIGHTS
from src.mtgtop8.storage import load_json, save_json

try:
    # Optional database dependency: only used for matchups_min_matches
    from api import db as _db
except ImportError:  # pragma: no cover - during tooling/import edge cases
    _db = None  # type: ignore[assignment]


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = Path(os.getenv("DATA_DIR", str(_PROJECT_ROOT)))
if not _DATA_DIR.is_absolute():
    _DATA_DIR = _PROJECT_ROOT / _DATA_DIR
_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _ignore_lands_cards_path() -> Path:
    return _DATA_DIR / "ignore_lands_cards.json"


def _rank_weights_path() -> Path:
    return _DATA_DIR / "rank_weights.json"


def get_rank_weights() -> Dict[str, float]:
    """Load rank -> points mapping, falling back to analyzer defaults."""
    data = load_json(_rank_weights_path(), default={}, suppress_errors=True) or {}
    weights = data.get("weights")
    if isinstance(weights, dict):
        return {k: float(v) for k, v in weights.items() if isinstance(v, (int, float))}
    return dict(DEFAULT_RANK_WEIGHTS)


def set_rank_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Persist rank weights and return the canonical stored mapping."""
    # Filter out None values and coerce to float for consistency
    cleaned = {k: float(v) for k, v in weights.items() if v is not None}
    save_json(_rank_weights_path(), {"weights": cleaned}, indent=2, ensure_ascii=False)
    return get_rank_weights()


def get_ignore_lands_cards() -> List[str]:
    """Load ignore-lands card list, falling back to the default set."""
    data = load_json(_ignore_lands_cards_path(), default={}, suppress_errors=True) or {}
    cards = data.get("cards")
    if isinstance(cards, list) and all(isinstance(c, str) for c in cards):
        return sorted({c.strip() for c in cards if c and c.strip()})
    return sorted(DEFAULT_IGNORE_LANDS_SET)


def set_ignore_lands_cards(cards: List[str]) -> List[str]:
    """Persist ignore-lands card list and return the canonical stored list."""
    cleaned = [c.strip() for c in cards if isinstance(c, str) and c.strip()]
    unique_sorted = sorted({c for c in cleaned})
    save_json(_ignore_lands_cards_path(), {"cards": unique_sorted}, indent=2, ensure_ascii=False)
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

