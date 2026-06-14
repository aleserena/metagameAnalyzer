# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

MTG Top 8 Metagame Analyzer — full-stack app for scraping and analyzing Magic: The Gathering tournament metagames from mtgtop8.com. **Python/FastAPI** backend (port 8000) and **React/Vite** frontend (port 5173). **PostgreSQL is required** — there is no JSON-only fallback mode.

## Running Services

Run backend and frontend in **two separate terminals** (do not use a combined `npm run dev`):

- **Terminal 1 — Backend:** `npm run api`
- **Terminal 2 — Frontend:** `npm run web`

Start the API first, then the frontend. Vite proxies `/api` → `http://localhost:8000` (configured in `web/vite.config.ts`).

> This file is the **single source of truth** for project guidance. `AGENTS.md` is a thin pointer here (plus a few Cursor-Cloud-specific notes) — keep new guidance in this file.

## Commands

| Task | Command |
|---|---|
| Lint everything | `npm run lint` (runs `lint:py` + `lint:web`) |
| Python lint | `npm run lint:py` (`ruff check .`) |
| JS lint | `npm run lint:web` (`cd web && npm run lint`) |
| Python tests | `python3 -m pytest` |
| Python tests + coverage | `npm run test:py:coverage` |
| Single Python test | `python3 -m pytest tests/path/to/test.py::test_name` |
| JS tests | `cd web && npx vitest run` |
| JS tests + coverage | `cd web && npm run test:coverage` |
| Frontend build | `cd web && npm run build` |
| DB migrate (staging) | `npm run db:migrate:staging` |
| DB migrate (prod) | `npm run db:migrate:prod` |

## Architecture

```
metagameAnalyzer/
├── api/             # FastAPI backend
│   ├── main.py      # app setup only (~155 lines): FastAPI(), CORS, middleware, include_router, info endpoint, SPA static serving
│   ├── config.py    # .env loading + DATA_DIR / MAX_UPLOAD_JSON_BYTES (import first)
│   ├── state.py     # in-memory deck list + caches: the `state` holder + DB/alias loaders
│   ├── helpers.py   # pure date/rank/sort/filter + card-name normalization helpers
│   ├── route_helpers.py # helpers shared by 2+ routers (upload-link URL, matchup result, date range)
│   ├── dependencies.py # auth/DB FastAPI dependencies (require_admin, …) + JWT
│   ├── db.py        # SQLAlchemy models and database layer
│   ├── routers/     # one APIRouter module per domain (see below) — ~90 routes; aggregated in routers/__init__.py
│   ├── schemas/     # Pydantic request/response models (one file per domain)
│   ├── services/    # settings.py — rank weights, ignore-lands list, matchup thresholds
│   └── email.py     # Brevo email integration
│   # routers/: health, auth, feedback, cards, decks, events, upload,
│   #           metagame, matchups, players, settings, data
├── src/mtgtop8/     # Core scraping/analysis library
│   ├── scraper.py   # Scrapes deck lists from mtgtop8.com
│   ├── analyzer.py  # Metagame analysis engine
│   ├── normalize.py # Deck/archetype normalization
│   ├── models.py    # Core data models (Event, Deck)
│   └── card_lookup.py # Card data lookup (Scryfall)
├── web/src/         # React/TypeScript frontend
│   ├── App.tsx      # Routing
│   ├── api.ts       # API client (~35KB)
│   ├── types.ts     # TypeScript interfaces
│   ├── pages/       # Route-level components
│   ├── components/  # Reusable UI components
│   ├── hooks/       # Custom React hooks
│   └── contexts/    # React context for state
├── alembic/         # Database migrations
└── scripts/         # Utility scripts (migrations, data fixes)
```

**Data flow:** Web UI or CLI → FastAPI (port 8000) → scraper fetches mtgtop8.com → data normalized → stored in PostgreSQL → API serves data → React frontend renders dashboards, deck browser, leaderboard, metagame analysis.

**Supported formats** (`src/mtgtop8/config.py` FORMATS, mirrored in `web/src/config.ts`): EDH (Duel Commander), Standard, Pioneer, Modern, Legacy, Vintage, Pauper, cEDH, Premodern, Explorer, Historic, Alchemy, Peasant, Block, Extended, Highlander, Canadian Highlander.

