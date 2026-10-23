"""Logging robustness (api/logging_config.py), error emails and deployment emails."""

import json
import logging
import threading
import time

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from api import logging_config as lc
from api.main import app
from api.services import alerts


def _record(msg="boom %s", args=("x",), name="api.test", exc_info=None, **extra):
    rec = logging.getLogger(name).makeRecord(name, logging.ERROR, __file__, 1, msg, args, exc_info, extra=extra)
    return rec


# ---- redaction / formatting -----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, secret",
    [
        ("postgresql+psycopg2://admin:sup3rs3cret@db:5432/x", "sup3rs3cret"),
        ("Authorization: Bearer eyJhbGciOi.abc.def", "eyJhbGciOi.abc.def"),
        ("login failed password=hunter2 for admin", "hunter2"),
        ('{"api_key": "xkeysib-123"}', "xkeysib-123"),
    ],
)
def test_redact_secrets(raw, secret):
    assert secret not in lc.redact_secrets(raw)


def test_json_formatter_redacts_and_includes_context():
    try:
        raise ValueError("postgresql://u:topsecret@h/db")
    except ValueError:
        import sys

        rec = _record("connect failed: %s", ("postgresql://u:topsecret@h/db",), exc_info=sys.exc_info())
    out = json.loads(lc.JsonFormatter().format(rec))
    assert "topsecret" not in out["message"]
    assert "topsecret" not in out["exception"]
    assert out["source"].startswith("test_logging_alerts:")


def test_json_formatter_survives_bad_args():
    rec = _record("needs two %s %s", ("only-one",))
    out = json.loads(lc.JsonFormatter().format(rec))
    assert "needs two" in out["message"]


def test_record_factory_adds_request_id_env_build():
    lc.configure_logging()
    token = lc.request_id_var.set("req-123")
    try:
        rec = logging.getLogger("api.test").makeRecord("api.test", logging.INFO, __file__, 1, "m", (), None)
    finally:
        lc.request_id_var.reset(token)
    assert rec.request_id == "req-123"
    assert rec.env and rec.build


def test_thread_excepthook_logs_uncaught(caplog):
    lc.configure_logging()
    caplog.set_level(logging.ERROR, logger="uncaught")
    logging.getLogger("uncaught").addHandler(caplog.handler)
    try:
        t = threading.Thread(target=lambda: 1 / 0, name="boom-thread")
        t.start()
        t.join()
    finally:
        logging.getLogger("uncaught").removeHandler(caplog.handler)
    assert any("boom-thread" in r.getMessage() and r.levelno == logging.CRITICAL for r in caplog.records)


# ---- request id / unhandled errors ----------------------------------------------------------

_boom_router = APIRouter()


@_boom_router.get("/api/v1/__test_boom")
def _boom():
    raise RuntimeError("kaboom")


app.include_router(_boom_router)


def test_request_id_header_generated_and_propagated():
    c = TestClient(app)
    r = c.get("/api/v1/health")
    assert len(r.headers["X-Request-ID"]) == 16
    r = c.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"
    r = c.get("/api/v1/health", headers={"X-Request-ID": "bad id with spaces"})
    assert r.headers["X-Request-ID"] != "bad id with spaces"


def test_unhandled_exception_logs_with_request_id(caplog):
    caplog.set_level(logging.ERROR)
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/v1/__test_boom", headers={"X-Request-ID": "trace-me"})
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error", "request_id": "trace-me"}
    errs = [rec for rec in caplog.records if getattr(rec, "event", None) == "unhandled_exception"]
    assert errs and errs[0].request_id == "trace-me" and errs[0].exc_info


# ---- ErrorEmailHandler ----------------------------------------------------------------------


def _handler(sent, **kw):
    kw.setdefault("batch_seconds", 0.05)
    return lc.ErrorEmailHandler(lambda s, b: sent.append((s, b)), **kw)


