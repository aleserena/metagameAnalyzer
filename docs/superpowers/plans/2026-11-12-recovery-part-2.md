# Data Recovery — Part 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make lost or damaged data recoverable: whole-database backups on Railway, per-event snapshots with one-click restore, a change log, and hand corrections that survive a re-scrape.

**Architecture:** One additive migration (019) adds two tables (`event_snapshots`, `change_log`) and a nullable `manual_fields` JSON column on `decks` and `events`. A snapshot is the existing event export (`build_event_export`) stored as JSON; restore is a new in-place writer that keeps the original event id, deck ids and origins (the existing `import_event_payload` always creates a *new* event, so it cannot be reused as is). Snapshots are taken inside the transaction of each destructive action, before it changes anything. The scrape path skips fields listed in `manual_fields`.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / Alembic / pytest (real Postgres via `TEST_DATABASE_URL`); React + TypeScript / Vitest; Railway CLI (`railway postgres pitr …`).

**Spec:** `docs/superpowers/specs/2026-11-11-security-hardening-and-recovery-design.md`, Part 2 (sections 2.1–2.4).

## Global Constraints

- Follow `CLAUDE.md`. `python3`, `db.utcnow_naive()`, routes in the matching router then `npm run gen:routes`, no new frontend styling system.
- **Additive migration only:** new tables and nullable columns; the previous release must keep working against the migrated database. Deploy when no scrape or MTGJSON sync is running.
- Any change to decks must end with `_load_decks_from_db()` (or `state.touch()`), as existing handlers do.
- Commit directly on `staging`, one commit per task.
- Snapshots contain player emails: listing and restore are admin only, and snapshot JSON is never returned to event-edit link holders.
- The change log identifies a link by its type and label, never by its token.
- Exact values from the spec: keep the newest **10** snapshots per event and nothing older than **90** days; change log kept **180** days; fallback dump retention **14** days.
- Before each commit `npm run lint`; before finishing: `python3 -m pytest`, `cd web && npx vitest run`, `cd web && npm run build`, `npm run gen:routes:check`.

## Facts established before planning (2026-11-12)

- `railway postgres pitr status` reports **disabled, no bucket** for the `postgres` service in both `production` and `staging`, and `railway postgres pitr schedule list` reports **no backup schedule** on production. Production currently has no backups of any kind.
- The Railway CLI offers `pitr enable`, `pitr backup create|list|restore|lock`, `pitr schedule set|list`, and `pitr restore` (into a new service).
- `import_event_payload` (`api/services/event_import.py`) creates a new manual event with fresh event and deck ids.
- `upsert_deck` (`api/db.py:415`) overwrites name, player, rank, card lists of an existing deck; archetype and commanders survive only when the incoming dict has none.
- The scrape skips existing events unless `force_replace` or explicit event ids are given (`api/routers/data.py:195`).

## Review Focus

1. **Restoring an event after a merge.** Its decks now belong to the other event. Restore must bring them back under the original event id without leaving duplicates in the kept event. (Task 4)
2. **Restoring when a player was renamed, merged or deleted since.** Decks must reattach to the right player by name, creating the player if needed, never failing the whole restore. (Task 4)
3. **Clear-decks with hundreds of events.** One snapshot per event in a single transaction must finish in reasonable time and must not be pruned by its own retention rule. (Task 5)
4. **A forced re-scrape of many existing events, repeated.** It must not fill the table with identical snapshots or push out the one snapshot that matters. (Tasks 3 and 5)
5. **A hand edit that sets a field back to the scraped value.** It still counts as a hand edit; the next scrape must not touch it. (Task 7)

---

### Task 1: Whole-database backups on Railway (owner go-ahead required)

**Files:**
- Create: `docs/BACKUP_RESTORE.md`

This task changes Railway infrastructure and adds storage cost. **Do not run any enabling command until the owner has said which option to use.** Reading status is fine.

- [ ] **Step 1: Get the owner's decision** between (a) point-in-time recovery — `railway postgres pitr enable`, continuous, about four weeks of history, needs a Railway storage bucket and redeploys the database service — and (b) a scheduled backup only — `railway postgres pitr schedule set`, daily, restores to the time of the backup. Run `railway postgres pitr enable --help` and `railway postgres pitr schedule set --help` and give the owner the exact options and what the CLI says about cost or plan requirements. If neither is available on the plan, stop and ask before building the spec's fallback (a scheduled `pg_dump` to a bucket, 14 days).

