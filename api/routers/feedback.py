import logging
import os

import requests
from fastapi import HTTPException

from api.schemas.auth_feedback import SiteFeedbackBody

try:
    from api import db as _db
except ImportError:
    _db = None
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()


GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()  # e.g. aleserena/metagameAnalyzer


_FEEDBACK_LABELS = {"bug", "enhancement", "question"}


@router.post("/api/v1/feedback")
def post_feedback(body: SiteFeedbackBody):
    """Create a GitHub issue from feedback form. Requires GITHUB_TOKEN and GITHUB_REPO."""
    # Honeypot: if filled, treat as bot and return fake success (do not create issue)
    if (body.website or "").strip():
        return {"url": "", "number": None}
    # Simple math captcha: expect small integers (e.g. 1–20) and answer = a + b
    a, b, ans = body.captcha_a, body.captcha_b, body.captcha_answer
    if a is None or b is None or ans is None or not (1 <= a <= 20 and 1 <= b <= 20) or a + b != ans:
        raise HTTPException(status_code=400, detail="Please solve the simple math question correctly.")
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise HTTPException(
            status_code=503,
            detail="Feedback is not configured (GITHUB_TOKEN and GITHUB_REPO must be set)",
        )
    label = (body.type or "bug").strip().lower()
    if label not in _FEEDBACK_LABELS:
        label = "question"
    title = (body.title or "").strip()
    if not title or len(title) > 256:
        raise HTTPException(status_code=400, detail="Title is required and must be at most 256 characters")
    description = (body.description or "").strip()
    if not description or len(description) > 65536:
        raise HTTPException(status_code=400, detail="Description is required and must be at most 65536 characters")
    email = (body.email or "").strip() or None
    issue_body = description
    if email:
        issue_body += f"\n\n---\n*Contact (optional): {email}*"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"title": title, "body": issue_body, "labels": [label]}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        return {"url": data.get("html_url", ""), "number": data.get("number")}
    except requests.RequestException as e:
        if hasattr(e, "response") and e.response is not None:
            try:
                err = e.response.json()
                msg = err.get("message", err.get("documentation_url", str(e)))
            except Exception:
                msg = str(e)
            logger.warning("GitHub API error creating feedback issue: %s", msg)
            raise HTTPException(status_code=502, detail=f"Could not create issue: {msg}")
        raise HTTPException(status_code=502, detail="Could not create issue. Try again later.")
