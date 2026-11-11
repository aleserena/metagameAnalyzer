"""Format helpers shared by routers and services."""

_COMMANDER_FORMATS = frozenset({"EDH", "CEDH", "COMMANDER"})


def is_commander_format(format_id: str | None) -> bool:
    """True for the commander-style formats (EDH, cEDH, Commander), in any letter case."""
    return (format_id or "").strip().upper() in _COMMANDER_FORMATS
