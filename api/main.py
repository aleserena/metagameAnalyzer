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
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

import api.config  # noqa: F401  (importing loads .env before configure_logging / state read env)
from api.logging_config import build_id, configure_logging, environment_name, request_id_var

configure_logging()
logger = logging.getLogger(__name__)

# Before importing api.state (which loads decks at import) so those errors are emailed too.
from api.services.alerts import (
    check_database_on_startup,
    email_alerts_configured,
    get_database_status,
    install_error_email_handler,
    notify_deployment,
    shutdown_alerts,
)

install_error_email_handler()

from api.routers import router as api_router
from api.state import (
    log_split_player_identities,
    state,
)

try:
    from api import db as _db
except ImportError:
    _db = None

_project_root = Path(__file__).resolve().parent.parent  # used by the static-file mount below


@asynccontextmanager
async def lifespan(_app):
    """Log startup and shutdown for monitoring (e.g. Railway); send deploy/restart and DB alerts."""
    logger.info(
        "Application startup: env=%s build=%s",
        environment_name(),
        build_id(),
        extra={
            "event": "startup",
            "deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID") or None,
            "replica_id": os.getenv("RAILWAY_REPLICA_ID") or None,
            "decks_loaded": len(state.decks),
            "error_emails": email_alerts_configured(),
            "log_level": logging.getLevelName(logging.getLogger().level),
        },
    )
    db_status = check_database_on_startup()
    notify_deployment(db_status, deck_count=len(state.decks))
    log_split_player_identities()
    yield
    logger.info("Application shutdown", extra={"event": "shutdown"})
    shutdown_alerts()


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


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SLOW_REQUEST_MS = float(os.getenv("SLOW_REQUEST_MS", "5000"))


def _request_id(request: Request) -> str:
    """Reuse a sane incoming X-Request-ID / Railway request id, else generate one."""
    for header in ("x-request-id", "x-railway-request-id"):
        value = request.headers.get(header, "")
        if _REQUEST_ID_RE.match(value):
            return value
    return uuid.uuid4().hex[:16]


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log each request with method, path, status, duration and request id for monitoring.

    The request id is attached to every log line emitted while handling the request and
    returned as ``X-Request-ID`` so a user-reported error can be found in the logs.
    5xx responses and slow requests log at WARNING; unhandled exceptions are logged
    (with traceback, at ERROR) by ``unhandled_exception_handler``.
    """
    rid = _request_id(request)
    request.state.request_id = rid
    token = request_id_var.set(rid)
    start = time.perf_counter()
    status_code = 500
    failed = True
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = rid
        failed = False
        return response
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        level = logging.WARNING if status_code >= 500 or duration_ms >= _SLOW_REQUEST_MS else logging.INFO
        logger.log(
            level,
            "%s %s %s %sms",
            request.method,
            request.url.path,
            status_code,
            duration_ms,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client_ip": request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                or (request.client.host if request.client else None),
            },
        )
        # On an exception keep the id set: unhandled_exception_handler runs outside this
        # middleware (in the same request task) and its log line should carry the id.
        if not failed:
            request_id_var.reset(token)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return generic 500 and log the real error (avoid leaking internals)."""
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        extra={"event": "unhandled_exception", "method": request.method, "path": request.url.path},
    )
    rid = getattr(request.state, "request_id", None) or request_id_var.get()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": rid},
        headers={"X-Request-ID": rid} if rid else None,
    )


def _get_build_id() -> str:
    """Short SHA from Railway or GIT_COMMIT_SHA; 'dev' if unset."""
    return build_id()


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
    """Public endpoint: build identifier (short SHA), DB environment and DB status.

    ``db_status`` (ok | unavailable | not_configured) drives the admin "database
    unavailable" banner; error details stay out of this public response (see /health).
    """
    return {"build_id": _get_build_id(), "db_env": _get_db_env(), "db_status": get_database_status()["status"]}


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
