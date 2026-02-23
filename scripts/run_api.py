#!/usr/bin/env python3
"""Run the API against a specific database environment (dev, staging, prod).

Usage (from project root):
  python scripts/run_api.py dev
  python scripts/run_api.py staging
  python scripts/run_api.py prod

Uses .env.dev, .env.staging, or .env.prod (same format as .env). Set DB_ENV so
api.main loads the correct file on startup.
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ENVS = ("dev", "staging", "prod")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_api.py <dev|staging|prod> [uvicorn args...]", file=sys.stderr)
        print("Example: python scripts/run_api.py dev", file=sys.stderr)
        sys.exit(1)

    env_name = sys.argv[1].lower()
    if env_name not in ALLOWED_ENVS:
        print(f"Environment must be one of: {', '.join(ALLOWED_ENVS)}", file=sys.stderr)
        sys.exit(1)

    env_file = PROJECT_ROOT / f".env.{env_name}"
    if not env_file.exists():
        print(f"Missing {env_file}. Create it with DATABASE_URL=postgresql://... (and ADMIN_PASSWORD etc.)", file=sys.stderr)
        sys.exit(1)

    os.environ["DB_ENV"] = env_name
    # Default uvicorn args; pass extra args after env, e.g. run_api.py dev --reload
    uvicorn_args = sys.argv[2:] if len(sys.argv) > 2 else ["--reload"]
    cmd = [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"] + uvicorn_args
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, env=os.environ)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
