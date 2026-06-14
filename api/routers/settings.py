import logging

from fastapi import Depends, Query
from src.mtgtop8.card_lookup import clear_cache as clear_scryfall_cache
from src.mtgtop8.card_lookup import refresh_otag_index

from api.dependencies import (
    require_admin,
    require_database,
)
from api.schemas.settings import (
    IgnoreLandsCardsBody,
    MatchupsMinMatchesBody,
    RankWeightsBody,
)
from api.services import mtgjson as mtgjson_service
from api.services import settings as settings_service
from api.state import (
    _clear_decks_in_db,
    _invalidate_metagame,
    state,
)

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/v1/settings/ignore-lands-cards")
def get_ignore_lands_cards(_: str = Depends(require_admin)):
    """Return list of card names excluded when 'Ignore lands' is checked (admin-only)."""
    return {"cards": settings_service.get_ignore_lands_cards()}


@router.put("/api/v1/settings/ignore-lands-cards")
def put_ignore_lands_cards(body: IgnoreLandsCardsBody, _: str = Depends(require_admin)):
    """Update list of cards excluded when 'Ignore lands' is checked (admin-only)."""
    return {"cards": settings_service.set_ignore_lands_cards(body.cards)}


@router.get("/api/v1/settings/rank-weights")
def get_rank_weights(_: str = Depends(require_admin)):
    """Return points per placement (1st, 2nd, 3-4, etc.). Admin-only."""
    return {"weights": settings_service.get_rank_weights()}


@router.put("/api/v1/settings/rank-weights")
def put_rank_weights(body: RankWeightsBody, _: str = Depends(require_admin)):
    """Update points per placement (admin-only)."""
    return {"weights": settings_service.set_rank_weights(body.weights)}


@router.get("/api/v1/settings/matchups-min-matches", dependencies=[Depends(require_admin), Depends(require_database)])
def get_matchups_min_matches_setting():
    """Legacy stored setting; the Matchups page uses ``GET /matchups/summary?min_matches=`` instead."""
    return {"value": settings_service.get_matchups_min_matches()}


@router.put("/api/v1/settings/matchups-min-matches", dependencies=[Depends(require_admin), Depends(require_database)])
def put_matchups_min_matches_setting(body: MatchupsMinMatchesBody):
    """Legacy stored setting (e.g. scripts); summary endpoints do not read this value."""
    n = settings_service.set_matchups_min_matches(body.value)
    return {"value": n}


@router.get("/api/v1/settings/matchups-players-min-matches", dependencies=[Depends(require_admin), Depends(require_database)])
def get_matchups_players_min_matches_setting():
    """Legacy stored setting; the Matchups page uses ``GET /matchups/players-summary?min_matches=`` instead."""
    return {"value": settings_service.get_matchups_players_min_matches()}


@router.put("/api/v1/settings/matchups-players-min-matches", dependencies=[Depends(require_admin), Depends(require_database)])
def put_matchups_players_min_matches_setting(body: MatchupsMinMatchesBody):
    """Legacy stored setting (e.g. scripts); players-summary does not read this value."""
    n = settings_service.set_matchups_players_min_matches(body.value)
    return {"value": n}


@router.post("/api/v1/settings/clear-cache")
def post_clear_scryfall_cache(_: str = Depends(require_admin)):
    """Clear Scryfall card lookup cache (in-memory and .scryfall_cache.json). Admin-only."""
    clear_scryfall_cache()
    return {"message": "Scryfall cache cleared"}


@router.post("/api/v1/settings/refresh-otag-index")
def post_refresh_otag_index(
    categories: list[str] | None = None,
    _: str = Depends(require_admin),
):
    """Rebuild the oracle tag index used for deck functional-stats categories.

    Queries Scryfall search (otag:X) for each category and persists the card→[categories]
    mapping to .scryfall_otag_cache.json. Pass a subset of category keys to refresh
    only those; omit to refresh all. Admin-only. Takes 1–5 minutes on first run.
    """
    counts = refresh_otag_index(categories)
    return {"refreshed": counts}


@router.post("/api/v1/settings/sync-mtgjson", dependencies=[Depends(require_database)])
def post_sync_mtgjson(_: str = Depends(require_admin)):
    """Start a background MTGJSON metadata sync; refreshes the ``cards`` table. Admin-only.

    Streams AtomicCards + AllIdentifiers (+ SetList) and upserts card metadata,
    scryfall_id and a representative printing UUID (price columns untouched —
    use sync-mtgjson-prices). Runs in a background thread (large download, minutes);
    poll ``GET /settings/sync-mtgjson/status``. Returns {started, running, message}.
    """
    return mtgjson_service.start_sync_job("metadata")


@router.post("/api/v1/settings/sync-mtgjson-prices", dependencies=[Depends(require_database)])
def post_sync_mtgjson_prices(_: str = Depends(require_admin)):
    """Start a background MTGJSON price sync (AllPricesToday). Admin-only.

    Requires cards to be synced first (prices join on the stored printing UUID).
    Runs in a background thread; poll ``GET /settings/sync-mtgjson/status``.
    """
    return mtgjson_service.start_sync_job("prices")


@router.get("/api/v1/settings/sync-mtgjson/status")
def get_sync_mtgjson_status(_: str = Depends(require_admin)):
    """Return the MTGJSON sync job status (which job is running + per-job state). Admin-only."""
    return mtgjson_service.get_sync_status()


@router.post("/api/v1/settings/clear-decks", dependencies=[Depends(require_database)])
def post_clear_decks(_: str = Depends(require_admin)):
    """Clear all decks in the database. Admin-only. Requires PostgreSQL."""
    state.decks = []
    _invalidate_metagame()
    _clear_decks_in_db()
    return {"message": "Decks cleared"}


@router.get("/api/v1/settings/upload-links")
def get_settings_upload_links(_: str = Depends(require_admin), __: None = Depends(require_database)):
    """List all one-time upload links (admin-only). Requires database."""
    with _db.session_scope() as session:
        links = _db.get_all_upload_links(session)
    return {"links": links}


@router.delete("/api/v1/settings/upload-links")
def delete_settings_upload_links(
    used_only: bool = Query(False, description="If true, only delete links that have been used"),
    _: str = Depends(require_admin),
    __: None = Depends(require_database),
):
    """Clear one-time upload links (admin-only). used_only=true clears only used links. Requires database."""
    with _db.session_scope() as session:
        deleted = _db.delete_all_upload_links(session, used_only=used_only)
    return {"deleted": deleted, "message": f"Cleared {deleted} link(s)"}
