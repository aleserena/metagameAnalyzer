"""Per-data-version indexes over ``state.decks``: duplicate groups and commander colors.

Both values depend only on the deck list (and, for colors, on card data, which
bumps ``state.decks_version`` via ``state.touch()`` after a sync), so each is
computed at most once per version. One lock guards both so concurrent cold
callers trigger a single computation.
"""

import logging
import threading

from api.state import state
from src.mtgtop8.analyzer import effective_commanders, find_duplicate_decks
from src.mtgtop8.card_lookup import lookup_cards
from src.mtgtop8.models import Deck

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_duplicates: tuple[int, dict[int, list[int]]] | None = None
_colors: tuple[int, dict[int, list[str]]] | None = None

_COLOR_ORDER = ["W", "U", "B", "R", "G", "C"]
_BASIC = {"W", "U", "B", "R", "G"}
_EDH_FORMATS = {"EDH", "CEDH", "COMMANDER"}


def duplicate_map() -> dict[int, list[int]]:
    """``find_duplicate_decks`` over all of ``state.decks``, cached per data version."""
    global _duplicates
    with _lock:
        version = state.decks_version
        if _duplicates is None or _duplicates[0] != version:
            decks = [Deck.from_dict(d) for d in state.decks]
            _duplicates = (version, find_duplicate_decks(decks))
        return _duplicates[1]


def _build_color_identities(deck_dicts: list[dict]) -> dict[int, list[str]]:
    deck_objs = [Deck.from_dict(d) for d in deck_dicts]
    commander_names = list({c for deck in deck_objs for c in effective_commanders(deck) if c})
    metadata = lookup_cards(commander_names) if commander_names else {}
    result: dict[int, list[str]] = {}
    for deck_obj, d in zip(deck_objs, deck_dicts):
        ec = effective_commanders(deck_obj)
        ci: set[str] = set()
        for name in ec:
            entry = metadata.get(name)
            if entry and "error" not in entry:
                for c in entry.get("color_identity") or entry.get("colors") or []:
                    if c in _BASIC:
                        ci.add(c)
        # EDH/Commander decks with commanders but no colors are colorless ("C").
        if not ci and ec and (deck_obj.format_id or "").upper() in _EDH_FORMATS:
            ci.add("C")
        if ci:
            result[d.get("deck_id")] = [c for c in _COLOR_ORDER if c in ci]
    return result


def color_identities() -> dict[int, list[str]]:
    """deck_id -> commander colors (W,U,B,R,G then C), cached per data version.

    A lookup failure is logged and yields an empty map for that version.
    """
    global _colors
    with _lock:
        version = state.decks_version
        if _colors is None or _colors[0] != version:
            try:
                value = _build_color_identities(state.decks)
            except Exception:
                # Color identity is cosmetic; do not fail requests over it.
                logger.exception("Color identity lookup failed")
                value = {}
            _colors = (version, value)
        return _colors[1]
