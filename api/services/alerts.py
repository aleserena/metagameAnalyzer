"""Database health status and operator alerts.

A deployment that has DATABASE_URL set but cannot use the database keeps serving
(empty) pages in JSON fallback mode, which is easy to miss — e.g. SQLAlchemy 2.1
switching the default Postgres driver to one that wasn't installed. On startup we
check the database and, when it is unusable, log an error and notify the operator
by GitHub issue (GITHUB_TOKEN/GITHUB_REPO) and email (ALERT_EMAIL, via Brevo).
The status is also exposed to /api/v1/health (503) and /api/v1/info (admin banner).

Beyond the DB check, the operator is emailed (ALERT_EMAIL) for every ERROR log record
(batched/deduplicated by :class:`api.logging_config.ErrorEmailHandler`), for each new
Railway deployment, and when the same deployment restarts (usually after a crash).

Alerts are sent only on Railway (RAILWAY_ENVIRONMENT_NAME set) unless ALERTS_ENABLED=1;
ALERTS_ENABLED=0 disables them everywhere.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

import requests
from api import email as _email
from api.config import DATA_DIR
from api.logging_config import ErrorEmailHandler, build_id, environment_name

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NOT_CONFIGURED = "not_configured"

_STATUS_TTL_SECONDS = 60
_status_cache: tuple[float, dict] | None = None
_status_lock = threading.Lock()


def _database_url_set() -> bool:
    return bool((os.getenv("DATABASE_URL") or "").strip())


def check_database() -> dict:
    """Live DB check: ``{"status": ok|unavailable|not_configured, "error": str|None}``.

    ``not_configured`` (no DATABASE_URL) is the intentional local JSON mode, not a failure.
    """
    # Imported lazily: api.state loads decks at import, and the error-email handler must be
    # installed (see install_error_email_handler) before that so its failures are emailed.
    from api import state as _state_module

    if not _database_url_set():
        result = {"status": STATUS_NOT_CONFIGURED, "error": None}
    elif _state_module._db is None:
        result = {"status": STATUS_UNAVAILABLE, "error": _state_module.db_import_error or "api.db not importable"}
    else:
        error = _state_module._db.ping_database()
        result = {"status": STATUS_UNAVAILABLE if error else STATUS_OK, "error": error}
    global _status_cache
    with _status_lock:
        _status_cache = (time.monotonic(), result)
    return result


def get_database_status() -> dict:
    """Like :func:`check_database`, but reuses a result younger than a minute (for /info)."""
    with _status_lock:
        cached = _status_cache
    if cached is not None and time.monotonic() - cached[0] < _STATUS_TTL_SECONDS:
        return cached[1]
    return check_database()


def alerts_enabled() -> bool:
    flag = os.getenv("ALERTS_ENABLED", "").strip().lower()
    if flag in ("0", "false", "no"):
        return False
    if flag in ("1", "true", "yes"):
        return True
    return bool(os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip())


def _alert_recipients() -> list[str]:
    return [a.strip() for a in os.getenv("ALERT_EMAIL", "").split(",") if a.strip()]


def email_alerts_configured() -> bool:
    """Alerts enabled, ALERT_EMAIL set and Brevo/SMTP configured."""
    return alerts_enabled() and bool(_alert_recipients()) and _email.is_email_configured()


def _create_github_issue(title: str, body: str) -> None:
    """Open an issue labelled ``alert``, unless an open one with the same title exists."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repo = os.getenv("GITHUB_REPO", "").strip()
    if not token or not repo:
        logger.info("GitHub alert skipped (GITHUB_TOKEN/GITHUB_REPO not set)")
        return
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"https://api.github.com/repos/{repo}/issues"
    r = requests.get(base, params={"labels": "alert", "state": "open", "per_page": 100}, headers=headers, timeout=15)
    r.raise_for_status()
    existing = next((i for i in r.json() if i.get("title") == title), None)
    if existing is not None:
        # Same problem still open: comment so repeated restarts are visible without new issues.
        requests.post(
            f"{base}/{existing['number']}/comments", json={"body": body}, headers=headers, timeout=15
        ).raise_for_status()
        logger.info("Commented on existing alert issue #%s", existing["number"])
        return
    r = requests.post(base, json={"title": title, "body": body, "labels": ["alert"]}, headers=headers, timeout=15)
    r.raise_for_status()
    logger.info("Opened alert issue %s", r.json().get("html_url", ""))


def send_alert_email(subject: str, body: str) -> None:
    """Email every ALERT_EMAIL recipient. Raises on send failure; no-op when unconfigured."""
    recipients = _alert_recipients()
    if not recipients:
        logger.info("Email alert skipped (ALERT_EMAIL not set)")
        return
    if not _email.is_email_configured():
        logger.info("Email alert skipped (email sending not configured)")
        return
    for addr in recipients:
        _email.send_email(addr, subject, body)



def notify(title: str, body: str) -> None:
    """Send an operator alert through every configured channel. Never raises."""
    for channel, send in (("GitHub", _create_github_issue), ("email", send_alert_email)):
        try:
            send(title, body)
        except Exception as e:
            # A failed email is not itself emailed (it would fail the same way).
            logger.error(
                "Failed to send %s alert: %s", channel, e,
                extra={"event": "alert_failed", "email": channel != "email"},
            )


