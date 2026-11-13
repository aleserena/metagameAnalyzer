# Single-elimination events — design

Date: 2026-11-13 · Status: draft, awaiting approval

## Intent

Some real events are a pure single-elimination bracket with no Swiss rounds. The examples in prod are
**Hadouken League: DC Temp 1** (`90844`) and **DC Temp 2** (`93708`). Each is the playoff of a two-month league:
the league had 44 / 39 players, and its top 16 played a 16-player knockout bracket. Every deck in the event
is in the bracket.

Today every event is modelled as "N Swiss rounds (N from player count) + an optional Top 8 cut". For these events
that causes two problems:

- The matchups editor forces bracket games into Swiss rows. The stored round numbers end up scrambled: in DC Temp 1
  the winner has three matches stored as round 1 and one as round 3, and the round-of-16 games are spread over rounds 2–4.
- The missing-matchups check expects every deck to play N rounds (4 for 16 players, 6 for 39). A deck knocked out in the
  first round played one match, so nearly every deck shows as incomplete.

The goal: matchups for single-elimination events are entered, stored and checked the way the Top 8 cut works today,
using bracket rounds.

## Goals

- An admin can mark an event as **single elimination** and set its **bracket size**. Both are settings on the event.
- For those events, the matchups editor shows only bracket rows, labelled *Round of 16 / Quarterfinal / Semifinal / Final*.
  These rows work like today's Top 8 section, without a Swiss section.
- Bracket games are stored as rounds `1..log2(bracket_size)`, with no Swiss offset.
- The missing-matchups check expects from each deck the number of matches its rank implies.
- DC Temp 1 and DC Temp 2 are fixed: they get the new settings, and their stored rounds are renumbered to match the bracket.

## Non-goals

- **Swiss events keep a fixed Top 8 cut.** The new bracket size field is only used by single-elimination events.
  Using it to set the cut of a Swiss event (Swiss + Top 16, for example) is possible later, but it is not part of this
  release. *(My call: you chose the two-field design (B) so this stays possible, not to build it now.)*
- Win-rate, matchup and metagame statistics are unchanged. Bracket games already count, and they keep counting. The metagame
  "Top 8" statistics keep using ranks 1–8.
- The public deck-upload link keeps storing matchups without round numbers. Admins (or event-edit link holders) number the
  rounds in the event editor, as they do for Top 8 today.
- The Hadouken import (`api/services/hadouken.py`) is not changed. It keeps Hadouken's own round numbers.
- No bracket visualisation (tree view).

## Anti-goals

- Existing Swiss events must not change at all: they keep the same editor, the same round numbering and the same
  completeness rule.
- The previous release must keep working against the migrated database (additive migration rule).

## Approaches considered

| | Approach | Trade-off |
|---|---|---|
| A | One nullable `bracket_size` field; a value means single elimination | Smallest change, but the field's meaning is implicit. "Swiss + Top 16" would need a second field later |
| **B (chosen)** | `structure` field (`swiss` / `single_elimination`) + `bracket_size` | Explicit. `bracket_size` can later become the cut size of Swiss events. Slightly more to build now |
| — | Infer single elimination from deck ranks | Rejected: you want it set explicitly |

You chose **B**.

## Design

### Data (migration `020`, additive)

