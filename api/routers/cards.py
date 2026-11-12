import logging

from fastapi import Depends, Header, Query, Request
from src.mtgtop8.card_lookup import UNRESOLVED, autocomplete_cards, lookup_cards

from api.dependencies import optional_admin
from api.schemas.auth_feedback import CardLookupBody
from api.services.rate_limit import RateLimiter, client_ip, rate_limited

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


# Names an anonymous request may send on to Scryfall when neither the cards table nor the
# Scryfall cache knows them. Enough for a newly released card or two on a deck page.
PUBLIC_FALLBACK_NAMES = 5
# How often anonymous requests may use that fallback at all: per client IP, and for the whole
# site (each use costs several Scryfall calls and holds a worker thread for a second or more).
# Over budget is not an error; the names simply stay "unresolved".
ANON_FALLBACK_IP_LIMITER = RateLimiter(6, 60)
ANON_FALLBACK_GLOBAL_LIMITER = RateLimiter(30, 60)
_GLOBAL_KEY = "all"


def _is_valid_link_token(token: str) -> bool:
    """True for an existing, unexpired upload / feedback / event-edit link token."""
    token = (token or "").strip()
    if not token or _db is None or not _db.is_database_available():
        return False
    with _db.session_scope() as session:
        row = _db.get_upload_link(session, token)
        return row is not None and (row.expires_at is None or row.expires_at >= _db.utcnow_naive())


def _anonymous_lookup(names: list[str], ip: str) -> dict:
    """Cards table and cache first; then, budget permitting, a few names from Scryfall."""
    result = lookup_cards(names, max_fallback=0)
    unresolved = [n for n in names if (result.get(n) or {}).get("error") == UNRESOLVED]
    if not unresolved:
        return result
    if not (ANON_FALLBACK_IP_LIMITER.allow(ip) and ANON_FALLBACK_GLOBAL_LIMITER.allow(_GLOBAL_KEY)):
        return result
    ANON_FALLBACK_IP_LIMITER.record(ip)
    ANON_FALLBACK_GLOBAL_LIMITER.record(_GLOBAL_KEY)
    result.update(lookup_cards(unresolved[:PUBLIC_FALLBACK_NAMES]))
    return result


# Per client IP. A deck page fires several lookups plus one per card hover, so this is loose.
LOOKUP_LIMITER = RateLimiter(600, 60)


@router.post("/api/v1/cards/lookup", dependencies=[Depends(rate_limited(LOOKUP_LIMITER))])
def cards_lookup(
    body: CardLookupBody,
    request: Request,
    admin: str | None = Depends(optional_admin),
    x_upload_token: str | None = Header(None, alias="X-Upload-Token"),
    x_event_edit_token: str | None = Header(None, alias="X-Event-Edit-Token"),
):
    """Look up card metadata and images (cards table, then the Scryfall fallback).

    Public. An admin, or the holder of a valid upload / feedback / event-edit link (validating a
    deck list they are entering), gets every name looked up. Anyone else gets the cards table and
    the cache, plus a small budgeted Scryfall fallback; names left over are ``unresolved``.
    """
    if not body.names:
        return {}
    if admin or any(_is_valid_link_token(t) for t in (x_upload_token, x_event_edit_token) if t):
        return lookup_cards(body.names, max_fallback=None)
    return _anonymous_lookup(list(dict.fromkeys(body.names)), client_ip(request))


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
