import logging

from fastapi import Query
from src.mtgtop8.card_lookup import autocomplete_cards, lookup_cards

from api.schemas.auth_feedback import CardLookupBody

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/v1/cards/lookup")
def cards_lookup(body: CardLookupBody):
    """Look up card metadata and images from Scryfall."""
    if not body.names:
        return {}
    return lookup_cards(body.names)


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
