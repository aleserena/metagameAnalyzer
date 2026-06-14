"""FastAPI backend for MTG Metagame web app.

Route handlers live below; shared pieces are split out:
- api.config       — .env loading + DATA_DIR / MAX_UPLOAD_JSON_BYTES
- api.state        — in-memory deck list + caches (the `state` holder) and loaders
- api.helpers      — pure date/rank/sort/filter + card-name normalization helpers
- api.dependencies — auth/DB FastAPI dependencies and JWT helpers
- api.routers/*    — domain routers included on the app
See docs/API_ROUTES.md for the route -> handler index.
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

import api.config  # noqa: F401  (importing loads .env before configure_logging / state read env)
from api.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

from api.routers import router as api_router
from api.state import (
    state,
)

try:
    from api import db as _db
except ImportError:
    _db = None

_project_root = Path(__file__).resolve().parent.parent  # used by the static-file mount below


@asynccontextmanager
async def lifespan(_app):
    """Log startup and shutdown for monitoring (e.g. Railway)."""
    logger.info("Application startup", extra={"event": "startup"})
    yield
    logger.info("Application shutdown", extra={"event": "shutdown"})


app = FastAPI(title="MTG Metagame API", version="1.0.0", lifespan=lifespan)

_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount sub-routers
app.include_router(api_router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log each request with method, path, status, and duration for monitoring."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "%s %s %s %sms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return generic 500 and log the real error (avoid leaking internals)."""
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _get_build_id() -> str:
    """Short SHA from Railway or GIT_COMMIT_SHA; 'dev' if unset."""
    sha = os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT_SHA", "")
    if sha:
        return sha[:7]
    return "dev"


def _get_db_env() -> str:
    """DB environment: DB_ENV if set and valid, else 'postgres' when DB available, else 'json'."""
    if state.database_available():
        env = os.getenv("DB_ENV", "").strip().lower()
        if env in ("dev", "staging", "prod"):
            return env
        return "postgres"
    return "json"


@app.get("/api/v1/info", tags=["Info"])
def get_info():
    """Public endpoint: build identifier (short SHA) and DB environment for footer display."""
    return {"build_id": _get_build_id(), "db_env": _get_db_env()}


# Feedback: create GitHub issue from app (no user GitHub account required)


# --- Admin-only: events and deck management (DB required for create/update/delete) ---


# --- One-time upload links (admin create; public submit) ---


# ---------- Player analysis (dashboard) -------------------------------------


# Cache analysis responses between requests. Key includes a stable signature of
# the current `state.decks` list and rank weights so we invalidate automatically when
# data changes.


# Serve built frontend (production); static dir is populated by Dockerfile
STATIC_DIR = _project_root / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
    _index_path = STATIC_DIR / "index.html"

    @app.get("/", include_in_schema=False)
    def serve_index():
        if _index_path.exists():
            return FileResponse(_index_path)
        raise StarletteHTTPException(status_code=404)

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            raise StarletteHTTPException(status_code=404)
        if _index_path.exists():
            return FileResponse(_index_path)
        raise StarletteHTTPException(status_code=404)
