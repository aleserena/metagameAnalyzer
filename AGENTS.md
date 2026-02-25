# AGENTS.md

## Cursor Cloud specific instructions

### Overview

MTG Top 8 Metagame Analyzer — full-stack app with a **Python/FastAPI** backend (port 8000) and **React/Vite** frontend (port 5173). No database required; the app falls back to JSON file storage when `DATABASE_URL` is not set.

### Running services

- **Backend:** `python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload`
- **Frontend:** `cd web && npx vite --host 0.0.0.0 --port 5173`
- The Vite dev server proxies `/api` requests to `localhost:8000` (configured in `web/vite.config.ts`).

### Lint / Test / Build

| Task | Command |
|---|---|
| Python lint | `ruff check .` |
| JS lint | `cd web && npx eslint src` |
| Python tests | `python3 -m pytest` |
| JS tests | `cd web && npx vitest run` |
| Frontend build | `cd web && npm run build` (runs `tsc && vite build`) |

### Non-obvious caveats

- Use `python3` not `python` — the environment does not alias `python`.
- Ruff has pre-existing E402/I001 warnings in `alembic/`, `api/main.py`, and `src/mtgtop8/scraper.py`. These are intentional (path manipulation before imports) and are not regressions.
- The root `package.json` has husky pre-commit hooks that run build + both test suites. Use `--no-verify` on commits when iterating, and ensure all checks pass before the final push.
- Environment variables are documented in `.env.example`. No `.env` file is required for basic dev — the app runs in JSON-storage mode with sensible defaults.
