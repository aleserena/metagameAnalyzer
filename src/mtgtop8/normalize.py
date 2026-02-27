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