**Route index:** `docs/API_ROUTES.md` lists every endpoint with its handler function name and source router — grep the handler name to jump to it. It is **auto-generated** by `scripts/gen_api_routes.py` (scans `api/main.py` + `api/routers/*.py`); after adding/changing a route run `npm run gen:routes` (pre-push runs `gen:routes:check` and fails if it's stale).

## Backend Patterns

**Adding a new API route:** Add the endpoint to the matching domain router in `api/routers/<domain>.py` (each defines `router = APIRouter()`, aggregated in `api/routers/__init__.py`). A brand-new domain needs a new router module wired into `__init__.py`. Define request/response Pydantic models in the appropriate file under `api/schemas/`. Use `_db.session_scope()` for DB access and `state.decks` for fast in-memory read queries. Import shared helpers from `api.helpers`/`api.route_helpers`, auth dependencies from `api.dependencies`, and the state holder from `api.state`. After adding a route run `npm run gen:routes`.

**DB access pattern:**
```python
with _db.session_scope() as session:
    rows = session.query(MatchupRow).filter(...).all()
```

**Key DB models** (`api/db.py`):
- `DeckRow` — deck with `player_id`, `event_id`, `archetype`, `format_id`
- `MatchupRow` — per-round match result: `deck_id`, `opponent_player_id`, `opponent_deck_id`, `opponent_archetype`, `result` (`win|loss|draw|intentional_draw`), `round`. Both sides stored (inverse written automatically by `upsert_matchups_for_deck`).
- `PlayerRow` — canonical player with `display_name`

**In-memory data:** the process-wide `state` object (`api/state.py`) holds `state.decks` (list of dicts loaded from DB on startup), plus `metagame_cache`, `events_cache`, `player_aliases`. Most read endpoints query `state.decks` directly for speed; mutations go to DB then call `_load_decks_from_db()` (which reassigns `state.decks`). It is a holder object on purpose — `from api.state import state` then `state.decks` always sees the current list, whereas `from api.state import decks` would capture a stale reference after reassignment. Tests patch `state.decks` (see `tests/test_api.py`).

**Player aliases:** stored in the database when available (`_db.get_player_aliases`), with `player_aliases.json` in `DATA_DIR` as the JSON fallback. Managed via the `/api/v1/player-aliases` endpoints in `api/main.py` (not in `api/services/`).

## Frontend Patterns

**No component library or Tailwind.** Styles are inline (`style={{ ... }}`) or in `web/src/style.css` using plain CSS class names. Follow existing patterns — don't introduce a new styling system.

**Adding a new API call:** Add the function to `web/src/api.ts` (TypeScript types in `web/src/types.ts`). No GraphQL, no React Query — plain `fetch` wrapped in async functions. Return type is inferred from the response shape; add matching types to `types.ts` if needed.

**Tooltip pattern:** `Matchups.tsx` has a self-contained tooltip positioning helper (`getTooltipPosition`) using `DOMRect` + `window.innerWidth/innerHeight`. Reuse this pattern for any hover-based popups.

**Scroll containers:** `style.css` provides `.table-wrap` (with `-webkit-overflow-scrolling: touch`) and `.table-wrap-outer` (adds gradient right-edge indicator). The matrix tables in `Matchups.tsx` nest `.table-wrap` inside `.table-wrap-outer`, with `overflow: 'auto'` + `touchAction: 'pan-x pan-y'` on the inner matrix div. Use these classes for new scrollable tables.

**Scryfall integration** (`src/mtgtop8/card_lookup.py`): `lookup_cards(names)` returns `{name: {image_uris, mana_cost, cmc, type_line, colors, color_identity, card_faces, prices}}`. `prices` is `{usd, usd_foil, eur, eur_foil, tix}`; when the default printing has no `usd`, `_build_entry()` falls back to a `/cards/named` lookup to pick a priced printing. Results are cached in `.scryfall_cache.json`.

## Non-obvious Caveats

- Use `python3`, not `python` — the environment does not alias `python`.
- The E402/I001 warnings in `alembic/`, `api/main.py`, and `src/mtgtop8/scraper.py` (intentional — path manipulation before imports) are now suppressed via `per-file-ignores` in `pyproject.toml`, so `ruff check .` is clean.
- Husky git hooks (`.husky/`): **pre-commit** runs fast lint only (`npm run lint`); **pre-push** runs the frontend build and both test suites (`npm run build`, `npm run test`, `npm run test:py`). Use `--no-verify` to bypass either when iterating, but ensure all checks pass before the final push.
- Ruff `per-file-ignores` (in `pyproject.toml`) suppress E402/I001 for the path-manipulation entrypoints (`api/main.py`, `src/mtgtop8/scraper.py`), `alembic/`, `scripts/`, and `tests/`. Real bugs (F-codes) are still enforced everywhere, so `ruff check .` should stay green.
- `api/main.py` is intentionally large and centralized — most FastAPI route logic lives there.

## Environment

Variables documented in `.env.example`. A `.env` file with `DATABASE_URL` is required. Set `DB_ENV=dev|staging|prod` to load `.env.dev`, `.env.staging`, or `.env.prod` as an override on top of the base `.env`.

Key variables:
- `DATABASE_URL` — PostgreSQL connection string (required)
- `ADMIN_PASSWORD`, `JWT_SECRET` — authentication
- `LOG_LEVEL`, `LOG_FORMAT=json` — production logging (JSON format auto-enabled on Railway)
- `SCRAPER_MAX_WORKERS` — parallel scraping threads
