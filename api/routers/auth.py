import hmac
import logging

from fastapi import Header, HTTPException, Request

from api.dependencies import (
    ADMIN_PASSWORD,
    _create_admin_token,
    _verify_admin_token,
)
from api.schemas.auth_feedback import LoginBody
from api.services.rate_limit import RateLimiter, client_ip

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()

# 5 failed admin logins per client IP per 15 minutes.
LOGIN_LIMITER = RateLimiter(5, 15 * 60)


@router.post("/api/v1/auth/login")
def auth_login(body: LoginBody, request: Request):
    """Login as admin. Returns JWT if password matches ADMIN_PASSWORD."""
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Admin login disabled (ADMIN_PASSWORD not set)")
    ip = client_ip(request)
    if not LOGIN_LIMITER.allow(ip):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(LOGIN_LIMITER.retry_after(ip))},
        )
    if not hmac.compare_digest(body.password.encode(), ADMIN_PASSWORD.encode()):
        LOGIN_LIMITER.record(ip)
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"token": _create_admin_token(), "user": "admin"}


@router.get("/api/v1/auth/me")
def auth_me(authorization: str | None = Header(None, alias="Authorization")):
    """Return current user if valid Bearer token, else 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if not _verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"user": "admin"}
