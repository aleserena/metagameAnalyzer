#!/usr/bin/env python3
"""Run Alembic against a specific environment (dev, staging, prod).

Usage (from project root):
  python scripts/run_alembic.py dev upgrade head
  python scripts/run_alembic.py staging current
  python scripts/run_alembic.py prod revision --autogenerate -m "add column"

Uses .env.dev, .env.staging, or .env.prod in the project root (same format as .env:
DATABASE_URL=postgresql://...). Values from the file override any DATABASE_URL already
set in the environment. Create these files and add them to .gitignore.
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ENVS = ("dev", "staging", "prod")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_alembic.py <dev|staging|prod> <alembic args...>", file=sys.stderr)
        print("Example: python scripts/run_alembic.py dev upgrade head", file=sys.stderr)
        sys.exit(1)

    env_name = sys.argv[1].lower()
    if env_name not in ALLOWED_ENVS:
        print(f"Environment must be one of: {', '.join(ALLOWED_ENVS)}", file=sys.stderr)
        sys.exit(1)

    env_file = PROJECT_ROOT / f".env.{env_name}"
    if not env_file.exists():
        print(f"Missing {env_file}. Create it with DATABASE_URL=postgresql://...", file=sys.stderr)
        sys.exit(1)

    try:
        from dotenv import load_dotenv
    except ImportError:
        print("Install python-dotenv to use this script: pip install python-dotenv", file=sys.stderr)
        sys.exit(1)

    load_dotenv(env_file, override=True)  # always use DATABASE_URL from file, not from shell
    os.environ["DB_ENV"] = env_name  # so alembic env.py loads the same file if needed
    if not os.getenv("DATABASE_URL"):
        print(f"No DATABASE_URL in {env_file}", file=sys.stderr)
        sys.exit(1)

    alembic_args = sys.argv[2:]
    if not alembic_args:
        alembic_args = ["current"]

    cmd = [sys.executable, "-m", "alembic"] + alembic_args
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, env=os.environ)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
