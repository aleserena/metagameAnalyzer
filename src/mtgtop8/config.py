"""Configuration: format IDs, meta values, constants."""

BASE_URL = "https://www.mtgtop8.com"
REQUEST_DELAY_SECONDS = 1.5
MAX_RETRIES = 3

# Format IDs (f parameter)
FORMATS: dict[str, str] = {
    "ST": "Standard",
    "PI": "Pioneer",
    "MO": "Modern",
    "LE": "Legacy",
    "VI": "Vintage",
    "PAU": "Pauper",
    "cEDH": "cEDH",
    "EDH": "Duel Commander",
    "PREM": "Premodern",
    "EXP": "Explorer",
    "HI": "Historic",
    "ALCH": "Alchemy",
    "PEA": "Peasant",
    "BL": "Block",
    "EX": "Extended",
    "HIGH": "Highlander",
    "CHL": "Canadian Highlander",
}

# Meta values for time period (format-specific; these are for EDH)
# Same labels may map to different IDs per format
META_EDH: dict[str, int] = {
    "Last 7 Days": 328,
    "Last 2 Weeks": 115,
    "Last 2 Months": 121,
    "MTGO Last 2 Months": 306,
    "Paper Last 2 Months": 308,
    "Last Major Events (3 Months)": 130,
    "Last 6 Months": 209,
    "All 2026 Decks": 343,
    "All 2025 Decks": 310,
    "All 2024 Decks": 283,
    "All 2023 Decks": 252,
    "Major Events": 196,
    "All Commander decks": 56,
}

# Standard meta (from docs)
META_ST: dict[str, int] = {
    "Last 2 Weeks": 50,
    "Last 2 Months": 52,
    "All 2026 Decks": 341,
}

# Fallback: use EDH meta for Commander formats, ST for others
META_BY_FORMAT: dict[str, dict[str, int]] = {
    "EDH": META_EDH,
    "cEDH": META_EDH,
    "ST": META_ST,
}

# Default meta when format not in META_BY_FORMAT (use EDH as fallback)
DEFAULT_META = META_EDH


def get_meta_value(format_id: str, period: str) -> int | None:
    """Get meta value for format and period."""
    meta_map = META_BY_FORMAT.get(format_id, DEFAULT_META)
    return meta_map.get(period)
