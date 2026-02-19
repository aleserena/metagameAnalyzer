# MTGTop8.com Site Structure Documentation

**Document purpose:** Structured reference for scraping and navigating www.mtgtop8.com

---

## 1. URL Structure for Browsing Formats, Events, Stores

### Base URLs

| Resource | URL Pattern | Example |
|----------|-------------|---------|
| **Homepage** | `https://www.mtgtop8.com` | Main landing with format links |
| **Format** | `https://www.mtgtop8.com/format?f={FORMAT_ID}` | `/format?f=EDH` (Duel Commander) |
| **Event** | `https://www.mtgtop8.com/event?e={EVENT_ID}&f={FORMAT_ID}` | `/event?e=80455&f=EDH` |
| **Deck** | `https://www.mtgtop8.com/event?e={EVENT_ID}&d={DECK_ID}&f={FORMAT_ID}` | `/event?e=80455&d=812268&f=EDH` |
| **Search** | `https://www.mtgtop8.com/search` | Advanced deck search |
| **Archetype** | `https://www.mtgtop8.com/archetype?a={ARCHETYPE_ID}` | `/archetype?a=387` |
| **Player search** | `https://www.mtgtop8.com/search?player={NAME}` | `/search?player=Edmund+Mallari` |
| **Limited format** | `https://www.mtgtop8.com/format_limited` | Different structure (uses `meta_m` for sets) |

### Format IDs (f parameter)

| Format | ID |
|--------|-----|
| Standard | ST |
| Pioneer | PI |
| Modern | MO |
| Legacy | LE |
| Vintage | VI |
| Pauper | PAU |
| cEDH | cEDH |
| Duel Commander | EDH |
| Premodern | PREM |
| Explorer | EXP |
| Historic | HI |
| Alchemy | ALCH |
| Peasant | PEA |
| Block | BL |
| Extended | EX |
| Highlander | HIGH |
| Canadian Highlander | CHL |

### Store/Location

- **No dedicated store URL.** Store and location are embedded in event names.
- Event naming: `{Event Name} @ {Store/Location}`
- Example: `CR PdLL MTGAnjou @ Angers (France)`, `MTGO League` (no store)
- Store filtering requires parsing event names or using the Search page filters.

---

## 2. Filtering by Format, Store, Time Period

### Format Filter

- **Format page:** `/format?f={FORMAT_ID}` shows events for that format.
- **Time period:** Use `meta` parameter on format pages.

### Time Period (meta parameter)

| Period | meta value (example for EDH) |
|--------|------------------------------|
| Last 2 Weeks | 115 |
| Last 2 Months | 121 |
| MTGO Last 2 Months | 306 |
| Paper Last 2 Months | 308 |
| Last 7 Days | 328 |
| Last Major Events (3 Months) | 130 |
| Last 6 Months | 209 |
| All 2026 Decks | 343 |
| All 2025 Decks | 310 |
| All 2024 Decks | 283 |
| Major Events | 196 |
| All Commander decks | 56 |

**Note:** `meta` values are format-specific; same label can map to different IDs per format.

### Search Page Filters (`/search`)

- **Event type** – filter by event
- **Deck** – archetype
- **Player** – player name
- **Format** – Standard, Pioneer, Modern, etc.
- **Level** – Professional, Major, Competitive, Regular
- **Decks must contain** – card filter (Main deck / Sideboard)
- **Period** – From / To dates

### Store Filtering

- No direct store URL parameter.
- Store info is in event names: `Event Name @ Store (Location)`.
- To filter by store: scrape events and filter by event name/location text, or use Search with date range and format.

---

## 3. Deck List Display and Data Per Deck

### Deck Page URL

`/event?e={EVENT_ID}&d={DECK_ID}&f={FORMAT_ID}`

### Deck Metadata

| Field | Source |
|-------|--------|
| Deck name | Title (e.g., "Sultai Changeling Slivers") |
| Player | Link to `/search?player={Name}` |
| Event name | e.g., "CR PdLL MTGAnjou @ Angers (France)" |
| Format | e.g., "Duel Commander" |
| Player count | e.g., "128 players" |
| Date | e.g., "15/02/26" |
| Rank | 1, 2, 3-4, 5-8, 9-16, etc. |
| Main/Sideboard counts | e.g., "MD 60 SB 15" or "MD 99 SB 1" |

### Deck List Structure

