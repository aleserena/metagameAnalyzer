import pytest

from tests._dbguard import UnsafeTestDatabase, resolve_test_database_url

TEST_URL = "postgresql://postgres:test@localhost:55432/mtg_test"


def test_uses_environ_value():
    assert resolve_test_database_url({"TEST_DATABASE_URL": TEST_URL}, {}) == TEST_URL


def test_reads_base_dotenv_when_environ_has_none():
    files = {".env": {"TEST_DATABASE_URL": TEST_URL}}
    assert resolve_test_database_url({}, files) == TEST_URL


def test_empty_when_only_database_url_is_set():
    environ = {"DATABASE_URL": "postgresql://u:p@h:5432/app"}
    assert resolve_test_database_url(environ, {}) == ""


@pytest.mark.parametrize("env_file", [".env.staging", ".env.prod"])
def test_refuses_same_host_port_and_name_as_staging_or_prod(env_file):
    files = {env_file: {"DATABASE_URL": "postgresql://real:secret@db.host:5432/railway"}}
    environ = {"TEST_DATABASE_URL": "postgres://other:creds@db.host:5432/railway"}
    with pytest.raises(UnsafeTestDatabase):
        resolve_test_database_url(environ, files)


def test_ensure_test_schema_returns_false_when_unreachable():
    from tests._dbguard import ensure_test_schema

    def migrate():
        raise AssertionError("must not migrate an unreachable database")

    url = "postgresql://postgres@127.0.0.1:1/none"
    assert ensure_test_schema(url, migrate=migrate) is False


def test_ensure_test_schema_propagates_migration_failure_on_reachable_db(monkeypatch):
    import psycopg2

    from tests import _dbguard

    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(psycopg2, "connect", lambda *a, **k: _Conn())

    def migrate():
        raise RuntimeError("broken migration")

    with pytest.raises(RuntimeError, match="broken migration"):
        _dbguard.ensure_test_schema(TEST_URL, migrate=migrate)


def test_ensure_test_schema_empty_url_is_noop():
    from tests._dbguard import ensure_test_schema

    assert ensure_test_schema("") is False