- `events.structure` — `String(32)`, nullable. `NULL` or `'swiss'` means Swiss + Top 8 (today's behaviour).
  `'single_elimination'` means a bracket only.
- `events.bracket_size` — `Integer`, nullable. Required when `structure = 'single_elimination'`: a power of two from 2 to 128
  (128 is the largest rank band, `65-128`). Ignored for Swiss events in this release.
- Both fields go into the event dict (`api/db.py` event-to-dict helpers), the event export/import
  (`api/services/event_export.py` / `event_import.py`) and snapshot restore (`api/services/snapshots.py`). Old exports
  and snapshots without the fields restore as `NULL`, which is Swiss.
- Event merge (`api/routers/events.py` preview + apply) carries both fields with the same "prefer keep, fill from remove"
  rule as the other event fields.
- The scraper never sets these fields, and the `scrape_store` update path must not clear them. They are not added to
  `EVENT_MANUAL_FIELDS`, because no scrape writes them.

### Shared rules (backend `api/` + frontend `web/src/lib/matchups.ts`, kept in step)

Let `R = log2(bracket_size)`.

- **Round label** for bracket round `r` (1-based), with `left = bracket_size / 2^(r-1)` players remaining:
  2 → "Final", 4 → "Semifinal", 8 → "Quarterfinal", otherwise "Round of {left}".
- **Expected matches for a deck**, from its normalized rank band (`normalize_rank`). Let `U` be the band's upper bound
  (1, 2, 4, 8, 16, …):
  - `U > bracket_size`: 0 (the deck is outside the bracket)
  - otherwise: `min(R, R - log2(U) + 1)`

  For a 16-player bracket that gives 9-16 → 1, 5-8 → 2, 3-4 → 3, 2 → 4, 1 → 4.
  A deck with no rank or an unparseable rank is expected to have **1** match. *(My call: it is in the bracket, so it
  played at least once.)*
- A **bye** counts as a played round, and a **drop** exempts the deck, as in today's rule.

### Backend

- `api/schemas/events.py` / create body: optional `structure`, `bracket_size`. Validation (shared helper): `structure`
  must be one of the two values, and `single_elimination` requires a valid `bracket_size`. Otherwise respond 422.
- `PUT /api/v1/events/{event_id}`: new optional query params `structure`, `bracket_size`, with the same validation. It
  stays a hand-edit path and keeps the existing change-log entry.
- `POST /api/v1/events` (create): accepts both fields.
- Missing-matchups check (`_decks_missing_matchups`, `list_missing_matchups_for_event`,
  `list_event_ids_with_complete_matchups` in `api/db.py`): replace the single `expected` int with an expected count per deck.
  Swiss events pass `_swiss_rounds_for_players(n)` for every deck (unchanged). Single-elimination events use the rank rule
  above.
- Missing-decks check (`api/db.py` ~L651, "deck count < player_count"): for single-elimination events, compare against
  `bracket_size`, not `player_count`. Otherwise DC Temp 1 (16 decks, 44 players) shows as missing decks.
  *(My call.)*
- Event cache invalidation: these are event fields, so the existing `_load_decks_from_db()` + `_invalidate_events_cache()`
  in the update handler cover it.
- Run `npm run gen:routes` if the route listing changes.

### Frontend

- Types (`web/src/types.ts`): `structure?: 'swiss' | 'single_elimination' | null`, `bracket_size?: number | null` on the event.
- API (`web/src/api.ts`): create/update pass the new fields.
- **Event edit form** (EventDetail) and **create form** (Events page): a "Structure" select (Swiss + Top 8 / Single
  elimination). When single elimination is chosen, a "Bracket size" select (2, 4, 8, 16, 32, 64, 128) appears. The player
  count field stays and keeps meaning the league's real number of players.
- **Matchups editor** (`EventDetail.tsx` + `MatchupsForm.tsx`):
  - Single-elimination events: no Swiss section. One bracket section, always shown (not gated on top-8 rank), with up to `R`
    rows. Each row is labelled by its round (row *i* = round *i*). The deck's expected count from the rank rule is shown as a
    hint. Saving uses `phasesToApiMatchups` with `swissRounds = 0`, which numbers the rows 1..k.
  - Loading uses `apiMatchupsToPhases` with `swissRounds = 0`, so every stored row lands in the bracket section, including
    rows reported against this deck by opponents.
  - Swiss events: unchanged.
- Event detail header: show "Single elimination · 16-player bracket" next to the player count.

### Fixing DC Temp 1 and DC Temp 2

A one-off, idempotent script: `scripts/renumber_single_elim_rounds.py --event-id <id> --bracket-size 16 [--apply] --db-env <env>`.
It does a dry run by default and prints the before → after rounds.

1. Calls `take_snapshot(session, event_id, "renumber single-elimination rounds")` first, in the same session (recovery rule).
2. Sets `structure = 'single_elimination'` and `bracket_size`.
3. For each pair of matchup rows between two decks of the event (both sides are stored; resolve the opponent by
   `opponent_deck_id`, falling back to `opponent_player_id` → that player's deck in the event), the round is the round in which the
   **loser** was eliminated: loser band `U` → round `R - log2(U) + 1`. In a 16-player bracket, a 9-16 loser means round 1
   and a 2 loser means round 4. Both sides get that round.
4. Refuses to change an event when the data contradicts the bracket. Examples: a pair with no clear loser (draw/ID), a deck
   with more matches than its rank allows, or two matches for one deck in the same round. It reports these and changes
   nothing for that event.
5. Writes a `change_log` entry (`actor = change_log.ADMIN`) after commit. Afterwards, restart the API or trigger
   `POST /analyze` so the running process reloads.

I checked prod (read-only): both events fit this rule. Every pair has one win and one loss, and the match counts per rank
are 1/2/3/4/4.

### Tests

- Python: the expected-matches rule (every band, out-of-bracket, no rank); `_decks_missing_matchups` with per-deck
  expectations; create/update validation (422 cases); export/import/snapshot round-trip of the new fields; merge carries them;
  the renumber script's pairing logic, including the refuse-on-contradiction cases (DB tests).
- Vitest: round labels, expected matches, and `apiMatchupsToPhases`/`phasesToApiMatchups` with `swissRounds = 0`.

### Docs

- `CLAUDE.md`: one paragraph on event structure / bracket size and the rank-based completeness rule.
- `docs/API_ROUTES.md`: regenerate.

## Left to the builder

- Exact component structure inside `MatchupsForm.tsx` (a new prop vs a variant).
- Where the shared Python helpers live. `api/helpers.py` or a small `api/brackets.py` both fit; follow the `api/formats.py`
  precedent.
- Copy and placement of the structure/bracket hint in the editor.
