from unittest.mock import MagicMock, patch

from api import email as em


def test_smtp_send_has_a_network_timeout(monkeypatch):
    with patch.object(em.smtplib, "SMTP") as smtp:
        em._send_via_smtp("h", 587, "u", "p", "f@x.com", "t@x.com", "s", "b", None)
    assert smtp.call_args.kwargs["timeout"] == em.EMAIL_TIMEOUT_SECONDS


def test_brevo_api_send_has_a_network_timeout(monkeypatch):
    monkeypatch.setenv("SMTP_FROM", "f@x.com")
    with patch("urllib.request.urlopen", return_value=MagicMock()) as urlopen:
        em._send_via_brevo_api("t@x.com", "s", "b", None, "key")
    assert urlopen.call_args.kwargs["timeout"] == em.EMAIL_TIMEOUT_SECONDS
