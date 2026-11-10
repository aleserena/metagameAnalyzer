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
