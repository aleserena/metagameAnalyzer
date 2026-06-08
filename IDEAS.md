# IDEAS.md

Feature ideas and possible improvements for the MTG Metagame Analyzer.

---

## Data & Analysis

### Metagame Health Score
A single aggregated metric (0–100) per format answering "is this format healthy?". Factors: archetype diversity, top-card play-rate concentration, win-rate parity across archetypes, trend velocity. Surfaced on the dashboard as a quick status indicator.

### Format Volatility / Churn Metric
Track week-over-week metagame instability: percentage of archetypes that dropped in or out, average rank delta per archetype, and a "stability index". Helps identify when a format is naturally evolving vs. when a ban is needed. Endpoint: `GET /api/v1/metagame/churn?weeks=4`.

### Card Usage Heatmap by Archetype
Extend the archetype view to show "core" vs "flex" cards: inclusion rate (% of decks), main vs sideboard split, and cards that rotate in/out week-to-week. Helps brewers understand which slots are fixed and which are meta-dependent.

### Meta Forecast
Predict the likely archetype distribution for the next event based on recent trend trajectories. Returns archetype confidence intervals. Endpoint: `GET /api/v1/metagame/forecast?events_ahead=1`. Long-term stretch goal.

---

## Player Tools

### Head-to-Head Player Statistics
Win/loss/draw record between two specific players, which decks each piloted in those match-ups, and the most frequent pairings. Useful for tournament preparation. Endpoint: `GET /api/v1/players/{player}/vs/{opponent}`.

### Sideboard Recommendations
Given a deck, suggest sideboard cards based on what decks with strong records against the expected field play. Endpoint: `GET /api/v1/matchups/{deck_id}/recommendations`. Requires matchup data to be populated for the relevant format.

---

## Commander / EDH

### Commander Synergy View
For a given commander: co-commanders that appear in top-placing lists, typical shell composition (% ramp, % draw, % interaction, % threats), and flex slots. Endpoint: `GET /api/v1/commanders/{name}/synergies`.

---

## Quality of Life

### Card Rotation / Legality Checker
Flag cards in a decklist that are illegal or rotating soon in the selected format. Leverage existing Scryfall integration for legality data and suggest replacements. Endpoint: `GET /api/v1/decks/{deck_id}/rotation-check`.
