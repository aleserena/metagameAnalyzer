"""Test-database safety guard.

DB-backed tests must only ever run against ``TEST_DATABASE_URL``, never against the
staging/prod database that ``.env`` / ``DB_ENV`` would otherwise select.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BASE_ENV = ".env"
_PROTECTED_ENV_FILES = (".env.staging", ".env.prod")


class UnsafeTestDatabase(ValueError):
    """TEST_DATABASE_URL points at the same database as staging or prod."""


def _identity(url: str) -> tuple[str, int, str]:
    parts = urlsplit(url)
    return (parts.hostname or "", parts.port or 5432, parts.path)


def resolve_test_database_url(
    environ: Mapping[str, str],
    dotenv_files: Mapping[str, Mapping[str, str]],
) -> str:
    """Return TEST_DATABASE_URL ("" when unset); refuse it if it matches staging/prod."""
    url = (environ.get("TEST_DATABASE_URL") or "").strip()
    if not url:
        url = (dotenv_files.get(_BASE_ENV, {}).get("TEST_DATABASE_URL") or "").strip()
    if not url:
        return ""
    wanted = _identity(url)
    for name in _PROTECTED_ENV_FILES:
        protected = (dotenv_files.get(name, {}).get("DATABASE_URL") or "").strip()
        if protected and _identity(protected) == wanted:
            raise UnsafeTestDatabase(
                f"TEST_DATABASE_URL points at the same database as DATABASE_URL in {name}; refusing to run tests."
            )
    return url


def apply_test_database_env() -> str:
    """Point DATABASE_URL at the test database (or at nothing) before api.config loads .env."""
    import pytest
    from dotenv import dotenv_values

    files = {}
    for name in (_BASE_ENV, *_PROTECTED_ENV_FILES):
        path = _PROJECT_ROOT / name
        if path.exists():
            files[name] = {k: v for k, v in dotenv_values(path).items() if v is not None}
    try:
        url = resolve_test_database_url(os.environ, files)
    except UnsafeTestDatabase as exc:
        pytest.exit(str(exc), returncode=2)
    # Empty string (not unset) so api.config's load_dotenv cannot fill it from .env.
    os.environ["DATABASE_URL"] = url
    os.environ["DATABASE_URL_LOCKED"] = "1"
    return url


def ensure_test_schema(url: str, migrate=None) -> bool:
    """Run alembic migrations on the test database.

    Returns False (DB tests skip) if the database is unreachable. Migration failures on a
    reachable database propagate. ``migrate`` is injectable for tests.
    """
    if not url:
        return False
    import psycopg2

    try:
        psycopg2.connect(url, connect_timeout=5).close()
    except psycopg2.OperationalError:
        return False
    if migrate is None:
        from api.db import run_migrations as migrate

    migrate()
    return True
