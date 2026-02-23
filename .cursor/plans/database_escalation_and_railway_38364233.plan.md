---
name: Database escalation and Railway
overview: Plan for introducing a PostgreSQL database to replace in-memory/JSON storage, and for deploying the app on Railway with a managed database. Covers schema design, Railway setup, and implementation approach.
todos:
  - id: todo-1771599813460-6pw4ujbyw
    content: ""
    status: completed
isProject: false
---

# Database escalation and Railway deployment

## Current state

- **Storage:** All deck data lives in an in-memory list `_decks` in [api/main.py](api/main.py), loaded from `DATA_DIR/decks.json` on startup and saved on load/clear. Admin settings use JSON files: `player_aliases.json`, `ignore_lands_cards.json`, `rank_weights.json`.
- **Data shape:** Each deck is a dict (see [src/mtgtop8/models.py](src/mtgtop8/models.py) and [web/src/types.ts](web/src/types.ts)): `deck_id`, `event_id`, `format_id`, `name`, `player`, `event_name`, `date`, `rank`, `player_count`, `mainboard` / `sideboard` (list of `{qty, card}`), `commanders`, `archetype`.
- **Deploy:** [Dockerfile](Dockerfile) builds frontend and runs `uvicorn api.main:app`; no database or Railway config in the repo.

## Why use a database

- **Persistence:** Data survives restarts and redeploys; no dependency on a single `decks.json` file or ephemeral filesystem.
- **Scale:** Support larger datasets and multiple app instances; filtering and pagination can be done in the DB with indexes.
- **Railway:** Ephemeral filesystem means file-based storage is not reliable; a managed PostgreSQL instance is the right fit.

## Target data model

High-level entities and where they live today:

```mermaid
erDiagram
    Deck ||--o{ DeckCard_main : "mainboard"
    Deck ||--o{ DeckCard_side : "sideboard"
    Deck }o--|| Event : "event_id"
    PlayerAlias }o--o{ Deck : "player name"

    Deck {
        int deck_id PK
        int event_id
        string format_id
        string name
        string player
        string event_name
        string date
        string rank
        int player_count
        string commanders "JSON array"
        string archetype
    }

    DeckCard_main {
        int deck_id FK
        string card
        int qty
    }

    DeckCard_side {
        int deck_id FK
        string card
        int qty
    }

    Event {
        int event_id PK
        string format_id
        string name
        string date
    }

    PlayerAlias {
        string alias PK
        string canonical
    }
```



**Recommended schema (PostgreSQL):**

- `**decks`** — One row per deck. Store `mainboard` and `sideboard` as **JSONB** (e.g. `[{"qty":1,"card":"Sol Ring"},...]`) to avoid a large join explosion and to keep compatibility with existing `Deck.from_dict`/`to_dict`. Columns: `deck_id` (PK), `event_id`, `format_id`, `name`, `player`, `event_name`, `date`, `rank`, `player_count`, `commanders` (JSONB or TEXT), `archetype`, `mainboard` (JSONB), `sideboard` (JSONB).
- `**events`** (optional) — Normalized table `(event_id, format_id, name, date)` for deduplication and future event-level queries. Can be derived from decks at first and backfilled.
- `**player_aliases`** — `(alias TEXT PRIMARY KEY, canonical TEXT NOT NULL)`; replaces `player_aliases.json`.
- **Settings** — Either keep `ignore_lands_cards` and `rank_weights` in JSON files in a persistent volume, or add a small `settings` table (key, value JSONB). For Railway, moving them into the DB avoids volume dependency.

**Event ID and deck ID namespacing:** MTGTop8 event IDs (from the site, e.g. 80455) must never collide with manually created events. Use a separate ID space for manual events: e.g. add an `origin` on `events` (`'mtgtop8'` | `'manual'`) and treat `event_id` as unique per origin, or assign manual events IDs from a dedicated sequence (e.g. negative IDs, or IDs >= 1_000_000) so they never equal MTGTop8 numeric IDs. Apply the same care for deck IDs if manual uploads can create decks: use a separate sequence or high range for manual deck IDs so they do not clash with scraped `deck_id` values from MTGTop8.

**Indexes (for current API filters):** `event_id`, `format_id`, `date` (or parsed date), `player` (normalized/canonical), `archetype`. For “filter by card” you can use JSONB containment/indexing or a separate `deck_cards(deck_id, card)` table if you need efficient card lookups at scale.

