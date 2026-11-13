# Single-Elimination Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Events can be marked single elimination with a bracket size. Their matchups are entered as bracket rounds,
stored as rounds `1..log2(size)`, and checked against the rank-implied match count. A script fixes the two existing
DC Temp events.

**Architecture:** A pure rules module (`api/brackets.py`, mirrored in `web/src/lib/matchups.ts`) holds the bracket
maths. Two nullable event columns (`structure`, `bracket_size`) flow through the event dict, create/update/merge,
export/import and snapshots. The completeness checks switch from one expected count per event to one per deck.
The frontend reuses the Top 8 machinery with `swissRounds = 0`.

**Tech Stack:** FastAPI, SQLAlchemy 2.1 + Alembic (Postgres), pytest; React + TypeScript + Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-13-single-elimination-events-design.md`

## Global Constraints

- Migration is additive only: two nullable columns, no backfill, no drops (the previous release must keep working).
- `structure` values: `'swiss'` (or NULL, meaning Swiss) and `'single_elimination'`. `bracket_size` is one of `2, 4, 8, 16, 32, 64, 128`. It is required for single elimination and stored as NULL for Swiss.
- Event dicts and `EventResponse` always expose `structure` (`'swiss'` when NULL) and `bracket_size` (`null` for Swiss).
- Existing Swiss events behave exactly as today: same editor, same round numbers, same completeness rule.
- Use `python3`. Any handler that mutates an event calls `change_log.log(...)` after commit. A bulk overwrite of an event's matchups calls `take_snapshot(...)` first, in the same session.
- Shared helpers: rank bands come from `normalize_rank` (`src/mtgtop8/analyzer.py`), and win/loss from `api/results.py`. Don't re-inline them.
- Commit each task directly on `staging` (no feature branch). Pre-commit runs `npm run lint`, which must pass.
- No new styling system: inline styles / existing classes only.

## Review Focus

1. **Switching an event back to Swiss:** `bracket_size` is cleared, and the editor shows Swiss + Top 8 again. Stored rounds are left alone. → Task 3 test `test_update_event_back_to_swiss_clears_bracket_size`.
2. **Decks ranked outside the bracket** (e.g. `17-32` in a 16 bracket, or extra league decks) are never flagged as missing matchups. → Task 4 test `test_single_elim_outside_bracket_not_missing`.
3. **Rows saved through the public upload link** (round `null`) on a single-elimination event land in the bracket section, in order. → Task 6 test `apiMatchupsToPhases puts null-round rows in bracket order when swissRounds is 0`.
4. **A first-round bye in a bracket** is saved with a blank opponent and counts as a played round. → Task 6 test `phasesToApiMatchups blanks bye opponent in the cut section`. Task 4 test `test_single_elim_bye_counts_as_match`.
5. **Running the renumber script twice:** the second run plans zero changes and writes nothing. → Task 5 test `test_renumber_is_idempotent`.

---

### Task 1: Bracket rules module (Python)

**Files:**
- Create: `api/brackets.py`
- Test: `tests/test_brackets.py`

**Interfaces:**
- Produces:
  - `STRUCTURE_SWISS = "swiss"`, `STRUCTURE_SINGLE_ELIM = "single_elimination"`, `VALID_BRACKET_SIZES = (2, 4, 8, 16, 32, 64, 128)`
  - `is_single_elimination(structure: str | None) -> bool`
  - `validate_structure(structure: str | None, bracket_size: int | None) -> tuple[str, int | None]`: returns the normalized `(structure, bracket_size)`. `None`/`""` structure → `"swiss"`. Swiss always returns `bracket_size=None`. Raises `ValueError` (message names the bad value) for an unknown structure, or for single elimination without a valid size.
  - `bracket_rounds(bracket_size: int) -> int`: `log2(size)`.
  - `rank_band_upper(rank: str | None) -> int | None`: the upper bound of `normalize_rank(rank)` (`"1"→1, "2"→2, "3-4"→4, "5-8"→8, "9-16"→16, …`), `None` when the band is `""`.
  - `expected_matches_for_rank(rank: str | None, bracket_size: int) -> int`
  - `elimination_round(rank: str | None, bracket_size: int) -> int | None`: the round the deck lost in. `None` for rank 1, unknown rank, or outside the bracket.
  - `round_label(round_no: int, bracket_size: int) -> str`

- [ ] **Step 1: Write the failing tests** in `tests/test_brackets.py` (no DB):

```python
def test_validate_structure():
    assert validate_structure(None, None) == ("swiss", None)
    assert validate_structure("swiss", 16) == ("swiss", None)
    assert validate_structure("single_elimination", 16) == ("single_elimination", 16)
    for bad in [("single_elimination", None), ("single_elimination", 12), ("single_elimination", 256), ("league", None)]:
        with pytest.raises(ValueError):
            validate_structure(*bad)

