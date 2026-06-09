# IDEAS.md

Feature ideas and possible improvements for the MTG Metagame Analyzer.

---

## Data & Analysis

### Metagame Health Score
A single aggregated metric (0–100) per format answering "is this format healthy?".

**Factors (all four equally weighted):**
- Archetype diversity — how many viable archetypes exist (fewer = less healthy)
- Top-card concentration — % of decks running the same 1–2 cards (high = format solved)
- Win-rate parity — how balanced win rates are across the top archetypes
- Meta shift rate — is the meta still evolving? Use churn data as input

**UI:** Surfaced on the dashboard as a quick status card per format. Clicking opens the format detail page with a breakdown of each factor's contribution to the score.

**API:** `GET /api/v1/metagame/health?format=EDH`

**Implementation notes:**
- All four factors are computable from `_decks` and the `MatchupRow` table — no new data sources needed.
- Archetype diversity: count distinct archetypes with play rate above a threshold (e.g. >2%) — normalize to 0–100.
- Top-card concentration: for the top 5 most-played cards, compute average inclusion rate across all decks — higher = less healthy.
- Win-rate parity: compute standard deviation of archetype win rates from `MatchupRow` data — lower stddev = more balanced = healthier.
- Meta shift rate: reuse the stability index from the Churn feature as this factor's input.
- Implement as a pure function taking format-filtered deck/matchup data; call the churn endpoint logic internally.

---

### Format Volatility / Churn Metric ⭐ Priority
Measures week-over-week metagame instability for a given format and configurable time window.

**What it measures:**
- Archetypes entering / leaving the top N (user-configurable N)
- Average rank delta per archetype between periods
- Most volatile cards — cards whose play rate changed most between periods
- Overall stability index (0–100, higher = more stable)

**Time slicing:** Configurable window via `?weeks=N` query param.

**UI:** Stability index summary card on the dashboard (alongside existing format stats). Clicking opens the full breakdown on the format detail page: rank delta chart, archetype entry/exit table, and most volatile cards list.

**API:** `GET /api/v1/metagame/churn?format=EDH&weeks=4&top_n=8`

**Implementation notes:**
- All data is available in the `_decks` in-memory list in `api/main.py`. Each deck dict has `archetype`, `format_id`, `event_id`, and `date` (DD/MM/YY string).
- Date parsing: use the existing `_yymmdd_to_ordinal()` helper in `api/main.py` to convert DD/MM/YY strings to ordinals for comparison.
- Algorithm: split the `_decks` list into two time windows (current period vs previous period), compute archetype play-rate (count/total) for each window, then diff — rank delta, entry/exit, and card-level changes across windows.
- Most volatile cards requires per-archetype card data (mainboard counts), which is available in each deck's `mainboard` list in `_decks`.
- The stability index (0–100) can be computed as `100 - clamp(churn_score * k, 0, 100)` where `churn_score` is a weighted sum of archetype entry/exit rate and average rank delta.
- No new DB table needed — all computation is in-memory at request time. Cache the result with a short TTL if performance is a concern.

---

### Card Usage Heatmap by Archetype
Extends the archetype view to reveal which cards are "core" (always in) vs "flex" (meta-dependent).

**Content:**
- Individual card stats: inclusion rate (% of decks), main vs sideboard split, week-over-week change
- Category summary rolled up from individual cards: % ramp, % removal, % draw, % threats, etc.
- Both levels shown together — individual cards with their stats, grouped into categories

**UI:** New tab or expandable section on the existing archetype detail page.

**API:** `GET /api/v1/archetypes/{name}/card-heatmap?format=EDH`

**Implementation notes:**
- Card data per deck is available in `_decks` — each deck dict has `mainboard` (list of `{name, qty}`) and `sideboard`.
- Inclusion rate: for a given archetype, count how many decks include each card / total decks for that archetype.
- Card categories (ramp, removal, draw, etc.) are not currently tagged in the data. Options: (a) use Scryfall `type_line` + oracle text keywords to auto-classify, (b) maintain a manual mapping. Auto-classify is more scalable; Scryfall data is already cached via `card_lookup.py`.
- Week-over-week change: split decks by date into two windows and diff inclusion rates — same approach as the Churn metric.

---

## Player Tools

### Head-to-Head Player Statistics ⭐ Priority
Win/loss/draw record between two specific players, using the existing round-by-round match result data already in the DB.

**Scope:** Per-format breakdown + combined total across all formats.

**Content (new "Rivals" section on the player profile page):**
- Top rivals ranked by number of matches played
- W/L/D record vs each opponent, by format and combined
- Deck pairings — which deck each player piloted in each encounter
- Win-rate trend over time across events

**UI:** New section/tab on the existing player profile. Symmetric — Player B's profile shows the same encounters from their perspective.

**API:**
- `GET /api/v1/players/{player_id}/head-to-head` — all opponents with aggregated stats
- `GET /api/v1/players/{player_id}/head-to-head/{opponent_id}` — full per-match detail

**Implementation notes:**
- `MatchupRow` (`api/db.py:107`) already has everything needed: `deck_id`, `opponent_player_id`, `opponent_archetype`, `result` (`win|loss|draw|intentional_draw`), `round`. Both sides of each match are already stored (the inverse is written automatically by `upsert_matchups_for_deck`).
- To get all H2H records for `player_id=X`: join `MatchupRow` with `DeckRow` on `MatchupRow.deck_id == DeckRow.deck_id` and filter `DeckRow.player_id == X` (this finds all matches where X was the reporting player). The inverse (where X was the opponent) is already stored as its own row, so one direction is enough.
- Format per match: join through `DeckRow.event_id` → `EventRow` or read `format_id` directly from `DeckRow`.
- Deck pairing per encounter: `MatchupRow.deck_id` (player's deck) and `MatchupRow.opponent_deck_id` (opponent's deck) — both are deck IDs that can be looked up for archetype/name.
- Add the new endpoint to `api/main.py`. Add response schema to `api/schemas/matchups.py` or `api/schemas/players.py`.
- Player profile frontend page: look for the player detail component in `web/src/pages/`.

