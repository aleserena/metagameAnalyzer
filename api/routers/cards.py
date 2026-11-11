import logging

from fastapi import Depends, Query
from src.mtgtop8.card_lookup import autocomplete_cards, lookup_cards

from api.dependencies import optional_admin
from api.schemas.auth_feedback import CardLookupBody
from api.services.rate_limit import RateLimiter, rate_limited

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


# Names an anonymous request may send on to Scryfall when the cards table does not know them.
# Enough for a newly released card or two on a deck page; too few to turn the API into a relay.
PUBLIC_FALLBACK_NAMES = 5


# Per client IP. A deck page fires several lookups plus one per card hover, so this is loose.
LOOKUP_LIMITER = RateLimiter(600, 60)


@router.post("/api/v1/cards/lookup", dependencies=[Depends(rate_limited(LOOKUP_LIMITER))])
def cards_lookup(body: CardLookupBody, admin: str | None = Depends(optional_admin)):
    """Look up card metadata and images (cards table, then a bounded Scryfall fallback).

    Public. Anonymous callers get at most PUBLIC_FALLBACK_NAMES live Scryfall lookups per
    request; an admin gets the full fallback.
    """
    if not body.names:
        return {}
    return lookup_cards(body.names, max_fallback=None if admin else PUBLIC_FALLBACK_NAMES)


@router.get("/api/v1/cards/search")
def cards_search(
    q: str = Query("", description="Card name prefix for autocomplete"),
    role: str | None = Query(
        None,
        description=(
            "Optional commander/partner role filter: commander, partner, "
            "friends_forever, background, doctors_companion, time_lord_doctor"
        ),
    ),
):
    """Return card names matching the query prefix, optionally filtered by role."""
    data = autocomplete_cards(q, role=role)
    return {"data": data}