def test_expected_matches_16():
    assert [expected_matches_for_rank(r, 16) for r in ["1", "2", "3-4", "5-8", "9-16", "17-32", "", "7"]] == [4, 4, 3, 2, 1, 0, 1, 2]

def test_expected_matches_8():
    assert [expected_matches_for_rank(r, 8) for r in ["1", "2", "3-4", "5-8", "9-16"]] == [3, 3, 2, 1, 0]

def test_elimination_round_16():
    assert [elimination_round(r, 16) for r in ["1", "2", "3-4", "5-8", "9-16", "17-32", ""]] == [None, 4, 3, 2, 1, None, None]

def test_round_label():
    assert [round_label(r, 16) for r in (1, 2, 3, 4)] == ["Round of 16", "Quarterfinal", "Semifinal", "Final"]
    assert round_label(1, 32) == "Round of 32"
    assert round_label(1, 2) == "Final"
```

- [ ] **Step 2: Run them to verify they fail.** Run `python3 -m pytest tests/test_brackets.py -v`. Expected: ImportError / FAIL.
- [ ] **Step 3: Implement `api/brackets.py`.** Rules: `R = bracket_rounds(size)`; for band upper `U`: `U > size → 0`, unknown → `1`, else `min(R, R - log2(U) + 1)`. `elimination_round`: `None` when `U` is None, `U == 1`, or `U > size`; else `R - log2(U) + 1`. `round_label`: `left = size >> (round_no - 1)`, 2 → "Final", 4 → "Semifinal", 8 → "Quarterfinal", else `f"Round of {left}"`.
- [ ] **Step 4: Run the tests.** `python3 -m pytest tests/test_brackets.py -v`. Expected: PASS.
- [ ] **Step 5: Commit.** `git add api/brackets.py tests/test_brackets.py && git commit -m "feat(brackets): single-elimination bracket rules"`

---

### Task 2: Event columns, model and DB helpers

**Files:**
- Create: `alembic/versions/020_event_structure_bracket_size.py` (revision `"020"`, down `"019"`, docstring states it is additive)
- Modify: `api/db.py`: `EventRow` (~L78), `event_row_to_dict` (~L618), `create_event` (~L774), `update_event` (~L808)
- Modify: `api/schemas/events.py`: `EventResponse`, `CreateEventBody`
- Test: `tests/test_db_events.py`

**Interfaces:**
- Consumes: Task 1 constants.
- Produces:
  - `EventRow.structure = Column(String(32), nullable=True)`, `EventRow.bracket_size = Column(Integer, nullable=True)`
  - `event_row_to_dict(row)` adds `"structure": row.structure or "swiss"`, `"bracket_size": row.bracket_size if single elim else None`
  - `create_event(..., structure: str | None = None, bracket_size: int | None = None)`: stores the values as given (callers validate).
  - `update_event(..., structure: str | None = None, bracket_size: int | None = None)`: when `structure is not None`, sets both `row.structure = structure` and `row.bracket_size = bracket_size`. When `structure is None`, both are left alone. Not added to `EVENT_MANUAL_FIELDS`.
  - `EventResponse.structure: str = "swiss"`, `EventResponse.bracket_size: int | None = None`. Same two fields with the same defaults on `CreateEventBody`.

- [ ] **Step 1: Write the failing DB tests** in `tests/test_db_events.py`:
  - `test_event_structure_defaults_to_swiss`: `create_event(...)` without the new args → `event_row_to_dict(row)["structure"] == "swiss"` and `["bracket_size"] is None`.
  - `test_update_event_sets_structure`: `update_event(session, eid, structure="single_elimination", bracket_size=16)` → dict has `("single_elimination", 16)`. A following `update_event(session, eid, event_name="X")` leaves both unchanged.
- [ ] **Step 2: Run them to verify they fail.** `python3 -m pytest tests/test_db_events.py -v` (needs `TEST_DATABASE_URL`). Expected: FAIL / TypeError.
- [ ] **Step 3: Write migration 020** (`op.add_column("events", sa.Column("structure", sa.String(32), nullable=True))` and the same for `bracket_size` as `sa.Integer()`; the downgrade drops both). Then update the model, the dict, `create_event`, `update_event` and the schemas as in Interfaces.
- [ ] **Step 4: Run the tests.** `python3 -m pytest tests/test_db_events.py tests/test_db_matchups.py -v`. Expected: PASS (the tests migrate the DB to head at startup).
- [ ] **Step 5: Commit.** `git commit -m "feat(events): structure and bracket_size columns"`

---

### Task 3: Create/update/merge endpoints, export/import, snapshots

**Files:**
- Modify: `api/routers/events.py`: `create_event` (~L97), `update_event_endpoint` (~L482), `merge_preview` (~L340 `merged_preview`), `merge_events` (~L722 `update_event` call)
- Modify: `api/services/event_import.py` (~L18 `create_event` call)
- Modify: `api/services/snapshots.py` (~L238, restore)
- Test: `tests/test_api.py` (or the existing events-endpoint test file it uses), `tests/test_event_import.py`, `tests/test_snapshots.py`

**Interfaces:**
- Consumes: `validate_structure` (Task 1); `create_event`/`update_event` kwargs and `EventResponse` fields (Task 2).
- Produces:
  - `POST /api/v1/events` accepts `structure`, `bracket_size`. A `ValueError` from `validate_structure` → **422**.
  - `PUT /api/v1/events/{event_id}` takes new query params `structure: str | None`, `bracket_size: int | None`. If either is sent: `validate_structure(structure if sent else row.structure, bracket_size if sent else row.bracket_size)`, and pass the result to `update_event`. Invalid → **422**. Existing change-log entry unchanged.
  - `_merge_structure(keep_row, remove_row) -> tuple[str, int | None]` in `api/routers/events.py`: keep's values if keep is single elimination, else remove's if remove is, else `("swiss", None)`. Used in `merged_preview` (keys `structure`, `bracket_size`) and passed to `update_event` in `merge_events`.
  - Import: `create_event(..., *validate_structure(ev.structure, ev.bracket_size))`. Invalid → `ValueError` (existing 400 path).
  - Snapshot restore: `row.structure = event.get("structure") or None`, `row.bracket_size = event.get("bracket_size")`.

- [ ] **Step 1: Write the failing tests:**
  - `test_create_event_single_elim` → 200, response `structure == "single_elimination"`, `bracket_size == 16`. `test_create_event_single_elim_without_size_422` → 422.
  - `test_update_event_structure_query_params`: PUT `?structure=single_elimination&bracket_size=8` → GET shows `(single_elimination, 8)`. PUT `?bracket_size=12` → 422.
  - `test_update_event_back_to_swiss_clears_bracket_size` *(Review Focus 1)*: from `(single_elimination, 16)`, PUT `?structure=swiss` → `("swiss", None)`. The event's stored matchup rounds are unchanged.
  - `test_merge_keeps_single_elimination`: keep is Swiss, remove is `(single_elimination, 16)` → after merge, the kept event is `(single_elimination, 16)`.
  - `test_export_import_round_trips_structure` and `test_snapshot_restore_round_trips_structure`. Also: an old payload without the keys restores as `("swiss", None)`.
- [ ] **Step 2: Run them to verify they fail.** `python3 -m pytest tests/test_api.py tests/test_event_import.py tests/test_snapshots.py -k "structure or single_elim or swiss" -v`. Expected: FAIL.
- [ ] **Step 3: Implement** as in Interfaces.
- [ ] **Step 4: Run the tests**, then `npm run gen:routes` (commit `docs/API_ROUTES.md` if it changed). Run `python3 -m pytest tests/test_api.py tests/test_event_import.py tests/test_snapshots.py -v`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(events): set structure and bracket size on create, edit, merge, import and restore"`

