"""DB availability detection, health status and operator alerts (api/services/alerts.py)."""

import pytest
from fastapi.testclient import TestClient

from api import db as _db
from api.main import app
from api.services import alerts


@pytest.fixture
def fresh_engine(monkeypatch):
    """Reset the cached engine so _get_engine re-reads DATABASE_URL; restore it afterwards."""
    saved = (_db._engine, _db._engine_tried, _db._engine_error)
    monkeypatch.setattr(_db, "_engine", None)
    monkeypatch.setattr(_db, "_engine_tried", False)
    monkeypatch.setattr(_db, "_engine_error", None)
    yield
    _db._engine, _db._engine_tried, _db._engine_error = saved


@pytest.fixture(autouse=True)
def _clear_status_cache(monkeypatch):
    monkeypatch.setattr(alerts, "_status_cache", None)


def test_engine_pins_psycopg2_driver(fresh_engine, monkeypatch):
    """A bare postgres URL must use psycopg2 (SQLAlchemy 2.1 defaults to the uninstalled psycopg)."""
    for url in ("postgresql://u:p@h:5432/db", "postgres://u:p@h:5432/db"):
        monkeypatch.setattr(_db, "_engine_tried", False)
        monkeypatch.setenv("DATABASE_URL", url)
        engine = _db.get_engine()
        assert engine is not None
        assert engine.dialect.driver == "psycopg2"


def test_non_postgres_url_records_error(fresh_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "localhost:5432")
    assert _db.get_engine() is None
    assert "not a PostgreSQL URL" in _db.get_engine_error()


def test_redact_db_url_masks_password():
    msg = "could not connect: postgresql+psycopg2://admin:sup3rs3cret@db.example:5432/railway"
    redacted = _db.redact_db_url(msg)
    assert "sup3rs3cret" not in redacted
    assert "admin:***@db.example" in redacted


def test_check_database_not_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert alerts.check_database() == {"status": "not_configured", "error": None}


def test_check_database_unavailable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setattr(_db, "ping_database", lambda: "Database unreachable: boom")
    assert alerts.check_database() == {"status": "unavailable", "error": "Database unreachable: boom"}


def test_health_returns_503_when_db_unavailable(monkeypatch):
    monkeypatch.setattr(alerts, "check_database", lambda: {"status": "unavailable", "error": "secret detail"})
    monkeypatch.setattr("api.routers.health.check_database", alerts.check_database)
    r = TestClient(app).get("/api/v1/health")
    assert r.status_code == 503
    assert r.json() == {"status": "error", "database": "unavailable"}
    assert "secret detail" not in r.text


def test_info_reports_db_status(monkeypatch):
    monkeypatch.setattr("api.main.get_database_status", lambda: {"status": "unavailable", "error": "x"})
    r = TestClient(app).get("/api/v1/info")
    assert r.json()["db_status"] == "unavailable"
    assert "error" not in r.json()


def test_startup_alerts_when_db_unavailable(monkeypatch):
    monkeypatch.setattr(alerts, "check_database", lambda: {"status": "unavailable", "error": "No module named 'psycopg'"})
    monkeypatch.setenv("ALERTS_ENABLED", "1")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    sent = []
    monkeypatch.setattr(alerts, "notify", lambda title, body: sent.append((title, body)))

    class _SyncThread:
        def __init__(self, target, args, **_kw):
            self._run = lambda: target(*args)

        def start(self):
            self._run()

    monkeypatch.setattr(alerts.threading, "Thread", _SyncThread)
    alerts.check_database_on_startup()
    assert len(sent) == 1
    title, body = sent[0]
    assert title == "[production] Database unavailable"
    assert "No module named 'psycopg'" in body


def test_startup_no_alert_when_disabled_or_healthy(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "notify", lambda *a: sent.append(a))
    monkeypatch.setattr(alerts, "check_database", lambda: {"status": "unavailable", "error": "x"})
    monkeypatch.setenv("ALERTS_ENABLED", "0")
    alerts.check_database_on_startup()
    monkeypatch.setenv("ALERTS_ENABLED", "1")
    monkeypatch.setattr(alerts, "check_database", lambda: {"status": "ok", "error": None})
    alerts.check_database_on_startup()
    assert sent == []


def test_alerts_enabled_defaults_to_railway_only(monkeypatch):
    monkeypatch.delenv("ALERTS_ENABLED", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    assert alerts.alerts_enabled() is False
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    assert alerts.alerts_enabled() is True


class _Resp:
    def __init__(self, data=None):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_github_alert_comments_on_existing_open_issue(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPO", "o/r")
    posts = []
    monkeypatch.setattr(alerts.requests, "get", lambda *a, **k: _Resp([{"title": "T", "number": 7}]))
    monkeypatch.setattr(alerts.requests, "post", lambda url, **k: posts.append(url) or _Resp({}))
    alerts._create_github_issue("T", "body")
    assert posts == ["https://api.github.com/repos/o/r/issues/7/comments"]


def test_github_alert_opens_new_issue(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPO", "o/r")
    posts = []
    monkeypatch.setattr(alerts.requests, "get", lambda *a, **k: _Resp([{"title": "other", "number": 1}]))
    monkeypatch.setattr(alerts.requests, "post", lambda url, **k: posts.append((url, k["json"])) or _Resp({}))
    alerts._create_github_issue("T", "body")
    assert posts == [("https://api.github.com/repos/o/r/issues", {"title": "T", "body": "body", "labels": ["alert"]})]


def test_email_alert_sends_to_each_recipient(monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL", "a@x.com, b@x.com")
    monkeypatch.setattr(alerts._email, "is_email_configured", lambda: True)
    sent = []
    monkeypatch.setattr(alerts._email, "send_email", lambda to, subject, body: sent.append(to))
    alerts.send_alert_email("s", "b")
    assert sent == ["a@x.com", "b@x.com"]


def test_notify_never_raises(monkeypatch):
    def boom(*_a):
        raise RuntimeError("down")

    monkeypatch.setattr(alerts, "_create_github_issue", boom)
    monkeypatch.setattr(alerts, "send_alert_email", boom)
    alerts.notify("t", "b")