def _wait_for(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return pred()


def test_error_email_batches_records_into_one_email():
    sent = []
    h = _handler(sent, batch_seconds=0.3)
    h.emit(_record("first %s", ("a",)))
    h.emit(_record("second %s", ("b",)))
    assert _wait_for(lambda: sent)
    h.flush_and_stop()
    assert len(sent) == 1
    subject, body = sent[0]
    assert "(+1 more)" in subject and "first a" in body and "second b" in body


def test_error_email_cooldown_dedupes_and_counts_repeats():
    sent = []
    h = _handler(sent, cooldown_seconds=0.4)
    h.emit(_record("db down %s", ("1",)))
    assert _wait_for(lambda: len(sent) == 1)
    for i in range(3):
        h.emit(_record("db down %s", (str(i),)))  # same template -> same fingerprint
    time.sleep(0.2)
    assert len(sent) == 1
    time.sleep(0.4)
    h.emit(_record("db down %s", ("again",)))
    assert _wait_for(lambda: len(sent) == 2)
    h.flush_and_stop()
    assert "Repeated 3 more time(s)" in sent[1][1]


def test_error_email_hourly_cap():
    sent = []
    h = _handler(sent, max_per_hour=2)
    for i in range(4):
        h.emit(_record(f"distinct error {i}", ()))
        time.sleep(0.12)
    h.flush_and_stop()
    assert len(sent) == 2


def test_error_email_skips_opt_out_and_email_loggers():
    sent = []
    h = _handler(sent, skip_loggers=("api.email",))
    h.emit(_record("quiet", (), email=False))
    h.emit(_record("smtp broke", (), name="api.email"))
    h.flush_and_stop()
    assert sent == []


def test_error_email_send_failure_does_not_raise_or_loop(caplog):
    calls = []

    def bad_send(s, b):
        calls.append(s)
        raise OSError("smtp down")

    h = lc.ErrorEmailHandler(bad_send, batch_seconds=0.05, skip_loggers=("api.alerts.email",))
    logging.getLogger().addHandler(h)
    try:
        logging.getLogger("api.test").error("trigger")
        assert _wait_for(lambda: calls)
        time.sleep(0.2)
    finally:
        logging.getLogger().removeHandler(h)
        h.flush_and_stop()
    assert len(calls) == 1


def test_error_email_includes_traceback_redacted():
    sent = []
    h = _handler(sent)
    try:
        raise RuntimeError("postgresql://u:pw123@h/db")
    except RuntimeError:
        import sys

        h.emit(_record("failed", (), exc_info=sys.exc_info()))
    h.flush_and_stop()
    body = sent[0][1]
    assert "RuntimeError" in body and "pw123" not in body


def test_install_error_email_handler_requires_config(monkeypatch):
    monkeypatch.setattr(alerts, "_error_handler", None)
    monkeypatch.setattr(alerts, "email_alerts_configured", lambda: False)
    assert alerts.install_error_email_handler() is None


# ---- deployment emails ----------------------------------------------------------------------


@pytest.fixture
def deploy_env(monkeypatch, tmp_path):
    monkeypatch.setattr(alerts, "DATA_DIR", tmp_path)
    monkeypatch.setenv("ALERTS_ENABLED", "1")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abcdef1234567")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_MESSAGE", "Fix the thing\n\nlong body")
    sent = []
    monkeypatch.setattr(alerts, "_send_in_background", lambda name, s, b: sent.append((s, b)))
    return sent


def test_notify_deployment_new_then_restart(deploy_env, monkeypatch):
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "dep-1")
    assert alerts.notify_deployment({"status": "ok", "error": None}, deck_count=42) == "deployed"
    subject, body = deploy_env[0]
    assert subject == "[production] Deployed abcdef1: Fix the thing"
    assert "Database: ok" in body and "Decks loaded: 42" in body

    assert alerts.notify_deployment({"status": "ok"}) == "restarted"
    assert "Restarted" in deploy_env[1][0]

    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "dep-2")
    assert alerts.notify_deployment({"status": "unavailable", "error": "no psycopg"}) == "deployed"
    assert "Database: unavailable (no psycopg)" in deploy_env[2][1]


def test_notify_deployment_skipped_off_railway(deploy_env, monkeypatch):
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    assert alerts.notify_deployment({"status": "ok"}) is None
    assert deploy_env == []