def _send_in_background(name: str, subject: str, body: str) -> None:
    def run():
        try:
            send_alert_email(subject, body)
        except Exception as e:
            logger.warning("Failed to send %s email: %s", name, e, extra={"event": "alert_failed", "email": False})

    threading.Thread(target=run, name=f"{name}-email", daemon=True).start()


# ---- error emails -------------------------------------------------------------------------

_error_handler: ErrorEmailHandler | None = None


def _env_number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def install_error_email_handler() -> ErrorEmailHandler | None:
    """Attach the ERROR email handler to the root logger once, when email alerts are configured."""
    global _error_handler
    if _error_handler is not None:
        return _error_handler
    if not email_alerts_configured():
        logger.info("Error emails disabled (need ALERT_EMAIL, Brevo/SMTP settings and alerts enabled)")
        return None
    _error_handler = ErrorEmailHandler(
        send_alert_email,
        batch_seconds=_env_number("ALERT_EMAIL_BATCH_SECONDS", 30),
        cooldown_seconds=_env_number("ALERT_EMAIL_COOLDOWN_SECONDS", 900),
        max_per_hour=int(_env_number("ALERT_EMAIL_MAX_PER_HOUR", 20)),
        # The email path's own failures must not trigger more emails.
        skip_loggers=("api.alerts.email", "api.email"),
    )
    logging.getLogger().addHandler(_error_handler)
    logger.info("Error emails enabled for %d recipient(s)", len(_alert_recipients()))
    return _error_handler


def shutdown_alerts() -> None:
    """Flush queued error emails before the process exits (called on app shutdown)."""
    global _error_handler
    if _error_handler is not None:
        logging.getLogger().removeHandler(_error_handler)
        _error_handler.flush_and_stop()
        _error_handler = None


# ---- deployment emails --------------------------------------------------------------------

_DEPLOY_MARKER = ".last_deployment_notified"


def _read_marker(path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def notify_deployment(db_status: dict | None = None, deck_count: int | None = None) -> str | None:
    """Email "deployed" for a new Railway deployment, or "restarted" when the same one starts again.

    The last notified deployment id lives in DATA_DIR (the persistent /data volume on Railway),
    so it works even when the database is down. Returns "deployed", "restarted" or None.
    """
    deployment_id = os.getenv("RAILWAY_DEPLOYMENT_ID", "").strip()
    if not deployment_id or not alerts_enabled():
        return None
    marker = DATA_DIR / _DEPLOY_MARKER
    kind = "restarted" if _read_marker(marker) == deployment_id else "deployed"
    try:
        marker.write_text(deployment_id, encoding="utf-8")
    except OSError as e:
        logger.warning("Could not record deployment id in %s: %s", marker, e)

    env, build = environment_name(), build_id()
    status = (db_status or {}).get("status", "unknown")
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    commit_message = (os.getenv("RAILWAY_GIT_COMMIT_MESSAGE") or "").strip()
    if kind == "deployed":
        summary = commit_message.splitlines()[0][:100] if commit_message else "new deployment"
        subject = f"[{env}] Deployed {build}: {summary}"
        intro = "A new deployment has started."
    else:
        subject = f"[{env}] Restarted {build} (same deployment)"
        intro = (
            "The service started again without a new deployment — usually a crash or an "
            "out-of-memory restart. Check the logs just before this time."
        )
    lines = [
        intro,
        "",
        f"Environment: {env}",
        f"Build: {build}",
        f"Branch: {os.getenv('RAILWAY_GIT_BRANCH') or '-'}",
        f"Author: {os.getenv('RAILWAY_GIT_AUTHOR') or '-'}",
        f"Commit message: {commit_message or '-'}",
        f"Deployment: {deployment_id}",
        f"Time: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Database: {status}" + (f" ({(db_status or {}).get('error')})" if status == STATUS_UNAVAILABLE else ""),
    ]
    if deck_count is not None:
        lines.append(f"Decks loaded: {deck_count}")
    if domain:
        lines.append(f"Site: https://{domain}")
    logger.info("Deployment %s (%s)", kind, deployment_id, extra={"event": f"deployment_{kind}"})
    _send_in_background("deploy", subject, "\n".join(lines))
    return kind


# ---- database startup check ---------------------------------------------------------------


def check_database_on_startup() -> dict:
    """Check the DB at startup; log and (in background) alert when it is configured but unusable."""
    result = check_database()
    if result["status"] != STATUS_UNAVAILABLE:
        if result["status"] == STATUS_NOT_CONFIGURED:
            logger.info("DATABASE_URL not set: running in JSON fallback mode")
        return result
    env = environment_name()
    logger.error(
        "Database unavailable in %s: %s. The site is serving without a database.",
        env,
        result["error"],
        # notify() below sends a dedicated alert email, so skip the generic error email.
        extra={"event": "db_unavailable", "email": False},
    )
    if alerts_enabled():
        title = f"[{env}] Database unavailable"
        body = (
            f"The API started with `DATABASE_URL` set but cannot use the database, so it is "
            f"running in JSON fallback mode (no data).\n\n"
            f"- **Environment:** {env}\n"
            f"- **Build:** {build_id()}\n"
            f"- **Time:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
            f"- **Error:** `{result['error']}`\n\n"
            f"Check the deploy logs (`event=db_unavailable`) and `GET /api/v1/health`."
        )
        threading.Thread(target=notify, args=(title, body), name="db-alert", daemon=True).start()
    return result