## Events and deck uploads

**All of the following are admin-only:** creating events, uploading decks, and any management of events/decks (edit, delete) must require admin auth (JWT). Only admins see the Events/Data UI and can call the corresponding API endpoints.

- **Generate events:** Allow creating events from inside the app (admin-only). An event has: `event_id` (optional; if omitted, assign from a **manual-event ID space** — see "Event ID and deck ID namespacing" in the schema section above), `event_name`, `date` (DD/MM/YY), `format_id`. Store in `events` table; when decks are later uploaded to this event, they reference this `event_id`.
- **Upload decks to an event:** Admin can upload a JSON file (or paste `decks` array) and choose:
  - **Existing event:** Select an event from a dropdown (from `events` or derived from current decks). Incoming decks are associated with that `event_id` (overwrite or patch `event_id`/`event_name`/`date` from the selected event if needed so they match).
  - **New event:** Provide event name, date, format; create the event row, then insert decks with that `event_id`. For scraped-style JSON where each deck has its own `event_id`/`event_name`/date, support "create one event and attach all decks to it" or "use first deck's event info to create event."
- **API shape:** e.g. `POST /api/events` (body: `event_name`, `date`, `format_id`, optional `event_id`) and `POST /api/events/{event_id}/decks` (body: file or `decks: [...]`). Or a single `POST /api/load` variant that accepts `event_id` (existing) or `new_event: { event_name, date, format_id }` and uploads decks accordingly. Existing scrape flow can remain (scrape creates/uses events from MTGTop8); this adds manual "create event + upload decks" for custom data.

## In-app DB data management

Provide a way to modify database content from inside the application (admin-only):

- **Events:** List events (from `events` table and/or distinct from decks). Allow edit (name, date, format_id) and delete. Delete can be "delete event only" (decks unlinked or set to a placeholder) or "delete event and all its decks" with confirmation.
- **Decks:** List decks with filters (event, player, date range). Allow delete (single or bulk by selection). Optional: edit deck metadata (player, name, rank, archetype) without touching mainboard/sideboard.
- **Player aliases:** Already have GET/POST/DELETE in the API; ensure these write to the DB when `DATABASE_URL` is set. Expose in Settings as today.
- **Settings (ignore_lands, rank_weights):** If stored in DB, add simple edit UI in Settings (admin) so they can be changed without direct DB access.
- **Placement:** New "Data" or "Manage data" tab in the admin area (alongside Scrape and Settings), or extend Settings with subsections: Events, Decks, Aliases, and app settings. Use existing admin auth (JWT) for all of these endpoints.

## What to do on Railway

1. **Create a project** (or use existing) and deploy the app from the repo (Dockerfile or Nixpacks).
2. **Add PostgreSQL:** In the project, click **+ New** → **Database** → **PostgreSQL**. Railway creates a Postgres service and exposes:
  - `**DATABASE_URL`** (and often `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`) to the app service when both are in the same project.
3. **Connect app to DB:** In the app service, add a variable reference to `DATABASE_URL` from the Postgres service (Railway UI: Variables → New Variable → Reference from PostgreSQL). The app should read `os.getenv("DATABASE_URL")` and use it for the SQLAlchemy engine.
4. **Optional:** Use **Volumes** only if you explicitly keep file-based settings (e.g. `DATA_DIR` on a volume); otherwise prefer storing settings in the database so the app stays stateless.
5. **Build/start:** Ensure the Dockerfile (or stack) installs the DB driver and migration tool; run migrations in a release phase or at startup if no separate job.

No special “Railway-only” model changes: the app just needs a `DATABASE_URL` and to use it for all persistence.

## Using the Railway DB while developing locally

Manual steps to point your local app at the Railway PostgreSQL instance:

1. **Get the connection URL from Railway:** In the Railway project dashboard, open the PostgreSQL service → **Variables** (or **Connect**). Copy `DATABASE_URL` (or construct it from `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`).
2. **Set local env:** In the project root, create or edit `.env` and add:
  - `DATABASE_URL=postgresql://user:password@host:port/railway` (use the exact URL from Railway). Do not commit `.env` (keep it in `.gitignore`).