---

### Task 4: Structure-aware completeness checks

**Files:**
- Modify: `api/db.py`: `_decks_missing_matchups` (~L1447), `list_missing_matchups_for_event` (~L1504), `list_event_ids_with_complete_matchups` (~L669), `list_event_ids_with_missing_decks` (~L650)
- Test: `tests/test_db_matchups.py`

**Interfaces:**
- Consumes: `is_single_elimination`, `expected_matches_for_rank` (Task 1).
- Produces:
  - `_decks_missing_matchups(decks, matchup_rows, dropped_deck_ids, expected_by_deck: dict[int, int]) -> list[dict]`. The `expected` int is replaced by a per-deck dict; `expected_count` in each result is that deck's value; a deck with expected 0 is never returned.
  - `_expected_matchups_by_deck(decks: list[tuple[int, str]], n_decks: int, structure: str | None, bracket_size: int | None) -> dict[int, int]`, where `decks` is `(deck_id, rank)`. Swiss: every deck gets `_swiss_rounds_for_players(n_decks)` (unchanged rule). Single elimination: `expected_matches_for_rank(rank, bracket_size)`.
  - Both list functions query `DeckRow.rank` and the event's `structure`/`bracket_size`.
  - `list_event_ids_with_missing_decks`: the target is `bracket_size` for single-elimination events, `player_count` otherwise.

