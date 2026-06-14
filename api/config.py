"""Shared configuration: .env loading and core constants.

Imported first by api.main (and indirectly by every router) so that
environment variables are loaded before anything reads them.
"""

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root so DATABASE_URL (and others) are set before any config.
# First load .env (base), then if DB_ENV=dev|staging|prod load .env.{env} to override.
try:
    from dotenv import load_dotenv

    _env_base = _PROJECT_ROOT / ".env"
    if _env_base.exists():
        load_dotenv(_env_base)
    _db_env = os.getenv("DB_ENV", "").strip().lower()
    if _db_env in ("dev", "staging", "prod"):
        _env_override = _PROJECT_ROOT / f".env.{_db_env}"
        if _env_override.exists():
            load_dotenv(_env_override)
except ImportError:
    pass

# Directory for data files (decks.json, player_aliases.json, etc.).
DATA_DIR = Path(os.getenv("DATA_DIR", str(_PROJECT_ROOT)))
if not DATA_DIR.is_absolute():
    DATA_DIR = _PROJECT_ROOT / DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Max JSON upload size for admin load / deck import (bytes). Default 50 MiB.
MAX_UPLOAD_JSON_BYTES = int(os.getenv("MAX_UPLOAD_JSON_BYTES", str(50 * 1024 * 1024)))