- [ ] **Step 2: Enable on staging first.** Run the chosen command with `-s postgres -e staging`. Verify: `railway postgres pitr status -s postgres -e staging` shows it enabled (or `schedule list` shows the schedule); `railway postgres pitr backup create -s postgres -e staging` then `backup list` shows a completed backup.

- [ ] **Step 3: Restore drill on staging.** Note a row count (`SELECT count(*) FROM decks`) and the time. Restore into a **new** service with `railway postgres pitr restore` (or `backup restore`), connect to the restored service, and confirm the same count. Do not repoint the app. Delete the restored service afterwards — ask the owner before deleting.

- [ ] **Step 4: Enable on production** with the same command and `-e production`, at a time when no scrape or sync is running. Verify as in Step 2. Take one on-demand backup and `lock` it as the baseline.

- [ ] **Step 5: Write `docs/BACKUP_RESTORE.md`:** what is enabled and where; how to check it is healthy; the exact restore commands used in the drill, with the staging drill's date and result; how to point the app at a restored service (change `DATABASE_URL`, redeploy) and how to copy one table back instead; when to use a database restore versus an event snapshot (Task 8).

- [ ] **Step 6: Commit** — `git commit -m "docs: database backup and restore runbook"`

---

### Task 2: Migration 019 and models

**Files:**
- Create: `alembic/versions/019_snapshots_change_log_manual_fields.py`
- Modify: `api/db.py` (models near `EventUploadLinkRow`; `DeckRow`, `EventRow`)
- Test: `tests/test_schema_drift.py` (existing drift check), `tests/test_db_snapshots.py` (new)

**Interfaces:**
- Produces: `EventSnapshotRow` — table `event_snapshots`: `id` (PK), `event_id` (String, indexed, **no foreign key**: the event may be deleted), `event_name` (String), `created_at` (DateTime, naive UTC, indexed), `reason` (String(64)), `payload_hash` (String(64)), `payload` (JSON).
- Produces: `ChangeLogRow` — table `change_log`: `id` (PK), `at` (DateTime, naive UTC, indexed), `actor` (String(128)), `action` (String(64)), `event_id` (String, nullable, indexed), `deck_id` (Integer, nullable), `summary` (String(512)).
- Produces: `DeckRow.manual_fields` and `EventRow.manual_fields` — nullable JSON list of field names.

- [ ] **Step 1: Write the failing test** in `tests/test_db_snapshots.py`: with `db_session_rollback`, insert one `EventSnapshotRow` and one `ChangeLogRow`, flush, read them back; set `manual_fields = ["player"]` on a deck created with `upsert_deck` and read it back. Run `python3 -m pytest tests/test_db_snapshots.py -v` — FAIL (names not defined).

- [ ] **Step 2: Write the migration** following the header style of `017_event_date_columns.py` (`revision = "019"`, `down_revision = "018"`). `upgrade()` creates the two tables with their indexes and adds the two nullable columns. `downgrade()` drops them. No backfill.

- [ ] **Step 3: Add the models and columns** to `api/db.py`.

- [ ] **Step 4: Run** `python3 -m pytest tests/test_db_snapshots.py tests/test_schema_drift.py -v` — PASS (the test session migrates the test database to head).

- [ ] **Step 5: Commit** — `git commit -m "feat(recovery): migration 019 — event snapshots, change log, manual_fields"`

---

### Task 3: Taking and pruning snapshots

**Files:**
- Create: `api/services/snapshots.py`
- Test: `tests/test_snapshots.py`

