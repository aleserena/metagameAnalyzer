"""Alembic environment: use DATABASE_URL and api.db models."""

import os
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

# Add project root to path
_project_root = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(_project_root))

# Load .env so DATABASE_URL is set when running: alembic upgrade head
_env_path = _project_root / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        pass

from api.db import Base

config = context.config
if config.config_file_name is not None:
    # Allow DATABASE_URL to override sqlalchemy.url (only if it looks like a postgres URL)
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url and (url.startswith("postgresql://") or url.startswith("postgres://")):
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        config.set_main_option("sqlalchemy.url", url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = (os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or "").strip()
    if not url:
        raise RuntimeError(
            "Set DATABASE_URL in .env (or sqlalchemy.url in alembic.ini) to run migrations. "
            "Use a full PostgreSQL URL, e.g. postgresql://user:password@host:port/database"
        )
    if not (url.startswith("postgresql://") or url.startswith("postgres://")):
        raise RuntimeError(
            "DATABASE_URL must be a full PostgreSQL URL (postgresql://user:password@host:port/database). "
            "You have something like host:port only; copy the full DATABASE_URL from Railway or your provider."
        )
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    connectable = create_engine(url, pool_pre_ping=True)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
