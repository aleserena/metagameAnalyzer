"""FastAPI auth/DB dependencies and JWT helpers.

Depends on api.state for the in-memory deck lookup and DB-availability check.
"""

import hashlib
import os
import secrets
import time

import jwt
from fastapi import Header, HTTPException

from api.config import is_deployed, validate_auth_config  # noqa: F401  (re-exported)
from api.state import _database_available, _get_deck_by_id

try:
    from api import db as _db
except ImportError:
    _db = None

def derive_jwt_key(jwt_secret: str, admin_password: str) -> bytes:
    """Signing key: JWT_SECRET (SHA-256 if < 32 bytes), else from the admin password, else random per process."""
    secret = jwt_secret or admin_password
    if not secret:
        return secrets.token_bytes(32)
    raw = secret.encode("utf-8")
    # PyJWT recommends at least 32 bytes for HS256; derive a 32-byte key if shorter
    return raw if len(raw) >= 32 else hashlib.sha256(raw).digest()


# Admin auth: single user, password from env, JWT for session
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
_JWT_KEY = derive_jwt_key(JWT_SECRET, ADMIN_PASSWORD)
JWT_ALGORITHM = "HS256"
JWT_EXP_SECONDS = 12 * 3600  # 12 hours: one admin sitting (see docs/SECURITY_OPERATIONS.md)


def _create_admin_token() -> str:
    return jwt.encode(
        {"sub": "admin", "exp": int(time.time()) + JWT_EXP_SECONDS},
        _JWT_KEY,
        algorithm=JWT_ALGORITHM,
    )


def _verify_admin_token(token: str) -> bool:
    if not ADMIN_PASSWORD:
        return False
    try:
        payload = jwt.decode(token, _JWT_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("sub") == "admin"
    except jwt.PyJWTError:
        return False


def require_admin(authorization: str | None = Header(None, alias="Authorization")):
    """Dependency: require valid admin Bearer token or raise 401."""
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Admin login disabled (ADMIN_PASSWORD not set)")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if not _verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return "admin"


def optional_admin(authorization: str | None = Header(None, alias="Authorization")):
    """Dependency: return 'admin' if valid admin token, else None. Does not raise."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if _verify_admin_token(token):
        return "admin"
    return None


def require_admin_or_event_edit(
    event_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    x_event_edit_token: str | None = Header(None, alias="X-Event-Edit-Token"),
):
    """Dependency: require admin Bearer token OR valid one-time event-edit token for this event."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if _verify_admin_token(token):
            return "admin"
    if x_event_edit_token and _db and _db.is_database_available():
        with _db.session_scope() as session:
            row = _db.get_upload_link(session, x_event_edit_token.strip())
            if row and getattr(row, "link_type", None) == _db.LINK_TYPE_EVENT_EDIT and row.event_id == _db._event_id_str(event_id):
                if row.expires_at is not None and row.expires_at < _db.utcnow_naive():
                    raise HTTPException(status_code=401, detail="Event edit link expired")
                return "event_edit"
    raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_admin_or_event_edit_deck(
    deck_id: int,
    authorization: str | None = Header(None, alias="Authorization"),
    x_event_edit_token: str | None = Header(None, alias="X-Event-Edit-Token"),
):
    """Dependency: require admin OR valid event-edit token for the event that owns this deck."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if _verify_admin_token(token):
            return "admin"
    deck = _get_deck_by_id(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    event_id = str(deck.get("event_id", ""))
    if x_event_edit_token and _db and _db.is_database_available():
        with _db.session_scope() as session:
            row = _db.get_upload_link(session, x_event_edit_token.strip())
            if row and getattr(row, "link_type", None) == _db.LINK_TYPE_EVENT_EDIT and row.event_id == _db._event_id_str(event_id):
                if row.expires_at is not None and row.expires_at < _db.utcnow_naive():
                    raise HTTPException(status_code=401, detail="Event edit link expired")
                return "event_edit"
    raise HTTPException(status_code=401, detail="Invalid or expired token")


def current_actor(
    authorization: str | None = Header(None, alias="Authorization"),
    x_event_edit_token: str | None = Header(None, alias="X-Event-Edit-Token"),
) -> str:
    """Dependency: who is making this change, for the change log.

    ``admin`` for a valid admin token, else the event-edit link named by its type and label
    (never its token). Does not authorise anything; pair it with a ``require_*`` dependency.
    """
    from api.services import change_log

    if authorization and authorization.startswith("Bearer ") and _verify_admin_token(authorization[7:].strip()):
        return change_log.ADMIN
    return change_log.actor_for_token(x_event_edit_token)


def require_database():
    """Dependency: require database available or raise 503."""
    if not _database_available():
        raise HTTPException(status_code=503, detail="Database not configured")