**Interfaces:**
- Consumes: `build_event_export(session, event_id, *, include_emails: bool) -> EventExportData | None` (`api/services/event_export.py`); `EventSnapshotRow` (Task 2).
- Produces:
  - `SNAPSHOT_KEEP_PER_EVENT = 10`, `SNAPSHOT_MAX_AGE_DAYS = 90`
  - `take_snapshot(session, event_id: str, reason: str) -> int | None` — returns the snapshot id; `None` when the event does not exist. Payload is the export with `include_emails=True`, serialised with `model_dump(mode="json")`, plus a top-level `"origins"` object `{"event": <origin>, "decks": {"<deck_id>": <origin>}}` if the export does not already carry origins (check first). If the newest snapshot of that event has the same `payload_hash` (SHA-256 of the canonical JSON), no row is written and that snapshot's id is returned.
  - `prune_snapshots(session, event_id: str) -> int` — deletes that event's snapshots beyond the newest 10 and any older than 90 days; returns the number deleted. Called by `take_snapshot` after inserting.
  - `list_snapshots(session, *, event_id: str | None = None, limit: int = 200) -> list[dict]` — newest first; each `{id, event_id, event_name, created_at (iso_utc), reason, deck_count, matchup_count}`; never the payload.
- Reasons used by later tasks (exact strings): `"delete"`, `"merge"`, `"hadouken"`, `"clear_decks"`, `"rescrape"`, `"before_restore"`.

- [ ] **Step 1: Write the failing tests** (real DB, `db_session_rollback`; build an event with two decks, one matchup pair and one player email using the helpers the existing `tests/test_event_export.py` uses):

```python
def test_snapshot_holds_decks_matchups_and_emails(...):
    sid = take_snapshot(session, "snap_ev_1", "delete")
    row = session.get(EventSnapshotRow, sid)
    assert row.reason == "delete" and row.event_name
    assert len(row.payload["decks"]) == 2 and len(row.payload["matchups"]) == 2
    assert row.payload["player_emails"]  # emails are included

def test_snapshot_of_missing_event_returns_none(...):
    assert take_snapshot(session, "no_such_event", "delete") is None

def test_identical_snapshot_is_not_stored_twice(...):
    first = take_snapshot(session, "snap_ev_1", "rescrape")
    assert take_snapshot(session, "snap_ev_1", "rescrape") == first
    assert session.query(EventSnapshotRow).filter_by(event_id="snap_ev_1").count() == 1

def test_only_the_newest_ten_are_kept(...):
    # change the event between snapshots so each payload differs; take 12
    assert session.query(EventSnapshotRow).filter_by(event_id="snap_ev_1").count() == 10

def test_snapshots_older_than_ninety_days_are_dropped(...):
    # backdate one row's created_at to 91 days ago, take another
    assert backdated_id not in remaining_ids

def test_listing_never_returns_the_payload(...):
    assert all("payload" not in s and "player_emails" not in s for s in list_snapshots(session))
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_snapshots.py -v` — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(recovery): take, dedupe and prune event snapshots"`

---

### Task 4: Restoring a snapshot in place

**Files:**
- Modify: `api/services/snapshots.py`
- Test: `tests/test_snapshots.py`

**Interfaces:**
- Consumes: Task 3; `_db.upsert_matchups_for_deck`, `_db.set_player_email`, `_resolve_deck_player`, `_db.sync_decks_with_event`.
- Produces: `restore_snapshot(session, snapshot_id: int) -> dict` — returns `{"event_id", "deck_count", "matchup_count", "safety_snapshot_id"}`. Raises `LookupError` when the snapshot does not exist.

Behaviour, in this order, in one transaction:
1. If the event currently exists, `take_snapshot(session, event_id, "before_restore")`; its id is `safety_snapshot_id` (else `None`).
2. Remove the event's current decks and their matchups, and any current deck (in whatever event) whose `deck_id` is in the snapshot — that is how decks moved by a merge come back.
3. Recreate or update the event row with the snapshot's **same `event_id`**, fields and origin.
4. Recreate each deck with its **original `deck_id`** and origin, resolving the player by name with `_resolve_deck_player` (creates the player if it no longer exists). Restore `manual_fields` if present in the payload.
5. Recreate the matchup rows exactly as stored (both sides are in the export; generate no inverse rows — same rule as `import_event_payload`), dropping a row whose `opponent_deck_id` no longer exists anywhere.
6. Restore player emails with `_db.set_player_email`.
The caller reloads the in-memory decks after commit.

- [ ] **Step 1: Write the failing tests:**

