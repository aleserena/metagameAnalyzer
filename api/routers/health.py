from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/health", tags=["Health"])
def health():
    """Health check for load balancers and monitoring."""
    return {"status": "ok"}

