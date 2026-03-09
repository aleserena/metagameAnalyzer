"""Email sending via Brevo (SMTP or Transactional API). Admin-only use; no emails in API responses."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def is_email_configured() -> bool:
    """True if either Brevo SMTP or Brevo API is fully configured."""
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    if api_key:
        # Brevo API also requires SMTP_FROM (sender)
        return bool(os.getenv("SMTP_FROM", "").strip())
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    return bool(host and user and password)


def send_email(
    to: str,
    subject: str,
    body_plain: str,
    body_html: str | None = None,
) -> None:
    """Send one email. Uses Brevo API if BREVO_API_KEY set, else Brevo SMTP. Raises on failure."""
    to = (to or "").strip()
    if not to:
        raise ValueError("recipient email required")
    subject = (subject or "").strip()
    body_plain = body_plain or ""
    body_html = body_html or None

    api_key = os.getenv("BREVO_API_KEY", "").strip()
    if api_key:
        _send_via_brevo_api(to=to, subject=subject, body_plain=body_plain, body_html=body_html, api_key=api_key)
        return

    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    from_addr = os.getenv("SMTP_FROM", user or "").strip()
    if not (host and user and password):
        raise RuntimeError("Email not configured: set BREVO_API_KEY or SMTP_HOST, SMTP_USER, SMTP_PASSWORD")

    _send_via_smtp(
        host=host,
        port=port,
        user=user,
        password=password,
        from_addr=from_addr or user,
        to=to,
        subject=subject,
        body_plain=body_plain,
        body_html=body_html,
    )


def _send_via_smtp(
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to: str,
    subject: str,
    body_plain: str,
    body_html: str | None,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(body_plain, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, [to], msg.as_string())
    logger.info("Email sent to %s (subject: %s)", to[:50], subject[:50] if subject else "")


def _send_via_brevo_api(
    to: str,
    subject: str,
    body_plain: str,
    body_html: str | None,
    api_key: str,
) -> None:
    import json as _json
    import urllib.error
    import urllib.request

    from_addr = os.getenv("SMTP_FROM", "").strip()
    if not from_addr:
        raise RuntimeError("SMTP_FROM required when using BREVO_API_KEY")
    payload = {
        "sender": {"email": from_addr, "name": from_addr.split("@")[0]},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body_plain,
        "htmlContent": body_html,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=_json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req):
            # 2xx success
            pass
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        logger.warning("Brevo API error: %s %s", e.code, body[:300])
        raise RuntimeError(f"Brevo API error {e.code}: {body[:200] or e.reason}") from e
    logger.info("Email sent to %s (subject: %s)", to[:50], subject[:50] if subject else "")