- [ ] **Step 1: Write the failing DB tests** (16-deck single-elim event built with `_make_deck` + `rank`, `create_event(..., structure="single_elimination", bracket_size=16, player_count=44)`):
  - `test_single_elim_complete_bracket_not_missing`: a full 15-match bracket written per the elimination rule → `list_missing_matchups_for_event == []`, and the event is in `list_event_ids_with_complete_matchups`.
  - `test_single_elim_semifinalist_missing_one`: drop the 3-4 deck's semifinal → that deck is returned with `expected_count == 3`, `matchup_count == 2`.
  - `test_single_elim_outside_bracket_not_missing` *(Review Focus 2)*: an extra deck ranked `17-32` with no matchups is not returned.
  - `test_single_elim_bye_counts_as_match` *(Review Focus 4)*: a `9-16` deck whose only row is `Bye` is not returned.
  - `test_missing_decks_uses_bracket_size`: 16 decks, `player_count=44`, `bracket_size=16` → not in `list_event_ids_with_missing_decks`. The same event as Swiss → listed.
  - Existing Swiss tests in the file stay green unchanged.
- [ ] **Step 2: Run them to verify they fail.** `python3 -m pytest tests/test_db_matchups.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** as in Interfaces.
- [ ] **Step 4: Run the tests.** `python3 -m pytest tests/test_db_matchups.py tests/test_api.py -v`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(matchups): rank-based completeness check for single-elimination events"`

---

### Task 5: Renumber script for existing events

**Files:**
- Create: `scripts/renumber_single_elim_rounds.py` (modelled on `scripts/backfill_player_name_keys.py`: `--dry-run`/`--apply` (exactly one), `--db-env`, `load_env`, prints the target database)
- Test: `tests/test_renumber_single_elim.py`

**Interfaces:**
- Consumes: `validate_structure`, `elimination_round` (Task 1); `update_event` structure kwargs (Task 2); `take_snapshot` (`api/services/snapshots.py`); `change_log.log`, `change_log.ADMIN`; `WIN_RESULTS`/`LOSS_RESULTS` from `api/results.py`.
- Produces:
  - CLI: `python3 -m scripts.renumber_single_elim_rounds --event-id 90844 --bracket-size 16 (--dry-run|--apply) --db-env <env>`. `--event-id` is repeatable.
  - `plan_renumber(session, event_id: str, bracket_size: int) -> RenumberPlan`. `RenumberPlan` is a dataclass with `changes: list[tuple[int, int | None, int]]` (`matchup_id, old_round, new_round`) and `errors: list[str]`.
  - `apply_renumber(session, event_id: str, bracket_size: int, plan: RenumberPlan) -> int`: if `plan.errors`, raise `ValueError` and change nothing. Otherwise call `take_snapshot(session, event_id, "renumber single-elimination rounds")` first, then set the event to `("single_elimination", bracket_size)` via `update_event`, update `MatchupRow.round` for each change, and return the change count. `main()` commits, then calls `change_log.log(change_log.ADMIN, "event.renumber_rounds", f"Renumbered {n} bracket rounds", event_id=...)`.

