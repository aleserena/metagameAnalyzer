# AGENTS.md

**Full project guidance lives in [CLAUDE.md](CLAUDE.md) — read it.** It is the single source of truth for architecture, commands, backend/frontend patterns, environment variables, and non-obvious caveats. This file only holds notes specific to Cursor Cloud / sandboxed agent environments.

## Cursor Cloud specific instructions

MTG Top 8 Metagame Analyzer — **Python/FastAPI** backend (port 8000) + **React/Vite** frontend (port 5173). **PostgreSQL is required** (`DATABASE_URL` must be set); there is no JSON-only fallback. See [CLAUDE.md](CLAUDE.md) for the rest.

**Run services in two separate terminals** — the combined `npm run dev` approach had issues; running separately is reliable. Start the API first, then the frontend:

- **Terminal 1 — Backend:** `npm run api` (or `python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload`)
- **Terminal 2 — Frontend:** `npm run web` (or `cd web && npx vite --host 0.0.0.0 --port 5173`)

Use `python3`, not `python` — the environment does not alias `python`. Lint/test/build commands and everything else: see [CLAUDE.md](CLAUDE.md).
