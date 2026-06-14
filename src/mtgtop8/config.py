"""Configuration: format IDs, meta values, constants."""

import os

BASE_URL = "https://www.mtgtop8.com"
REQUEST_DELAY_SECONDS = 1.5
MAX_RETRIES = 3

# Parallel deck page fetches per event (1 = sequential; 2–8 for bounded parallelism)
_workers = os.getenv("SCRAPER_MAX_WORKERS", "1").strip()
try:
    SCRAPER_MAX_WORKERS = max(1, min(8, int(_workers)))
except ValueError:
    SCRAPER_MAX_WORKERS = 1

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

# Standard meta. Only a few periods are mapped so far — see note below to extend.
META_ST: dict[str, int] = {
    "Last 2 Weeks": 50,
    "Last 2 Months": 52,
    "All 2026 Decks": 341,
}

# Period -> mtgtop8 meta-ID maps, keyed by format. Meta IDs are FORMAT-SPECIFIC:
# the same period label (e.g. "Last 2 Months") has a different `meta` value per
# format, so there is no safe cross-format fallback (see get_meta_value below).
#
# To add support for another format (e.g. Modern "MO", Legacy "LE", Pioneer "PI"):
#   1. Open that format's page on mtgtop8.com and use its time-period dropdown.
#   2. For each period, read the `meta=<N>` value from the resulting URL
#      (https://www.mtgtop8.com/format?f=<FMT>&meta=<N>).
#   3. Add a `META_<FMT>: dict[str, int]` map above, then register it here.
# Until a format is added, scraping it with a --period filter fails fast
# (get_meta_value returns None) rather than scraping the wrong events.
META_BY_FORMAT: dict[str, dict[str, int]] = {
    "EDH": META_EDH,
    "cEDH": META_EDH,
    "ST": META_ST,
}

# Used by the scraper only when neither a period nor an explicit meta is given
DEFAULT_META = META_EDH


def get_meta_value(format_id: str, period: str) -> int | None:
    """Get meta value for format and period.

    Returns None when the format has no meta map of its own — meta IDs are
    format-specific on mtgtop8, so guessing another format's ID would silently
    scrape the wrong event set.
    """
    meta_map = META_BY_FORMAT.get(format_id)
    if meta_map is None:
        return None
    return meta_map.get(period)
