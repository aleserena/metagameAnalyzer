# MTGTop8 Scraper and Metagame Analyzer

Scrapes deck lists from [mtgtop8.com](https://www.mtgtop8.com) filtered by format, time period, and store/event, then provides metagame analysis. Includes a web app for viewing and analyzing the data.

## Installation

```bash
pip install -r requirements.txt
```

## Testing

Run tests before committing to catch regressions.

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

## Web Application

The web app provides a dashboard, metagame analysis, deck browser, player leaderboard, and scrape controls.

### Run the web app

1. **Start the API backend** (from project root):

```bash
python -m uvicorn api.main:app --reload --port 8000
```

2. **Start the frontend** (in another terminal):

```bash
cd web
npm install
npm run dev
```

3. Open http://localhost:5173 in your browser.

The API loads `decks.json` on startup if present. You can also load data via the Scrape page (upload JSON or run a new scrape).

### Admin authentication

Scrape and Settings are available only to an admin user. Set the environment variable **`ADMIN_PASSWORD`** (required for admin features). Optional **`JWT_SECRET`** (defaults to `ADMIN_PASSWORD` if set) is used to sign login tokens.

- **Login**: Open `/login` and enter the admin password. A signed token is stored in the browser and sent with requests to protected endpoints.
- **Scrape tab**: Load/upload data, download export, and run scrapes (admin only).
- **Settings tab**: Manage player aliases and the list of cards excluded by the "Ignore lands" metagame option (admin only).

If `ADMIN_PASSWORD` is not set, admin login is disabled and those tabs are hidden.

### Player aliases (merge duplicate names)

If the same player appears under different names (e.g. "Tomas Pesci" and "Pablo Tomas Pesci"), an admin can merge them in **Settings → Player aliases**: add mappings (alias → canonical). On the Player detail page, similar names are suggested with a "Merge into X" button (merge requires admin login). Aliases are stored in `player_aliases.json` (in `DATA_DIR`). Merged players share stats and deck lists.

## CLI Usage

### Scrape decks

```bash
# Duel Commander, Last 2 Weeks, filter by store "Angers"
python main.py scrape --format EDH --period "Last 2 Weeks" --store "Angers" -o decks.json

# Scrape specific event(s) by ID
python main.py scrape --format EDH --events 80455,80480 -o decks.json

# All Duel Commander events from Last 2 Months (no store filter)
python main.py scrape --format EDH --period "Last 2 Months" -o decks.json
```

### Analyze metagame

```bash
python main.py analyze decks.json -o metagame.json
```

## Supported formats

- EDH (Duel Commander)
- ST (Standard), PI (Pioneer), MO (Modern), LE (Legacy), VI (Vintage)
- PAU (Pauper), cEDH, PREM (Premodern)

## Time periods

- Last 7 Days, Last 2 Weeks, Last 2 Months
- MTGO Last 2 Months, Paper Last 2 Months
- Last Major Events (3 Months), Last 6 Months
- All 2026/2025/2024 Decks, Major Events

## Store filtering

Store and location are embedded in event names as `Event Name @ Store (Location)`. Use `--store` with a substring to filter (e.g. `"Angers"`, `"Le Vizz"`, `"MTGAnjou"`).
