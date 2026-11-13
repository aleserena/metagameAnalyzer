"""Single-elimination bracket rules: the one place for bracket maths (mirrored in web/src/lib/matchups.ts).

An event's ``structure`` is ``"swiss"`` (Swiss rounds + Top 8; NULL in the DB means the same) or
``"single_elimination"`` (a knockout bracket of ``bracket_size`` players, rounds numbered 1..log2(size)).
A deck's rank says how far it went, so it also says how many matches it played and which round it lost in.
"""

from __future__ import annotations

from src.mtgtop8.analyzer import normalize_rank

STRUCTURE_SWISS = "swiss"
STRUCTURE_SINGLE_ELIM = "single_elimination"
VALID_BRACKET_SIZES = (2, 4, 8, 16, 32, 64, 128)


def is_single_elimination(structure: str | None) -> bool:
    return structure == STRUCTURE_SINGLE_ELIM


def validate_structure(structure: str | None, bracket_size: int | None) -> tuple[str, int | None]:
    """Normalized ``(structure, bracket_size)``; Swiss never keeps a bracket size. Raises ValueError."""
    s = (structure or "").strip() or STRUCTURE_SWISS
    if s == STRUCTURE_SWISS:
        return STRUCTURE_SWISS, None
    if s != STRUCTURE_SINGLE_ELIM:
        raise ValueError(f"Unknown event structure {s!r} (expected 'swiss' or 'single_elimination')")
    if bracket_size not in VALID_BRACKET_SIZES:
        raise ValueError(
            f"Bracket size {bracket_size!r} is not valid for single elimination "
            f"(expected one of {', '.join(map(str, VALID_BRACKET_SIZES))})"
        )
    return STRUCTURE_SINGLE_ELIM, bracket_size


def bracket_rounds(bracket_size: int) -> int:
    """Rounds in a bracket: 16 players -> 4."""
    return max(0, int(bracket_size).bit_length() - 1)


def rank_band_upper(rank: str | None) -> int | None:
    """Upper bound of the rank's band: '1' -> 1, '3-4' -> 4, '7' -> 8; None when the rank has no band."""
    band = normalize_rank(rank or "")
    if not band:
        return None
    return int(band.split("-")[-1])


def expected_matches_for_rank(rank: str | None, bracket_size: int) -> int:
    """Matches a deck with this rank played: 9-16 in a 16 bracket -> 1, finalists -> 4.

    0 when the rank is outside the bracket; 1 when the rank is unknown (the deck played at least once)."""
    upper = rank_band_upper(rank)
    rounds = bracket_rounds(bracket_size)
    if upper is None:
        return 1
    if upper > bracket_size:
        return 0
    return min(rounds, rounds - bracket_rounds(upper) + 1)


def elimination_round(rank: str | None, bracket_size: int) -> int | None:
    """The round a deck with this rank lost in (2 in a 16 bracket -> 4, the final).

    None for the winner, an unknown rank, or a rank outside the bracket."""
    upper = rank_band_upper(rank)
    if upper is None or upper == 1 or upper > bracket_size:
        return None
    return bracket_rounds(bracket_size) - bracket_rounds(upper) + 1


def round_label(round_no: int, bracket_size: int) -> str:
    """'Round of 16', 'Quarterfinal', 'Semifinal', 'Final' for bracket round ``round_no`` (1-based)."""
    left = bracket_size >> (round_no - 1)
    return {2: "Final", 4: "Semifinal", 8: "Quarterfinal"}.get(left, f"Round of {left}")
