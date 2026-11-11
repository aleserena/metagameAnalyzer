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
| Python tests (DB) | DB tests use `TEST_DATABASE_URL` (never staging/prod); without it they skip. Tests migrate it to head at startup. Get one via Docker (`docker run --name mtg-test-db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=mtg_test -p 55432:5432 -d postgres:16`, URL `postgresql://postgres:test@localhost:55432/mtg_test`) or a local cluster (`initdb -D <dir> -U postgres -A trust`, `pg_ctl -D <dir> -o "-p 55432" start`, `createdb -h localhost -p 55432 -U postgres mtg_test`, URL `postgresql://postgres@localhost:55432/mtg_test`). |
| Python tests + coverage | `npm run test:py:coverage` |
| Single Python test | `python3 -m pytest tests/path/to/test.py::test_name` |
| JS tests | `cd web && npx vitest run` |
| JS tests + coverage | `cd web && npm run test:coverage` |
| Frontend build | `cd web && npm run build` |
| Dependencies | Local setup: `pip install -r requirements-dev.txt` (runtime-only `requirements.txt` is what the Docker image installs). Both are pinned and generated: edit `requirements.in` / `requirements-dev.in`, then `npm run deps:compile` (uv universal resolution; Docker pip-tools fallback). |
| DB migrate (staging) | `npm run db:migrate:staging` |
| DB migrate (prod) | `npm run db:migrate:prod` |

Migrations are applied **automatically on deploy**: Railway runs `alembic upgrade head` as `deploy.preDeployCommand` (`railway.json`; the image contains `alembic/` + `alembic.ini`). The `db:migrate:*` scripts remain for manual use.

## Architecture