```python
def test_restore_brings_back_a_deleted_event(...):
    sid = take_snapshot(session, "snap_ev_1", "delete")
    db.delete_event(session, "snap_ev_1", delete_decks=True); session.flush()
    out = restore_snapshot(session, sid)
    assert out["event_id"] == "snap_ev_1" and out["deck_count"] == 2
    assert {d["deck_id"] for d in db.get_decks_by_event(session, "snap_ev_1")} == original_deck_ids
    assert db.get_player_email(session, "Alice") == "alice@example.com"

def test_restore_undoes_edits_and_takes_a_safety_snapshot(...):
    # snapshot, change a deck's player and delete a matchup, restore
    assert restored player == original and matchup count == original
    assert session.get(EventSnapshotRow, out["safety_snapshot_id"]).reason == "before_restore"

def test_restore_after_merge_moves_decks_back(...):
    # snapshot event A, reassign its decks to event B and delete A, restore A
    assert A has its decks again and B no longer lists them

def test_restore_recreates_a_player_that_was_deleted(...):
def test_restore_keeps_deck_and_event_origin(...):          # mtgtop8 stays mtgtop8
def test_restore_of_unknown_snapshot_raises_lookup_error(...):
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** `python3 -m pytest tests/test_snapshots.py tests/test_event_export.py tests/test_event_import.py -v` — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(recovery): restore an event snapshot in place"`

---

### Task 5: Snapshot before every destructive action

**Files:**
- Modify: `api/routers/events.py` (`delete_event_endpoint` ~504, `merge_events`, `apply_hadouken_import` ~850), `api/routers/settings.py` (`post_clear_decks` ~136 and the `_clear_decks_in_db` it calls), `api/services/scrape_store.py` (`persist_scraped_decks`)
- Test: `tests/test_snapshots.py`, `tests/test_scrape_store.py`, `tests/test_event_merge.py`, `tests/test_hadouken_import.py`

**Interfaces:**
- Consumes: `take_snapshot(session, event_id, reason)`.

The snapshot is taken in the **same session and transaction** as the action, before the first change. If the snapshot fails, the action fails and nothing changes.

| Action | Snapshot(s) | Reason |
|---|---|---|
| Delete event | that event | `delete` |
| Merge events | both events | `merge` |
| Hadouken apply | that event | `hadouken` |
| Clear decks | every event that has decks | `clear_decks` |
| Scrape persisting decks for an event that already exists | that event, once per scrape | `rescrape` |

- [ ] **Step 1: Write the failing tests** — one per row: perform the action through the function the handler calls (same style as the existing merge / Hadouken / scrape-store tests) and assert a snapshot with that reason exists for each affected event and that restoring it returns the pre-action state. Plus:

```python
def test_scraping_a_new_event_takes_no_snapshot(...):
def test_clear_decks_snapshots_every_event_once(...):   # 30 events -> 30 snapshots, all restorable
def test_failed_snapshot_blocks_the_delete(...):        # take_snapshot patched to raise -> event still exists
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Wire in** the five call sites. For clear-decks, iterate events in one transaction; if 30 events take more than a few seconds locally, report the timing instead of changing the approach. **Step 4: Run** the four test files — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(recovery): snapshot events before delete, merge, Hadouken import, clear and re-scrape"`

---

### Task 6: Change log

**Files:**
- Create: `api/services/change_log.py`
- Modify: `api/dependencies.py` (expose who is acting), and the mutating handlers in `api/routers/events.py`, `decks.py`, `matchups.py`, `upload.py`, `players.py`, `settings.py`, `data.py`
- Test: `tests/test_change_log.py`

**Interfaces:**
- Produces:
  - `CHANGE_LOG_MAX_AGE_DAYS = 180`
  - `record(session, *, actor: str, action: str, summary: str, event_id: str | None = None, deck_id: int | None = None) -> None` — adds one `ChangeLogRow`; truncates `summary` to 512 characters; deletes rows older than 180 days at most once per process per hour.
  - `link_actor(link_row) -> str` — `"link:<link_type>:<label or 'unlabelled'>"`. Never includes the token.
  - `ADMIN = "admin"`
  - `list_changes(session, *, event_id: str | None = None, limit: int = 200) -> list[dict]` — newest first: `{id, at (iso_utc), actor, action, event_id, deck_id, summary}`.