- **COMMANDER** – Commander(s) for EDH
- **LANDS** – land count and list
- **CREATURES** – creature count and list
- **INSTANTS and SORC.** – instant/sorcery count and list
- **OTHER SPELLS** – artifacts, enchantments, planeswalkers, etc.

Each card line: `{quantity} {card name}` (e.g., `4 Llanowar Elves`).

### Additional Deck Data

- **Archetype link** – `/archetype?a={ID}` (e.g., "Sultai Aggro decks")
- **Export links** – MTGO, .dec
- **Pricing** – Card Kingdom, TCGplayer, Manatraders, Cardhoarder
- **Visual view** – `?switch=visual` on deck URL

### Event Page (no deck ID)

- Shows all decks in the event with rank, deck name, player.
- Each deck links to `/event?e={EVENT_ID}&d={DECK_ID}&f={FORMAT_ID}`.

---

## 4. Pagination and Navigation

### Format Page Pagination

- **Parameter:** `cp` (current page)
- **Pattern:** `/format?f={FORMAT_ID}&meta={META}&cp={PAGE}`
- **Example:** `/format?f=EDH&meta=115&cp=2`
- **Controls:** Prev, 1, 2, 3, 4, Next
- **Page size:** ~20 events per page ("Events 21 to 40" on page 2)

### Search Page Pagination

- **Controls:** Prev, 1, 2, 3, 4, 5, 6, 7, 8, Next
- **Page size:** ~30 decks per page (from table rows)

### Archetype Page Pagination

- Same `cp` pattern: `/archetype?f=ST&meta=50&a=387&cp=2` (if present)

### Event Page

- No pagination; all decks for the event on one page.

---

## 5. HTML Structure for Scraping

### Tables

| Page | Table content | Use |
|------|---------------|-----|
| Format | Event name, date | Event links, dates |
| Event | Rank, deck name, player | Deck links, players |
| Search | Deck, Player, Format, Event, Level, Rank, Date | Full deck metadata |
| Archetype | Deck, Player, Event, Level, Rank, Date | Archetype deck list |

### Link Patterns

| Pattern | Extract |
|---------|---------|
| `/event?e=(\d+)&f=(\w+)` | Event ID, format |
| `/event?e=(\d+)&d=(\d+)&f=(\w+)` | Event ID, deck ID, format |
| `/search?player=([^&]+)` | Player name |
| `/archetype?a=(\d+)` | Archetype ID |

### Selectors (inferred from structure)

- **Event tables:** Rows with event name + date
- **Deck tables:** Rows with deck name, player, event, rank, date
- **Deck list:** Sections by type (COMMANDER, LANDS, CREATURES, etc.)
- **Card lines:** `{number} {card name}` in each section

### Navigation Links

- Format nav: `/format?f={ID}` for each format
- Meta filters: `/format?f={ID}&meta={META}&a=` for time periods
- Pagination: `/format?f={ID}&meta={META}&cp={N}`

### Data Extraction Notes

1. **Event IDs** – From event links: `e=80455`
2. **Deck IDs** – From deck links: `d=812268`
3. **Store/location** – Parse event name after `@`
4. **Dates** – DD/MM/YY
5. **Ranks** – 1, 2, 3-4, 5-8, 9-16, etc.

---

## 6. Scraping Recommendations

### Crawl Order

1. Start at `/format?f={FORMAT}&meta={META}` for desired format and period
2. Follow pagination with `cp` to get all event links
3. For each event: `/event?e={EVENT_ID}&f={FORMAT}`
4. For each deck: `/event?e={EVENT_ID}&d={DECK_ID}&f={FORMAT}`

### Rate Limiting

- Add delays between requests
- Respect `robots.txt` if present

### Store-Specific Scraping

- Scrape format page for events
- Filter events by name containing store/location
- Or use Search with date range and parse results

### Robustness

- `meta` values differ by format; maintain a mapping or discover from page links
- Handle encoding (e.g., `R�mi` → `Rémi`)
- Commander format uses COMMANDER section; non-Commander formats do not

---

## Appendix: Sample meta Values by Format

**Duel Commander (EDH):**
- Last 2 Weeks: 115
- Last 2 Months: 121
- Last 7 Days: 328
- All 2026: 343

**Standard (ST):**
- Last 2 Weeks: 50
- Last 2 Months: 52
- All 2026: 341

**Limited:**
- Uses `meta_m` for set (e.g., 96 = Foundations)
- Uses `meta` for event type (97 = Premier Draft, 98 = Traditional Draft)
