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

### Player aliases (merge duplicate names)

If the same player appears under different names (e.g. "Tomas Pesci" and "Pablo Tomas Pesci"), you can merge them:

1. **Players page** → Expand "Manage player aliases" at the bottom. Add mappings (alias → canonical).
2. **Player detail page** → When viewing a player, similar names are suggested with a "Merge into X" button.

Aliases are stored in `player_aliases.json` in the project root. Merged players share stats and deck lists.

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