---

## Commander / EDH

### Commander Synergy View
For a given commander: shows both the archetype skeleton for new players and flex/tech cards for experienced players.

**Content:**
- Shell composition — typical % breakdown by role: ramp, draw, interaction, threats, utility
- Co-commanders that appear most in top-placing lists
- Tech cards — underplayed cards that appear in top-placing lists but not average lists
- Flex slots — cards that rotate in/out across different builds of the same commander

**API:** `GET /api/v1/commanders/{name}/synergies`

**Implementation notes:**
- Commander decks in `_decks` have a `commanders` list (one or two cards). Filter by `format_id` in `['EDH', 'cEDH']` and by the requested commander name appearing in `commanders`.
- Co-commanders: count the frequency of each partner/co-commander across matching decks.
- Tech cards: compare inclusion rate in top-placing decks (rank 1–4 in their event) vs all decks — cards with a large positive delta are "tech".
- Flex slots: cards with inclusion rate between ~20–70% (neither core nor absent) — these are the variable slots.
- Shell composition by role: same auto-classification approach as the Card Heatmap (Scryfall `type_line` + oracle text keywords).

---

## Quality of Life

### Deck & Card Prices
Show the cost of a deck and each of its cards directly on the deck page, with user-selectable price source.

**Price sources (user picks one):** Scryfall, TCGPlayer, CardMarket, CardKingdom.

**Currencies shown:** USD, EUR, MTGO tix, and foil variants alongside non-foil.

**Caching:** Prices fetched and stored once per day to avoid rate limits — no live fetching per request.

**Content on the deck page:**
- Deck total price prominently in the header/summary
- Per-card price next to each card in the mainboard and sideboard list
- Price breakdown by card type (how much of the budget goes to lands, creatures, instants, etc.)
- Price history chart — how the deck's total cost has changed over time as card prices shift
- Budget alternatives — for cards above a configurable price threshold, suggest cheaper replacements played in similar decks

**Scope:** Deck page only (not surfaced in the deck browser or leaderboard).

**API:**
- `GET /api/v1/decks/{deck_id}/prices?source=scryfall&currency=usd` — full price breakdown for a deck
- `GET /api/v1/cards/{card_name}/prices?source=scryfall` — price for a single card across all currencies

**Implementation notes:**
- Scryfall is the only source already integrated (`src/mtgtop8/card_lookup.py`). The raw Scryfall card object returned by the API contains a `prices` dict: `{"usd": "1.23", "usd_foil": "4.56", "eur": "0.98", "eur_foil": "2.34", "tix": "0.05"}` — values are strings or `null`.
- Currently `_build_entry()` in `card_lookup.py` discards this field. Adding `"prices": card.get("prices", {})` to the returned dict is the minimal change to expose prices through the existing Scryfall cache.
- The Scryfall cache file is `.scryfall_cache.json` — it has no TTL logic today. For daily price refresh, add a `prices_fetched_at` timestamp to each cache entry and re-fetch if stale.
- TCGPlayer, CardMarket, and CardKingdom each require a separate API integration (no existing code). TCGPlayer requires OAuth; CardMarket has a REST API; CardKingdom has no public API (would need scraping).
- For the price history chart, prices would need to be persisted to the DB (new table) with a timestamp — the Scryfall cache alone is not enough since it's overwritten on each fetch.

---

### Matchups Matrix — Mobile & Touch Improvements
Make the matchups matrix usable on phones and small screens. Two-phase approach:

**Phase 1 — Touch panning (easy win):**
- Set `touch-action: pan-x pan-y` explicitly on the scroll container so the browser handles panning natively and smoothly
- Ensure `-webkit-overflow-scrolling: touch` is set for momentum scrolling on iOS
- Keep the sticky left column and sticky header row working correctly during touch scroll

**Phase 2 — Pinch-to-zoom:**
- Detect pinch gestures on the matrix wrapper and apply a CSS `transform: scale()` to the table
- Zoom range: 0.5× (zoom out to see the full matrix) to 2× (zoom in on a specific area)
- Reset: double-tap gesture snaps back to 1×; a floating reset button also appears whenever the user is not at 1× scale
- Zoom state is local to the component (not persisted)

**Out of scope for this iteration:** focus/drill-down mode, auto-switching to list view, virtualized rendering.

**Implementation notes:**
- File: `web/src/pages/Matchups.tsx`
- The archetype matrix scroll wrapper is `<div className="card" style={{ overflow: 'auto' }}>` at line ~889; the players matrix is at line ~1210. Both need the same treatment.
- The inner `<div style={{ minWidth: 400 }}>` wraps the `<table>` — apply `transform: scale()` to this div, not the card, so the card border stays stable.
- `style.css` already sets `-webkit-overflow-scrolling: touch` on `.table-wrap` (line 720) but the matrix uses `.card` — add the same property to the card's inline style or extend `.card` in CSS.
- For pinch-to-zoom: use `onPointerDown/onPointerMove/onPointerUp` (pointer events, not Touch events) to track two simultaneous touches. No gesture library is used elsewhere in the project — implement with `useRef` for pointer tracking and `useState` for scale.
- Double-tap detection: track last tap timestamp with `useRef`; if two taps within ~300ms on the same element, reset scale to 1.
- The sticky left column (`position: 'sticky', left: 0`) breaks under `transform: scale()` on the parent — work around this by applying scale to an intermediate wrapper between the `.card` overflow container and the `<table>`, not on the overflow container itself.

---