- The two event-edit dependencies in `api/dependencies.py` currently return `"admin"` or `"event_edit"`. Keep those return values (handlers compare against them) and add a small helper, `acting_as(role: str, event_edit_token: str | None) -> str`, that returns `ADMIN` or the `link_actor(...)` of that token's link row.

Actions (exact strings) and where they are recorded — each in the handler's existing transaction, after the change succeeds:

`event.create`, `event.update`, `event.delete`, `event.merge`, `event.import`, `event.hadouken`, `event.restore` (Task 8), `deck.create`, `deck.update`, `deck.delete`, `deck.matchups`, `matchup.update`, `upload.deck`, `upload.feedback`, `upload.decklist`, `player.alias_add`, `player.alias_remove`, `player.email` (summary says "set" or "removed", **never the address**), `settings.update`, `data.clear_decks`, `data.load`, `data.scrape` (one row per scrape, with counts).

- [ ] **Step 1: Write the failing tests:**

```python
def test_record_and_list_newest_first(...):
def test_summary_is_truncated_to_512_characters(...):
def test_link_actor_names_type_and_label_not_the_token(...):
    assert link_actor(row) == "link:event_edit:Store organiser" and row.token not in link_actor(row)
def test_rows_older_than_180_days_are_dropped(...):
def test_player_email_change_does_not_log_the_address(...):
def test_public_upload_is_logged_with_the_link_as_actor(...):    # via the upload route function, real DB
def test_admin_deck_update_is_logged(...):
def test_a_failed_mutation_logs_nothing(...):                   # handler raises -> no row
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement the service, then wire each handler** listed above. **Step 4: Run** `python3 -m pytest tests/test_change_log.py tests/test_api.py tests/test_db_upload_links.py -v` — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(recovery): change log for every data mutation"`

---

### Task 7: Hand corrections survive a re-scrape

**Files:**
- Modify: `api/db.py` (`upsert_deck` ~415, `update_event`), `api/services/scrape_store.py`, and the hand-edit paths: `api/routers/decks.py` (`update_deck_endpoint`), `api/routers/upload.py` (update, feedback, decklist), `api/routers/events.py` (`update_event_endpoint`)
- Test: `tests/test_scrape_store.py`, `tests/test_db_snapshots.py`

**Interfaces:**
- Produces:
  - `DECK_MANUAL_FIELDS = ("name", "player", "rank", "archetype", "commanders", "mainboard", "sideboard")`; `EVENT_MANUAL_FIELDS = ("name", "date", "format_id", "store", "location")`
  - `upsert_deck(session, d, origin=ORIGIN_MTGTOP8, *, manual: bool = False, respect_manual: bool = False)`. With `manual=True`, every field in `DECK_MANUAL_FIELDS` that is present in `d` is added to `row.manual_fields` — **whether or not the value changed** (a deliberate confirmation of the scraped value is still a hand edit). With `respect_manual=True`, fields listed in `row.manual_fields` are left untouched; for `player`, the row's `player_id` and denormalised name are left untouched too.
  - `update_event(session, event_id, *, manual: bool = False, respect_manual: bool = False, **fields)` with the same meaning for `EVENT_MANUAL_FIELDS`.
- `persist_scraped_decks` and `_ensure_event` pass `respect_manual=True`. The hand-edit handlers pass `manual=True`. Other callers (import, restore, Hadouken) pass neither.

