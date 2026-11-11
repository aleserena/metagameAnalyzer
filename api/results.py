"""Single vocabulary for match results (no imports from ``api``).

Every statistic (matrix, player win%, head-to-head, health score) classifies a
stored result string through ``effective_wld`` so they all agree. Intentional
draws with a winner count as a win/loss; a plain intentional draw is a draw.
"""

WIN_RESULTS = ("win", "intentional_draw_win", "2-1", "1-0")
LOSS_RESULTS = ("loss", "intentional_draw_loss", "1-2", "0-1")
DRAW_RESULTS = ("draw", "intentional_draw", "1-1", "0-0")
COUNTED_RESULTS = WIN_RESULTS + LOSS_RESULTS + DRAW_RESULTS


def effective_wld(result: str | None) -> tuple[int, int, int] | None:
    """Return (wins, losses, draws) for one result, or None for bye/drop/empty.

    Unknown strings count as a draw.
    """
    r = (result or "").strip().lower()
    if not r or r in ("bye", "drop"):
        return None
    if r in WIN_RESULTS:
        return (1, 0, 0)
    if r in LOSS_RESULTS:
        return (0, 1, 0)
    return (0, 0, 1)


def invert_result(result: str) -> str:
    """Return the opponent's result: win<->loss, intentional_draw_win<->intentional_draw_loss; others unchanged."""
    r = (result or "").strip().lower()
    if r in ("win", "2-1", "1-0"):
        return "loss"
    if r in ("loss", "1-2", "0-1"):
        return "win"
    if r == "intentional_draw_win":
        return "intentional_draw_loss"
    if r == "intentional_draw_loss":
        return "intentional_draw_win"
    return result
