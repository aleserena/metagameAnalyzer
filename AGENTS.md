# AGENTS.md

## Cursor Cloud specific instructions

### Overview

MTG Top 8 Metagame Analyzer — full-stack app with a **Python/FastAPI** backend (port 8000) and **React/Vite** frontend (port 5173). **PostgreSQL is required** — set `DATABASE_URL` before starting the backend. There is no JSON-only fallback mode.

### Running services

Run backend and frontend in **two separate terminals** (the combined `npm run dev` approach had issues; running separately is reliable):

- **Terminal 1 — Backend:** `npm run api` or `python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload`
- **Terminal 2 — Frontend:** `npm run web` or `cd web && npx vite --host 0.0.0.0 --port 5173`

Start the API first, then the frontend. The Vite dev server proxies `/api` to `http://localhost:8000` (see `web/vite.config.ts`).

### Lint / Test / Build

| Task | Command |
|---|---|
| Python lint | `ruff check .` |
| JS lint | `cd web && npx eslint src` |
| Python tests | `python3 -m pytest` |
| Python tests + coverage | `npm run test:py:coverage` |
| JS tests | `cd web && npx vitest run` |
| JS tests + coverage | `cd web && npm run test:coverage` |
| Frontend build | `cd web && npm run build` (runs `tsc && vite build`) |
| DB migrate (staging) | `npm run db:migrate:staging` |
| DB migrate (prod) | `npm run db:migrate:prod` |

### Non-obvious caveats

- Use `python3` not `python` — the environment does not alias `python`.
- Ruff has pre-existing E402/I001 warnings in `alembic/`, `api/main.py`, and `src/mtgtop8/scraper.py`. These are intentional (path manipulation before imports) and are not regressions.
- The root `package.json` has husky pre-commit hooks that run build + both test suites. Use `--no-verify` on commits when iterating, and ensure all checks pass before the final push.
- Environment variables are documented in `.env.example`. A `.env` file with `DATABASE_URL` is required to run the backend. Set `DB_ENV=dev|staging|prod` to load `.env.dev`, `.env.staging`, or `.env.prod` instead (the API loads the base `.env` first, then the env-specific override).
- Logging: `LOG_LEVEL` (default INFO) and `LOG_FORMAT=json` for production/Railway. On Railway, JSON format is auto-enabled; logs go to stdout with request method, path, status_code, duration_ms.

### Architecture shortcuts

**Backend — adding a route:** All routes live in `api/main.py`. Pydantic schemas go in `api/schemas/` (one file per domain). DB access uses `_db.session_scope()` (context manager). Heavy read queries use the in-memory `_decks` list (populated at startup) instead of hitting the DB.

**Backend — DB models** (`api/db.py`):
- `MatchupRow`: `deck_id`, `opponent_player_id`, `opponent_deck_id`, `opponent_archetype`, `result` (`win|loss|draw|intentional_draw`), `round`. Both sides of each match are stored (inverse written by `upsert_matchups_for_deck`).
- `DeckRow`: `player_id`, `event_id`, `archetype`, `format_id`
- `PlayerRow`: `id`, `display_name`

**Frontend — styling:** No Tailwind, no component library. Use inline styles or plain CSS classes in `web/src/style.css`. Existing scroll containers: `.table-wrap` (horizontal scroll + `-webkit-overflow-scrolling: touch`) and `.table-wrap-outer` (adds right-edge gradient indicator). The matchup matrix uses `<div className="card" style={{ overflow: 'auto' }}>` directly at `web/src/pages/Matchups.tsx:889` and `:1210`.

**Frontend — API layer:** All API calls are in `web/src/api.ts`. TypeScript types in `web/src/types.ts`. No GraphQL, no React Query — plain `fetch` wrapped in async functions.

**Scryfall prices:** The `_build_entry()` function in `src/mtgtop8/card_lookup.py` builds the cached card entry. The raw Scryfall object has a `prices` dict (`usd`, `usd_foil`, `eur`, `eur_foil`, `tix`) that is currently dropped. Add it to `_build_entry()` to expose prices through the existing cache.