```
metagameAnalyzer/
├── api/             # FastAPI backend
│   ├── main.py      # app setup only (~155 lines): FastAPI(), CORS, middleware, include_router, info endpoint, SPA static serving
│   ├── config.py    # .env loading + DATA_DIR / MAX_UPLOAD_JSON_BYTES (import first)
│   ├── state.py     # in-memory deck list + caches: the `state` holder + DB/alias loaders
│   ├── helpers.py   # pure date/rank/sort/filter + card-name normalization helpers
│   ├── route_helpers.py # helpers shared by 2+ routers (upload-link URL, matchup result, date range)
│   ├── results.py   # single match-result vocabulary: WIN/LOSS/DRAW_RESULTS (incl. intentional_draw_win/loss), effective_wld, invert_result — every win-rate statistic goes through it
│   ├── dates.py     # DD/MM/YY deck-date parsing and range helpers (parse_ddmmyy, parse_bound, in_range, sort_key)
│   ├── formats.py   # is_commander_format() — the one commander-format check (EDH/cEDH/Commander, any case)
│   ├── dependencies.py # auth/DB FastAPI dependencies (require_admin, …) + JWT
│   ├── db.py        # SQLAlchemy models and database layer
│   ├── routers/     # one APIRouter module per domain (see below) — ~90 routes; aggregated in routers/__init__.py
│   ├── schemas/     # Pydantic request/response models (one file per domain)
│   ├── services/    # business logic shared by routers:
│   │                #   settings (rank weights + ignore-lands list live in the `settings` table under `rank_weights`/`ignore_lands_cards`, imported once from the legacy `DATA_DIR/settings/*.json`; matchup thresholds),
│   │                #   scrape_job (background scrape job + status), scrape_store (persist scraped decks), event_import / event_export (event JSON round-trip),
│   │                #   deck_index (cached duplicate map + colour identities), rate_limit, captcha, mtgjson (card/price sync jobs), alerts, hadouken
│   └── email.py     # Brevo email integration
│   # routers/: health, auth, feedback, cards, decks, events, upload,
│   #           metagame, matchups, players, settings, data
├── src/mtgtop8/     # Core scraping/analysis library
│   ├── scraper.py   # Scrapes deck lists from mtgtop8.com
│   ├── analyzer.py  # Metagame analysis engine
│   ├── normalize.py # Deck/archetype normalization
│   ├── models.py    # Core data models (Event, Deck)
│   └── card_lookup.py # Card data lookup (MTGJSON-backed, Scryfall images + fallback)
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

**Scrape jobs:** `POST /api/v1/scrape` starts a background scrape (`api/services/scrape_job.py`), `GET /api/v1/scrape/status` reports progress and `POST /api/v1/scrape/stop` cancels it (all admin, handlers in `api/routers/data.py`); results are persisted by `api/services/scrape_store.py`.

**Shared helpers (use these, don't re-inline):** `is_commander_format()` (`api/formats.py`), `effective_wld()` (`api/results.py`), `db.utcnow_naive()` for naive-UTC timestamps (never `datetime.utcnow()`), `metagame._card_category()` for card type buckets. Path parameters are already URL-decoded by FastAPI — do not `unquote` them again.

**CI:** `.github/workflows/ci.yml` runs the backend suite against a Postgres 16 service (`TEST_DATABASE_URL`, `REQUIRE_DB_TESTS=1` so DB tests fail instead of skipping) plus lint and the frontend build/tests.

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
- `MatchupRow` — per-round match result: `deck_id`, `opponent_player_id`, `opponent_deck_id`, `opponent_archetype`, `result` (`win|loss|draw|intentional_draw|intentional_draw_win|intentional_draw_loss`; see `api/results.py`), `round`. Both sides stored (inverse written automatically by `upsert_matchups_for_deck`).
- `PlayerRow` — canonical player with `display_name`

**In-memory data:** the process-wide `state` object (`api/state.py`) holds `state.decks` (list of dicts loaded from DB on startup), plus `metagame_cache`, `events_cache`, `player_aliases`. Most read endpoints query `state.decks` directly for speed; mutations go to DB then call `_load_decks_from_db()` (which reassigns `state.decks`). It is a holder object on purpose — `from api.state import state` then `state.decks` always sees the current list, whereas `from api.state import decks` would capture a stale reference after reassignment. Tests patch `state.decks` (see `tests/test_api.py`).

**Derived-data caches and invalidation:** `state.decks_version` is bumped by `state.set_decks()` (replace the deck list) and `state.touch()` (invalidate without replacing, e.g. card data changed); both also clear `metagame_cache`/`events_cache`. `GET /metagame` (cached in `state.metagame_cache`), and `api/services/deck_index.py` (`duplicate_map()`, `color_identities()`, each computed once per version) key off it, plus `settings_service.version()` (bumped when rank weights or the ignore-lands list change) for `/metagame`. **Rule:** any mutation of an input to `/metagame`, the `/decks` colour filter/`color_identity`, or the duplicate map (decks, player aliases, the `cards` table, rank weights, ignore-lands list) must call `set_decks()`/`touch()` or bump the settings version. Degraded results (card-table lookup failed) are never cached: `lookup_cards(..., strict=True)` re-raises DB errors so callers can skip caching. `scripts/sync_mtgjson.py` runs in a separate process and cannot invalidate a running API's caches; after running it, trigger `POST /analyze` (which calls `touch()`) or restart the API. If players were inserted by an older release after migration 016 (NULL `players.name_key`), run `python3 -m scripts.backfill_player_name_keys --apply --db-env <env>` (idempotent).

**Player aliases:** stored in the database when available (`_db.get_player_aliases`), with `player_aliases.json` in `DATA_DIR` as the JSON fallback. Managed via the `/api/v1/player-aliases` endpoints in `api/routers/players.py`. (The JSON fallback only applies when no database is configured, which the app does not support in normal operation.)

## Frontend Patterns

**No component library or Tailwind.** Styles are inline (`style={{ ... }}`) or in `web/src/style.css` using plain CSS class names. Follow existing patterns — don't introduce a new styling system.

**Adding a new API call:** Add the function to `web/src/api.ts` (TypeScript types in `web/src/types.ts`). No GraphQL, no React Query — plain `fetch` wrapped in async functions. Return type is inferred from the response shape; add matching types to `types.ts` if needed.

**Tooltip pattern:** `Matchups.tsx` has a self-contained tooltip positioning helper (`getTooltipPosition`) using `DOMRect` + `window.innerWidth/innerHeight`. Reuse this pattern for any hover-based popups.

**Scroll containers:** `style.css` provides `.table-wrap` (with `-webkit-overflow-scrolling: touch`) and `.table-wrap-outer` (adds gradient right-edge indicator). The matrix tables in `Matchups.tsx` nest `.table-wrap` inside `.table-wrap-outer`, with `overflow: 'auto'` + `touchAction: 'pan-x pan-y'` on the inner matrix div. Use these classes for new scrollable tables.

**Card data (MTGJSON + Scryfall images)** (`src/mtgtop8/card_lookup.py`): `lookup_cards(names)` returns `{name: {image_uris, mana_cost, cmc, type_line, oracle_text, colors, color_identity, card_faces, prices}}` (`prices` is `{usd, usd_foil, eur, eur_foil, tix}`). Metadata/oracle text/prices are read from the **`cards` Postgres table** (model `CardRow` in `api/db.py`), which is populated from **MTGJSON** by `api/services/mtgjson.py`. Images are not stored — `scryfall_image_urls(scryfall_id, face)` builds `cards.scryfall.io` URLs from each card's `scryfall_id` (two-faced layouts get `/front/` + `/back/`). Names missing from the table fall back to the legacy Scryfall API (`_scryfall_lookup_cards`, cached in `.scryfall_cache.json`); disable with `MTGJSON_SCRYFALL_FALLBACK=0`. `autocomplete_cards` queries the table locally. The MTGJSON sync is **manual** (no auto-download): run `python3 scripts/sync_mtgjson.py [--prices|--all]` (synchronous CLI) or use the **Sync MTGJSON cards** / **Update prices** buttons on the Settings page. The admin endpoints `POST /api/v1/settings/sync-mtgjson` and `.../sync-mtgjson-prices` start a **background thread** (downloads are hundreds of MB / minutes) and return immediately; the UI polls `GET /api/v1/settings/sync-mtgjson/status`. Job state lives in-memory in `api/services/mtgjson.py` (`start_sync_job` / `get_sync_status`); only one sync runs at a time and a server restart resets status to idle (DB upserts are idempotent). The last *successful* completion time of each job is persisted in the `settings` table (`mtgjson_last_sync_metadata` / `mtgjson_last_sync_prices`) and surfaced as `jobs.<name>.last_success_at` in the status response, so the Settings page can show it after a restart; the metadata job falls back to `MAX(cards.updated_at)` for data synced before this was recorded. The Scryfall **oracle-tag** category system (`refresh_otag_index` / `get_card_categories`) still calls the Scryfall search API, but the refresh now runs as the `otag` background job in the same single-job slot: `POST /api/v1/settings/refresh-otag-index` returns `{started, running, message}` immediately and progress/result (`{"refreshed": {category: count}}`) appear under `jobs.otag` in the status response (last success persisted as `otag_last_refresh`, no fallback).

## Non-obvious Caveats

- Use `python3`, not `python` — the environment does not alias `python`.
- DB URLs are rewritten to `postgresql+psycopg2://` in `api/db.py` and `alembic/env.py`: SQLAlchemy 2.1 maps a bare `postgresql://` to `psycopg` (v3), which isn't installed — that silently put prod in JSON mode once. If the DB is configured but unusable, `api/services/alerts.py` logs `event=db_unavailable`, `/api/v1/health` returns 503 (Railway healthcheck in `railway.json` then blocks the deploy), admins get a banner, and a GitHub issue + `ALERT_EMAIL` email are sent. Separately, every ERROR+ log record is emailed to `ALERT_EMAIL` (batched/deduped by `ErrorEmailHandler` in `api/logging_config.py`), as are new deployments and same-deployment restarts (`notify_deployment`). Pass `extra={"email": False}` on an error log that already has its own alert, and keep secrets out of logs anyway even though `redact_secrets` masks URLs/tokens.
- **Additive-migration rule:** Railway runs the migration before switching traffic and keeps the old release if the new deploy fails, so every migration must leave the previous release working: add nullable columns and indexes only; dropping or retyping happens in a later release. A failing migration blocks the deploy. ALTER/CREATE INDEX take table locks while the old release is still serving, and all pending migrations share one transaction, so those locks are held until it commits: keep backfills set-based (one `UPDATE … FROM unnest(…)` per chunk, as in 016/017, never one statement per value), and deploy when no scrape or MTGJSON sync is running. `alembic/env.py` sets `SET LOCAL lock_timeout = '10s'`, so a migration blocked behind a long transaction fails (blocking the deploy) rather than queueing every query behind the ALTER and hanging the site. Dates are stored only as DATE (`events.event_date` / `decks.event_date`); `EventRow.date` / `DeckRow.date` are a DD/MM/YY view of it (hybrid property: assigning parses the text, unparseable input stores NULL), so sort and filter on `event_date`. Migration 018, which dropped the text `date` columns, is the one exception to the additive rule: it syncs `event_date` from the text first and fails the deploy, changing nothing, if a non-empty text date cannot be parsed or a year is outside 2000–2099 (fix the rows and redeploy); the release before it cannot run against a migrated database, so roll forward rather than back.
- The E402/I001 warnings in `alembic/`, `api/main.py`, and `src/mtgtop8/scraper.py` (intentional — path manipulation before imports) are now suppressed via `per-file-ignores` in `pyproject.toml`, so `ruff check .` is clean.
- Husky git hooks (`.husky/`): **pre-commit** runs fast lint only (`npm run lint`); **pre-push** runs the frontend build and both test suites (`npm run build`, `npm run test`, `npm run test:py`). Use `--no-verify` to bypass either when iterating, but ensure all checks pass before the final push.
- Ruff `per-file-ignores` (in `pyproject.toml`) suppress E402/I001 for the path-manipulation entrypoints (`api/main.py`, `src/mtgtop8/scraper.py`), `alembic/`, `scripts/`, and `tests/`. Real bugs (F-codes) are still enforced everywhere, so `ruff check .` should stay green.

## Environment

Variables documented in `.env.example`. A `.env` file with `DATABASE_URL` is required. Set `DB_ENV=dev|staging|prod` to load `.env.dev`, `.env.staging`, or `.env.prod` as an override on top of the base `.env`.

Key variables:
- `DATABASE_URL` — PostgreSQL connection string (required)
- `ADMIN_PASSWORD`, `JWT_SECRET` — authentication; both required on Railway (app refuses to start without them), optional locally. A local `.env` containing `RAILWAY_ENVIRONMENT_NAME` blocks startup and test collection unless both are set. Admin sessions last 12 hours (`JWT_EXP_SECONDS`); changing `JWT_SECRET` logs everyone out. Upload/edit links expire after 7 days by default; an event-edit link stays valid for 12 hours once opened (`EVENT_EDIT_SITTING_HOURS`). Operating notes: `docs/SECURITY_OPERATIONS.md`.
- `LOG_LEVEL`, `LOG_FORMAT=json` — production logging (JSON format auto-enabled on Railway)
- `SCRAPER_MAX_WORKERS` — parallel scraping threads
