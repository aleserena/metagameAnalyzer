"""Card-name normalization helpers used across scraper and API."""

from __future__ import annotations

import re


def normalize_card_name(card: str) -> str:
    """Return a canonical card name for analysis and lookups.

    Normalization includes:
    - Trimming whitespace.
    - Converting split cards like ``'Fire / Ice'`` to ``'Fire // Ice'``.
    - Stripping trailing foiling markers like ``*F*`` / ``*C*``.
    - Stripping trailing set codes and collector numbers like ``(ECC) 1``.
    """
    if card is None:
        return ""
    if not isinstance(card, str):
        return str(card).strip()

    s = card.strip()

    # MTGTop8 uses single '/' for split cards; Scryfall expects '//'
    if " // " not in s and re.search(r"\s/\s", s):
        s = re.sub(r"\s+/\s+", " // ", s)

    # Trailing *F* *C* etc (foil/etched indicators)
    s = re.sub(r"\s*\*\w*\*(\s*\*\w*\*)*\s*$", "", s).strip()

    # Trailing (SET) or (SET) 123
    s = re.sub(r"\s*\([A-Za-z0-9]{2,5}\)\s*\d*\s*$", "", s, flags=re.IGNORECASE).strip()

    return s


def canonical_card_name_for_compare(card: str) -> str:
    """Return a canonical key for equality/comparison (double-faced = front face, case-insensitive).

    Double-faced cards may be stored as full name (\"Norman Osborn // Green Goblin\") or front only
    (\"Norman Osborn\"). For deck list validation and duplicate detection, treat them as the same
    by using the front face (part before \" // \") as the canonical key. Returns lowercase so
    all card comparisons are case-insensitive across the site.
    """
    if card is None or not isinstance(card, str):
        return (card or "").strip().lower()
    s = (card or "").strip()
    if " // " in s:
        s = s.split(" // ", 1)[0].strip()
    return s.lower()

