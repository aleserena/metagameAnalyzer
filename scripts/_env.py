"""Shared environment loading for the maintenance scripts in ``scripts/``.

These scripts mutate real data, so they must be explicit about which database they
are pointed at. ``.env`` sets ``DB_ENV=staging`` by default, which means a script run
without an override silently operates on staging even when the operator meant prod.

Use :func:`load_env` at the start of ``main()`` and print what it returns.
"""

from __future__ import annotations

import os

VALID_DB_ENVS = ("dev", "staging", "prod")


def describe_target(database_url: str, db_env: str) -> str:
    """Return ``"<db_env> (host:port/name)"`` with any credentials stripped.

    The result is printed to the console, so it must never include the password.
    """
    url = (database_url or "").strip()
    env = (db_env or "").strip() or "(unset)"
    if not url:
        return f"{env} (DATABASE_URL unset)"
    # postgresql://user:pass@host:port/name -> host:port/name
    tail = url.split("://", 1)[-1]
    if "@" in tail:
        tail = tail.rsplit("@", 1)[1]
    return f"{env} ({tail})"


def load_env(db_env: str | None = None) -> str:
    """Load ``.env`` plus the ``.env.<DB_ENV>`` override and return the target description.

    ``db_env`` (from a ``--db-env`` flag) wins over the ambient ``DB_ENV`` so the target
    can be stated at the call site instead of depending on shell state. Importing
    ``api.config`` performs the layered load; ``api.db`` does not import it, so without
    this no ``DATABASE_URL`` is set at all.
    """
    if db_env:
        chosen = db_env.strip().lower()
        if chosen not in VALID_DB_ENVS:
            raise SystemExit(f"--db-env must be one of {', '.join(VALID_DB_ENVS)} (got {db_env!r})")
        os.environ["DB_ENV"] = chosen

    import api.config  # noqa: F401  (import performs the layered .env load)

    return describe_target(os.getenv("DATABASE_URL", ""), os.getenv("DB_ENV", ""))
