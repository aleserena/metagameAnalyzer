from fastapi import APIRouter

from .auth import router as auth_router
from .cards import router as cards_router
from .data import router as data_router
from .decks import router as decks_router
from .events import router as events_router
from .feedback import router as feedback_router
from .health import router as health_router
from .matchups import router as matchups_router
from .metagame import router as metagame_router
from .players import router as players_router
from .settings import router as settings_router
from .upload import router as upload_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(cards_router)
router.include_router(data_router)
router.include_router(decks_router)
router.include_router(events_router)
router.include_router(feedback_router)
router.include_router(matchups_router)
router.include_router(metagame_router)
router.include_router(players_router)
router.include_router(settings_router)
router.include_router(upload_router)
