# MTGTop8 Scraper and Metagame Analyzer

Scrapes deck lists from [mtgtop8.com](https://www.mtgtop8.com) filtered by format, time period, and store/event, then provides metagame analysis. Includes a web app for viewing and analyzing the data.

## Installation

```bash
pip install -r requirements.txt
```

## Testing

Run tests before committing to catch regressions. **Husky git hooks** are configured: **pre-commit** runs fast lint (`npm run lint`), and **pre-push** runs the web build plus both test suites (`npm run build`, `npm run test`, `npm run test:py`) and the route-doc check.

**One-time setup (enable the hooks):** from the project root run `npm install`. This installs Husky and registers the hooks. Use `git commit --no-verify` / `git push --no-verify` to bypass them while iterating.

**Backend (pytest):**

```bash
pytest tests/ -v
# With coverage:
pytest tests/ --cov=src --cov=api
```

**Frontend (Vitest + React Testing Library):**

```bash
cd web
npm install
npm test
```

**Coverage (from project root):**

- Backend: `npm run test:py:coverage` (or `pytest tests/ --cov=src --cov=api --cov-report=term-missing`)
- Frontend: `npm run test:coverage` (or `cd web && npm run test:coverage`)

## Web Application

The web app provides a dashboard, metagame analysis (including health score and churn/volatility), archetype and matchup matrices, deck browser with compare view, commander pages, player leaderboard with head-to-head stats, and scrape controls.

### Run the web app

1. **Start the API backend** (from project root):

```bash
python3 -m uvicorn api.main:app --reload --port 8000
```

2. **Start the frontend** (in another terminal):

```bash
cd web
npm install
npm run dev
```

3. Open http://localhost:5173 in your browser.

The API loads decks from the PostgreSQL database on startup. You can load data via the Scrape page (upload JSON or run a new scrape) or via `POST /api/v1/load`.

### Admin authentication

Scrape and Settings are available only to an admin user. Set the environment variable **`ADMIN_PASSWORD`** (required for admin features). Optional **`JWT_SECRET`** (defaults to `ADMIN_PASSWORD` if set) is used to sign login tokens.

- **Login**: Open `/login` and enter the admin password. A signed token is stored in the browser and sent with requests to protected endpoints.
- **Scrape tab**: Load/upload data, download export, and run scrapes (admin only).
- **Settings tab**: Manage player aliases and the list of cards excluded by the "Ignore lands" metagame option (admin only).

If `ADMIN_PASSWORD` is not set, admin login is disabled and those tabs are hidden.

### Database and Railway

**PostgreSQL is required.** The app no longer supports JSON-only or in-memory storage. Use a PostgreSQL database (e.g. on [Railway](https://railway.app)); the API persists decks, events, and all data in the database.

#### How to connect the database and run migrations

1. **Get the connection URL**
   - **Railway:** In the project dashboard, open the PostgreSQL service → **Variables** (or **Connect**). Copy **`DATABASE_URL`** (or build it from `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`).
   - **Local Postgres:** Use e.g. `postgresql://user:password@localhost:5432/your_db`.

2. **Put the URL in `.env`**  
   In the project root, create or edit `.env` (do not commit it; it’s in `.gitignore`) and add:
   ```env
   DATABASE_URL=postgresql://user:password@host:port/database
   ```
   Replace with your real URL. Railway often gives `postgres://`; the app accepts that and converts it to `postgresql://` internally.

3. **Install dependencies and run migrations**  
   From the project root:
   ```bash
   pip install -r requirements.txt
   python3 -m alembic upgrade head
   ```
   The app and Alembic load `.env` automatically, so `DATABASE_URL` is read from that file.

4. **Start the API**  
   As usual: `python3 -m uvicorn api.main:app --reload --port 8000`. The API will connect to the database and load decks/aliases from it.

- Decks and events are stored in PostgreSQL. Scrapes upsert by deck ID (no duplicates on re-scrape). Manual events and deck uploads use separate ID ranges from MTGTop8.
- **Data tab** (admin): Create events, upload decks to an event, edit/delete events, delete decks.

If you use the Railway DB from your machine, avoid destructive operations (e.g. “Clear decks”) unless you mean to change that shared database.

#### Email setup (Brevo)

To send **missing-deck links** and **event feedback links** by email (admin-only, from the Event detail page), configure [Brevo](https://www.brevo.com) (ex-Sendinblue).

1. **Create a Brevo account** at [brevo.com](https://www.brevo.com) and log in.
2. **Get credentials:** In Brevo → **Settings → SMTP & API** you can use either:
   - **SMTP:** Note the server (`smtp-relay.brevo.com`), port (587), and create an SMTP key. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM` (verified sender) in `.env`.
   - **API:** Copy an API key and set `BREVO_API_KEY` and `SMTP_FROM` in `.env`.
3. **Documented in `.env.example`:** See the "Email (Brevo)" section for all variables. If none are set, "Email missing deck links" and "Email event feedback links" return 503.
4. **Optional (deliverability):** In Brevo, add and verify your domain and the suggested SPF/DKIM DNS records so messages are less likely to land in spam.

For local testing without sending to real addresses, you can point the same SMTP vars to [Mailtrap](https://mailtrap.io) or use a test Brevo sender.

#### Development: dev / staging / prod databases

To switch between dev, staging, and prod DBs without editing `.env` each time:

1. **Create one env file per target** in the project root (do not commit; they're in `.gitignore`):
   - `.env.dev` — local or dev DB
   - `.env.staging` — staging DB
   - `.env.prod` — production DB  
   Each file has the same format as `.env` (e.g. `DATABASE_URL=...`, `ADMIN_PASSWORD=...`). Copy from `.env.example` if needed.

2. **Run the API against a given env:**
   ```bash
   python3 scripts/run_api.py dev      # uses .env.dev
   python3 scripts/run_api.py staging  # uses .env.staging
   python3 scripts/run_api.py prod     # uses .env.prod
   ```
   Extra args are passed to uvicorn (e.g. `python3 scripts/run_api.py dev --reload`).

3. **Run Alembic against a given env:**
   ```bash
   python3 scripts/run_alembic.py dev upgrade head
   python3 scripts/run_alembic.py staging current
   python3 scripts/run_alembic.py prod revision --autogenerate -m "add column"
   ```

You can also set `DB_ENV=dev` (or `staging` / `prod`) and run `alembic` or `uvicorn` as usual; the app and Alembic will load `.env.dev` (or `.env.staging` / `.env.prod`) when `DB_ENV` is set.

### Player aliases (merge duplicate names)

If the same player appears under different names (e.g. "Tomas Pesci" and "Pablo Tomas Pesci"), an admin can merge them in **Settings → Player aliases**: add mappings (alias → canonical). On the Player detail page, similar names are suggested with a "Merge into X" button (merge requires admin login). Aliases are stored in the database (with `player_aliases.json` in `DATA_DIR` as a fallback when the DB is unavailable). Merged players share stats and deck lists.

## CLI Usage

### Scrape decks

```bash
# Duel Commander, Last 2 Weeks, filter by store "Angers"
python3 main.py scrape --format EDH --period "Last 2 Weeks" --store "Angers" -o decks.json

# Scrape specific event(s) by ID
python3 main.py scrape --format EDH --events 80455,80480 -o decks.json

# All Duel Commander events from Last 2 Months (no store filter)
python3 main.py scrape --format EDH --period "Last 2 Months" -o decks.json
```

### Analyze metagame

```bash
python3 main.py analyze decks.json -o metagame.json
```

## Supported formats

- EDH (Duel Commander)
- ST (Standard), PI (Pioneer), MO (Modern), LE (Legacy), VI (Vintage)
- PAU (Pauper), cEDH, PREM (Premodern)
- EXP (Explorer), HI (Historic), ALCH (Alchemy), PEA (Peasant)
- BL (Block), EX (Extended), HIGH (Highlander), CHL (Canadian Highlander)

## Time periods

- Last 7 Days, Last 2 Weeks, Last 2 Months
- MTGO Last 2 Months, Paper Last 2 Months
- Last Major Events (3 Months), Last 6 Months
- All 2026/2025/2024/2023 Decks, Major Events, All Commander decks

Note: period → mtgtop8 meta-ID mappings are defined per format in `src/mtgtop8/config.py` (complete for EDH/cEDH; only a few periods are mapped for Standard).

## Store filtering

Store and location are embedded in event names as `Event Name @ Store (Location)`. Use `--store` with a substring to filter (e.g. `"Angers"`, `"Le Vizz"`, `"MTGAnjou"`).
