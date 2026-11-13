"""Card-name normalization helpers used across scraper and API."""

from __future__ import annotations

import re

# Written as linear string scans rather than anchored regexes: card and archetype names come from
# scraped pages and user input, and patterns like ``\s+/\s+`` or ``\s*...\s*$`` backtrack
# quadratically on long runs of spaces (CodeQL py/polynomial-redos).
_SPLIT_SEPARATOR_RE = re.compile(r"\s/\s")
_WORD_RE = re.compile(r"\w*")
_ASCII_ALNUM = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")


def double_split_separators(s: str) -> str:
    """``'Fire / Ice'`` -> ``'Fire // Ice'`` (whitespace around each single slash collapses to one space).

    Leaves names that already contain `` // `` alone.
    """
    if " // " in s or not _SPLIT_SEPARATOR_RE.search(s):
        return s
    # Same result as re.sub(r"\s+/\s+", " // ", s), in one pass.
    out: list[str] = []
    n = len(s)
    i = last = 0
    while i < n:
        if not s[i].isspace():
            i += 1
            continue
        j = i
        while j < n and s[j].isspace():
            j += 1
        if j + 1 < n and s[j] == "/" and s[j + 1].isspace():
            k = j + 1
            while k < n and s[k].isspace():
                k += 1
            out += [s[last:i], " // "]
            last = k
        i = max(j, last)
    out.append(s[last:])
    return "".join(out)


def _strip_foil_markers(s: str) -> str:
    """Drop trailing ``*F*`` / ``*C*`` style markers (any number, optionally space-separated)."""
    s = s.rstrip()
    while s.endswith("*"):
        start = s.rfind("*", 0, len(s) - 1)
        if start < 0 or not _WORD_RE.fullmatch(s, start + 1, len(s) - 1):
            break
        s = s[:start].rstrip()
    return s


def _strip_set_code(s: str) -> str:
    """Drop a trailing ``(SET)`` or ``(SET) 123`` (set code: 2-5 ASCII letters/digits)."""
    tail = s.rstrip().rstrip("0123456789").rstrip()
    if not tail.endswith(")"):
        return s
    start = tail.rfind("(")
    code = tail[start + 1 : -1]
    if start < 0 or not 2 <= len(code) <= 5 or not set(code) <= _ASCII_ALNUM:
        return s
    return tail[:start]


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
    s = double_split_separators(s)

    # Trailing *F* *C* etc (foil/etched indicators)
    s = _strip_foil_markers(s).strip()

    # Trailing (SET) or (SET) 123
    s = _strip_set_code(s).strip()

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