Pairing rule (not determined by the signatures above): for each matchup row of a deck in the event, resolve the opponent deck (`opponent_deck_id`, else the event deck whose `player_id == opponent_player_id`). Group the two sides of each pair. The loser is the side whose result is in `LOSS_RESULTS`, and its partner's must be in `WIN_RESULTS`. The pair's round is `elimination_round(loser_rank, bracket_size)`. Record an error and skip the pair when: the results don't form a win/loss pair, the loser's `elimination_round` is `None`, or a deck would end with two rows in one round. Leave rows without an event opponent (Bye/drop) unchanged. Rows already in the right round are not listed in `changes`.

- [ ] **Step 1: Write the failing DB tests:**
  - `test_renumber_fixes_scrambled_rounds`: an 8-deck single-elim fixture (ranks 1, 2, 3-4×2, 5-8×4) with all rows stored at scrambled rounds → after `apply_renumber`, every QF row is round 1, SF round 2 and final round 3 (both sides), and the event is `(single_elimination, 8)`. One snapshot row exists for the event.
  - `test_renumber_refuses_contradictions`: one pair stored as `draw`/`draw` → `plan.errors` is non-empty, and `apply_renumber` raises with nothing changed.
  - `test_renumber_is_idempotent` *(Review Focus 5)*: after one apply, `plan_renumber(...).changes == []`.
- [ ] **Step 2: Run them to verify they fail.** `python3 -m pytest tests/test_renumber_single_elim.py -v`. Expected: ImportError / FAIL.
- [ ] **Step 3: Implement the script.**
- [ ] **Step 4: Run the tests.** `python3 -m pytest tests/test_renumber_single_elim.py -v`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(scripts): renumber single-elimination rounds from ranks"`

> Running it against staging/prod is **not** part of this task. It is a data write, and the user confirms each run (dry run first).

---

### Task 6: Bracket helpers in `web/src/lib/matchups.ts`

**Files:**
- Modify: `web/src/lib/matchups.ts`
- Test: `web/src/lib/matchups.test.ts`

**Interfaces:**
- Produces (mirroring Task 1; same values):
  - `bracketRounds(size: number): number`
  - `rankBandUpper(rank: string | null | undefined): number | null`: mirrors `normalize_rank` bands (digits and `"a-b"` bands up to 128).
  - `expectedBracketMatches(rank: string | null | undefined, size: number): number`
  - `bracketRoundLabel(round: number, size: number): string`
  - `BRACKET_SIZES = [2, 4, 8, 16, 32, 64, 128] as const`
  - `phasesToApiMatchups`: the cut section now blanks the opponent for bye/drop rows, as the Swiss section does.

- [ ] **Step 1: Write the failing tests:**
  - The same value tables as Task 1's `test_expected_matches_16`, `test_expected_matches_8` and `test_round_label`, for the TS functions.
  - `apiMatchupsToPhases puts null-round rows in bracket order when swissRounds is 0` *(Review Focus 3)*: input rows `[{opponent_player:'A',result:'win',round:null},{opponent_player:'B',result:'loss',round:null}]`, `swissRounds=0` → `top8` opponents are `['A','B']`. A following `phasesToApiMatchups([], top8, 0)` gives rounds `[1, 2]`.
  - `phasesToApiMatchups blanks bye opponent in the cut section` *(Review Focus 4)*: `top8 = [{opponent_player:'Bye', result:'bye', ...}]`, `swissRounds=0` → `[{opponent_player:'', result:'bye', round:1}]`.
- [ ] **Step 2: Run them to verify they fail.** `cd web && npx vitest run src/lib/matchups.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests.** `cd web && npx vitest run src/lib/matchups.test.ts`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(web): bracket helpers for single-elimination matchups"`

---

### Task 7: Frontend: event settings and bracket matchups editor