Note the spec says a field is marked "when the new value differs"; this plan marks any field the hand-edit request **sends**, because the edit forms resend every field and a field the editor left equal to the scraped value was still reviewed by a person. If the deck edit endpoint receives only changed fields (check `update_deck_endpoint`'s body handling), the two rules coincide. Record whichever applies in the commit body.

- [ ] **Step 1: Write the failing tests:**

```python
def test_rescrape_keeps_a_hand_corrected_player_and_refreshes_the_rest(...):
    # scraped deck; hand edit player via upsert_deck(..., manual=True);
    # persist_scraped_decks with a different player AND a different rank
    assert row.player == "Corrected Name" and row.rank == "new scraped rank"

def test_forced_rescrape_also_keeps_corrections(...):          # refresh_events=True
def test_hand_corrected_card_list_survives(...):
def test_field_set_back_to_the_scraped_value_stays_protected(...):
def test_unedited_deck_is_fully_refreshed(...):                # manual_fields is None
def test_event_name_edited_by_hand_survives_a_forced_rescrape(...):
def test_decks_edited_before_this_release_are_not_protected(...):  # manual_fields None -> overwritten (known limit)
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** in `api/db.py`, then pass the flags from the scrape path and the hand-edit handlers. **Step 4: Run** `python3 -m pytest tests/test_scrape_store.py tests/test_db_snapshots.py tests/test_api.py -v` — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(recovery): hand-edited deck and event fields survive a re-scrape"`

---

### Task 8: Snapshots and change log on the Settings page

**Files:**
- Modify: `api/routers/settings.py`, `api/schemas/settings.py`, `web/src/api.ts`, `web/src/types.ts`, `web/src/pages/Settings.tsx`
- Create: `web/src/components/settings/SnapshotsPanel.tsx`, `web/src/components/settings/ChangeLogPanel.tsx`
- Test: `tests/test_api.py`, `web/src/components/settings/SnapshotsPanel.test.tsx`

**Interfaces:**
- Routes, all `Depends(require_admin)` + `Depends(require_database)`:
  - `GET /api/v1/settings/snapshots?event_id=&limit=` → `{"snapshots": list_snapshots(...)}`
  - `POST /api/v1/settings/snapshots/{snapshot_id}/restore` → `restore_snapshot(...)` result; 404 for an unknown id; then `_load_decks_from_db()`, invalidate the events cache, and `change_log.record(action="event.restore", …)`.
  - `GET /api/v1/settings/change-log?event_id=&limit=` → `{"changes": list_changes(...)}`
- Frontend: `getSnapshots(eventId?)`, `restoreSnapshot(id)`, `getChangeLog(eventId?)` in `api.ts`.

`Settings.tsx` is 620 lines; put the two new sections in their own components and render them from the page. Use `.table-wrap` for the tables.

- **Snapshots panel:** table of event name, when (local time), why (human label for each reason), decks, matchups, and a **Restore** button. Restore asks for confirmation in the page (not `window.confirm`) with exactly: `Restore "<event name>" to how it was on <date>? The current version is saved first, so this can be undone.` On success show `Event restored.` and reload the list.
- **Change log panel:** newest-first table of when, who (`admin` or the link's type and label), what, event; a text filter by event id. No diff view.

- [ ] **Step 1: Write the failing backend tests:** each route returns 401 without admin; listing returns no `payload` key; restore of an unknown id returns 404; restore of a real snapshot (patched service) returns its result and writes an `event.restore` change-log row.

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement the routes**, run `npm run gen:routes`. **Step 4: Run** — PASS.

- [ ] **Step 5: Write the failing frontend test:** the panel lists two mocked snapshots; clicking Restore shows the confirmation text above with the event name; confirming calls `restoreSnapshot` with that id and then shows `Event restored.`; cancelling calls nothing.

- [ ] **Step 6: Run** `cd web && npx vitest run src/components/settings` — FAIL. **Step 7: Implement both panels.** **Step 8: Run** — PASS; `cd web && npm run build`.

- [ ] **Step 9: End-to-end check on staging** (after push): delete a throwaway event, restore it from the Settings page, and confirm its decks, matchups and emails are back and the change log shows the delete and the restore.

- [ ] **Step 10: Update `CLAUDE.md`:** the snapshot rule (which actions snapshot, same transaction), `manual` / `respect_manual` on `upsert_deck` and `update_event` and who passes which, the change-log rule (every new mutating handler records an entry), and a pointer to `docs/BACKUP_RESTORE.md`.

- [ ] **Step 11: Commit** — `git commit -m "feat(recovery): snapshots and change log on the Settings page"`

---

## Final verification

- [ ] `npm run lint`; `python3 -m pytest` (none of the new DB tests skipped); `cd web && npx vitest run`; `cd web && npm run build`; `npm run gen:routes:check`.
- [ ] On staging: migration 019 applied by the deploy; an event deleted and restored from the Settings page; a deck's player corrected by hand survives a forced re-scrape of its event; the change log shows each step.
- [ ] `railway postgres pitr status` (or `schedule list`) shows backups active on production, and `docs/BACKUP_RESTORE.md` records a completed staging restore drill.
