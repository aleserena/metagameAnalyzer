from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.services.alerts import STATUS_UNAVAILABLE, check_database

router = APIRouter()


@router.get("/api/v1/health", tags=["Health"])
def health():
    """Health check for load balancers, monitoring and the Railway deploy healthcheck.

    Returns 503 when DATABASE_URL is set but the database is unusable, so a broken build
    fails its deploy instead of replacing a working one. ``database`` is ok | unavailable |
    not_configured (local JSON mode); error details go to the logs, not this public response.
    """
    db = check_database()
    if db["status"] == STATUS_UNAVAILABLE:
        return JSONResponse(status_code=503, content={"status": "error", "database": db["status"]})
    return {"status": "ok", "database": db["status"]}
