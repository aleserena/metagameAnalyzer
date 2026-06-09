# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

MTG Top 8 Metagame Analyzer — full-stack app for scraping and analyzing Magic: The Gathering tournament metagames from mtgtop8.com. **Python/FastAPI** backend (port 8000) and **React/Vite** frontend (port 5173). **PostgreSQL is required** — there is no JSON-only fallback mode.

## Running Services

Run backend and frontend in **two separate terminals** (do not use a combined `npm run dev`):

- **Terminal 1 — Backend:** `npm run api`
- **Terminal 2 — Frontend:** `npm run web`

Start the API first, then the frontend. Vite proxies `/api` → `http://localhost:8000` (configured in `web/vite.config.ts`).

## Commands

| Task | Command |
|---|---|
| Python lint | `ruff check .` |
| JS lint | `cd web && npx eslint src` |
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
│   ├── main.py      # All routes and most business logic (large, ~228KB)
│   ├── db.py        # SQLAlchemy models and database layer
│   ├── routers/     # Route handlers split by domain
│   ├── schemas/     # Pydantic request/response models
│   ├── services/    # Business logic (settings, aliases, excluded cards)
│   └── email.py     # Brevo email integration
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

**Supported formats:** EDH (Duel Commander), Standard, Pioneer, Modern, Legacy, Vintage, Pauper, cEDH, Premodern.

## Backend Patterns

**Adding a new API route:** Add the endpoint directly to `api/main.py` (where all routes live). Define request/response Pydantic models in the appropriate file under `api/schemas/`. Use `_db.session_scope()` for DB access and the `_decks` in-memory list for fast read queries.

**DB access pattern:**
```python
with _db.session_scope() as session:
    rows = session.query(MatchupRow).filter(...).all()
```

**Key DB models** (`api/db.py`):
- `DeckRow` — deck with `player_id`, `event_id`, `archetype`, `format_id`
- `MatchupRow` — per-round match result: `deck_id`, `opponent_player_id`, `opponent_deck_id`, `opponent_archetype`, `result` (`win|loss|draw|intentional_draw`), `round`. Both sides stored (inverse written automatically by `upsert_matchups_for_deck`).
- `PlayerRow` — canonical player with `display_name`

**In-memory data:** `_decks` is a list of dicts loaded from DB on startup. Most read endpoints query this list directly for speed. Mutations go to DB then trigger a reload.

## Frontend Patterns

**No component library or Tailwind.** Styles are inline (`style={{ ... }}`) or in `web/src/style.css` using plain CSS class names. Follow existing patterns — don't introduce a new styling system.

**Adding a new API call:** Add the function to `web/src/api.ts`. Return type is inferred from the response shape; add matching TypeScript types to `web/src/types.ts` if needed.

**Tooltip pattern:** `Matchups.tsx` has a self-contained tooltip positioning helper (`getTooltipPosition`) using `DOMRect` + `window.innerWidth/innerHeight`. Reuse this pattern for any hover-based popups.

**Scroll containers:** The matrix pages use `<div className="card" style={{ overflow: 'auto' }}>` as the scroll wrapper. `style.css` provides `.table-wrap` (with `-webkit-overflow-scrolling: touch`) and `.table-wrap-outer` (with gradient right-edge indicator). Use these classes for new scrollable tables.

**Scryfall integration** (`src/mtgtop8/card_lookup.py`): `lookup_cards(names)` returns `{name: {image_uris, mana_cost, cmc, type_line, colors, color_identity, card_faces}}`. The raw Scryfall card object has a `prices` field (`{usd, usd_foil, eur, eur_foil, tix}`) that `_build_entry()` currently discards — add it there to expose prices through the cache.

## Non-obvious Caveats

- Use `python3`, not `python` — the environment does not alias `python`.
- Ruff has pre-existing E402/I001 warnings in `alembic/`, `api/main.py`, and `src/mtgtop8/scraper.py`. These are intentional (path manipulation before imports) and are not regressions.
- The root `package.json` husky pre-commit hooks run the frontend build and both test suites. Use `--no-verify` when iterating; ensure all checks pass before final push.
- `api/main.py` is intentionally large and centralized — most FastAPI route logic lives there.

## Environment

Variables documented in `.env.example`. A `.env` file with `DATABASE_URL` is required. Set `DB_ENV=dev|staging|prod` to load `.env.dev`, `.env.staging`, or `.env.prod` as an override on top of the base `.env`.

Key variables:
- `DATABASE_URL` — PostgreSQL connection string (required)
- `ADMIN_PASSWORD`, `JWT_SECRET` — authentication
- `LOG_LEVEL`, `LOG_FORMAT=json` — production logging (JSON format auto-enabled on Railway)
- `SCRAPER_MAX_WORKERS` — parallel scraping threads