3. **Run migrations locally:** From the project root, run the migration command (e.g. `alembic upgrade head` or `python -m api.db migrate`) so your local code and the Railway DB schema stay in sync.
4. **Start the app:** Run the API as usual (e.g. `python -m uvicorn api.main:app --reload --port 8000`). The app will read `DATABASE_URL` from the environment and connect to Railway Postgres.
5. **Optional — load env from file:** If the app does not auto-load `.env`, use `dotenv` or run with `env $(cat .env) uvicorn ...` (Unix) or in PowerShell set `$env:DATABASE_URL = "..."` before starting.

**Cautions:** The Railway DB is shared (e.g. with production or other devs if you use one project). Avoid destructive bulk operations (e.g. "clear all decks") unless you intend to affect that shared data. Prefer a separate Railway project or a local Postgres instance for heavy or destructive testing.

## Implementation approach

1. **Add dependencies:** `sqlalchemy`, `asyncpg` or `psycopg2-binary`, and `alembic` in [requirements.txt](requirements.txt).
2. **DB layer:** Introduce a small module (e.g. `api/db.py` or `src/mtgtop8/db/`) that:
  - Defines SQLAlchemy models for `decks`, `player_aliases`, and optionally `events` and `settings`.
  - Provides a session/engine (sync or async) from `DATABASE_URL`; if unset, keep current in-memory + file behavior so local dev without a DB still works.
3. **Migrations:** Use Alembic to create and evolve tables (initial schema: decks, player_aliases, and optionally events/settings).
4. **API changes:** In [api/main.py](api/main.py):
  - Replace global `_decks` and file load/save with: load decks from DB on startup (or on first request) and write through to DB on load/clear/scrape.
  - Replace `_player_aliases` read/write with DB table; keep the same REST contract.
  - Optionally move ignore_lands and rank_weights into DB-backed getters/setters.
5. **Compatibility:** Keep using `Deck.from_dict` / `to_dict` in the analyzer and for API responses; the repository layer converts between ORM rows (or JSONB) and the existing dict/`Deck` shape so [src/mtgtop8/analyzer.py](src/mtgtop8/analyzer.py) and the frontend stay unchanged.
6. **Scrape flow:** After scrape completes, persist the new decks to the database. Use **duplicate protection:** upsert by `(event_id, deck_id)` or insert-only when a deck with that `deck_id` (and event) does not already exist, so re-scraping the same event does not create duplicate deck rows. Optionally update existing rows (e.g. rank, player) if the scrape has newer data.
7. **Events and uploads:** Implement `POST /api/events` (create event), `POST /api/events/{event_id}/decks` (upload decks to existing event), and extend `POST /api/load` (or add a dedicated endpoint) to support creating a new event and attaching uploaded decks. All of these endpoints are **admin-only**. Scrape flow continues to create/use events from MTGTop8; manual flow uses the new event CRUD and deck upload. Use the event ID namespacing so manual event IDs never equal MTGTop8 event IDs.
8. **In-app data management:** Add **admin-only** "Data" (or "Manage data") section (all list/edit/delete for events and decks require admin JWT): list/edit/delete events; list/delete (and optionally edit) decks; keep player aliases and settings in Settings. All protected by existing JWT admin auth.
9. **Tests:** Extend [tests/test_api.py](tests/test_api.py) to run against an in-memory SQLite or a test Postgres instance; or keep a “no DB” mode for existing tests and add a separate integration test with a real DB.

## Summary


| Topic                      | Recommendation                                                                                                         |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Database**               | PostgreSQL (Railway managed).                                                                                          |
| **Model**                  | `decks` table with JSONB for mainboard/sideboard/commanders; `player_aliases` table; optional `events` and `settings`. |
| **Railway**                | Add PostgreSQL service, reference `DATABASE_URL` in the app, run migrations at deploy/startup.                         |
| **Backward compatibility** | Keep `Deck` and API response shape; add a “no DB” fallback when `DATABASE_URL` is unset.                               |


- **Events and uploads:** Admin-only: create events via API; upload decks to new or existing events (file or JSON body). Event IDs namespaced so MTGTop8 and manual events never collide.
- **Scrape duplicate protection:** Upsert or insert-only when persisting scraped decks so re-scraping does not create duplicate rows.
- **In-app DB management:** Admin-only: "Data" or Settings tab to edit/delete events and decks; aliases and settings as today.
- **Local dev with Railway DB:** Copy `DATABASE_URL` from Railway into `.env`, run migrations, start app; avoid destructive ops on shared DB.

This gives you a clear path to escalate the project with a database and run it reliably on Railway with minimal change to the existing analyzer and frontend.