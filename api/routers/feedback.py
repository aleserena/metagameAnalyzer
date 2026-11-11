import logging
import os

import requests
from fastapi import HTTPException, Request

from api.schemas.auth_feedback import SiteFeedbackBody
from api.services.alerts import send_alert_email
from api.services.captcha import issue_captcha, verify_captcha
from api.services.rate_limit import RateLimiter, client_ip

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

# 5 accepted feedback submissions per client IP per hour.
FEEDBACK_LIMITER = RateLimiter(5, 3600)


@router.get("/api/v1/feedback/captcha")
def get_feedback_captcha():
    """Issue a signed, single-use math captcha for the feedback form."""
    return issue_captcha()


@router.post("/api/v1/feedback")
def post_feedback(body: SiteFeedbackBody, request: Request):
    """Create a GitHub issue from feedback form. Requires GITHUB_TOKEN and GITHUB_REPO."""
    # Honeypot: if filled, treat as bot and return fake success (do not create issue)
    if (body.website or "").strip():
        return {"url": "", "number": None}
    ip = client_ip(request)
    if not FEEDBACK_LIMITER.allow(ip):
        raise HTTPException(
            status_code=429,
            detail="Too many submissions. Try again later.",
            headers={"Retry-After": str(FEEDBACK_LIMITER.retry_after(ip))},
        )
    if (
        not body.captcha_token
        or body.captcha_answer is None
        or not verify_captcha(body.captcha_token, body.captcha_answer)
    ):
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
    issue_body = description  # the contact address is never put in the public issue
    FEEDBACK_LIMITER.record(ip)
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
        issue_url = data.get("html_url", "")
        number = data.get("number")
        if email:
            try:
                send_alert_email(f"Feedback contact for issue #{number}", f"{email}\n{issue_url}")
            except Exception:
                logger.warning("Could not forward feedback contact address")
        return {"url": issue_url, "number": number}
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