**Files:**
- Modify: `web/src/types.ts` (`Event` ~L235), `web/src/api.ts` (`createEvent` ~L335, `updateEvent` ~L384)
- Modify: `web/src/pages/EventDetail.tsx` (edit state ~L87, `eventEditDirty` ~L186, `startEdit` ~L246, `saveEdit` ~L286, edit form ~L828, details `<dl>` ~L851, matchups logic ~L530–620, `<MatchupsForm>` ~L1284)
- Modify: `web/src/pages/Events.tsx` (create form ~L32, ~L142, ~L475)
- Modify: `web/src/components/event/MatchupsForm.tsx`

**Interfaces:**
- Consumes: Task 6 helpers; API fields from Task 3.
- Produces:
  - `Event.structure?: 'swiss' | 'single_elimination'`, `Event.bracket_size?: number | null`
  - `createEvent` body and `updateEvent` params gain `structure?: 'swiss' | 'single_elimination'` and `bracket_size?: number | null`. `updateEvent` sets the `structure` / `bracket_size` query params when they are not null.
  - `MatchupsFormProps` gains `bracketSize?: number | null` and `expectedMatches?: number | null`. When `bracketSize` is set, the Swiss section and its intro sentence are not rendered. One section is rendered from `top8Matchups`, with `maxRows = bracketRounds(bracketSize)`, each row labelled `bracketRoundLabel(i + 1, bracketSize)`, and the full `opponentOptions` (Bye allowed). The hint reads "Bracket rounds in order, first round first. Expected for this deck: {expectedMatches}." `MatchupRows` gains an optional `rowLabel?: (i: number) => string`, rendered before the opponent select.

Behaviour (EventDetail):
- `isSingleElim = event.structure === 'single_elimination' && !!event.bracket_size`.
- `matchupsSwissRounds` is `0` when `isSingleElim`.
- On open: when `isSingleElim`, set `swissMatchups` to `[]`, and give `top8Matchups` one empty row if it is empty.
- The add-row cap is `bracketRounds(bracket_size)`. Save goes through `phasesToApiMatchups([], top8Matchups, 0)`.
- Swiss events: no change.
- Edit form: a "Structure" `<select>` (`Swiss + Top 8` / `Single elimination`). When single elimination is chosen, a "Bracket size" `<select>` over `BRACKET_SIZES` appears (defaults to 16). Both are included in `eventEditDirty`, and `saveEdit` sends them.
- Details `<dl>`: when `isSingleElim`, add `<dt>Structure</dt><dd>Single elimination · {bracket_size}-player bracket</dd>`.
- Events.tsx create form: the same two selects, sent in `createEvent`.

- [ ] **Step 1: Implement types + api + MatchupsForm + EventDetail + Events.**
- [ ] **Step 2: Verify the build, lint and tests.** Run `npm run lint && cd web && npm run build && npx vitest run`. Expected: all pass with no type errors.
- [ ] **Step 3: Verify in the running app** (`npm run api`, `npm run web`, local DB). Create a manual event as single elimination with bracket size 8 and 8 ranked decks. Open the matchups editor for the rank-1 deck: there is no Swiss section, rows are labelled Quarterfinal/Semifinal/Final, and the cap is 3 rows. Save; on reopening, the rows come back in order. A Swiss event's editor is unchanged.
- [ ] **Step 4: Commit.** `git commit -m "feat(web): single-elimination event settings and bracket matchups editor"`

---

### Task 8: Docs and full verification

**Files:**
- Modify: `CLAUDE.md` (Backend Patterns: a short paragraph "Event structure": the `structure`/`bracket_size` columns, `api/brackets.py` as the one place for bracket maths mirrored in `web/src/lib/matchups.ts`, the rank-based completeness rule, and `scripts/renumber_single_elim_rounds.py` for fixing old events)

- [ ] **Step 1: Write the CLAUDE.md paragraph.**
- [ ] **Step 2: Run the full suites.** Run `npm run lint && python3 -m pytest && cd web && npx vitest run && npm run build && cd .. && npm run gen:routes:check`. Expected: all green, routes up to date.
- [ ] **Step 3: Commit.** `git commit -m "docs: single-elimination events"`
