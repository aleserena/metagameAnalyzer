# Security hardening and data recovery — design

Date: 2026-11-11
Source: ISO 31000 risk review of this repository (risks R1–R10), followed by a design conversation with the owner.

## Why

The risk review found no critical vulnerability, but three high risks and one gap the owner has already been hurt by:

- Secret link tokens are written to the server logs, and event-edit links stay usable for days after use.
- One long-lived admin session token grants every destructive action.
- Anonymous visitors can tie up the server through the card lookup endpoint.
- There is no way to recover data. After past incidents the owner re-scraped and re-entered everything by hand. A re-scrape cannot bring back hand-entered matchups, players and deck lists, and it overwrites hand corrections on scraped decks.

## How the app is actually used (from the owner)

- The owner is the only admin. They log in from one PC, not mobile.
- A normal admin session is one sitting: run a scrape, then complete events by hand or by Hadouken import.
- Everyone else changes data only through links the owner sends. An organiser opens an event-edit link and finishes in a single sitting.
- Hand corrections must survive a re-scrape.

## Goals

1. A leaked link or session token is useful for hours, not days, and cannot be read out of logs.
2. An anonymous visitor cannot exhaust the server or get its IP blocked by Scryfall.
3. Any single event can be put back as it was before a destructive action, from the Settings page.
4. The whole database can be rewound after a catastrophe, and the procedure has been run once for real.
5. Hand corrections to scraped decks survive a re-scrape.
6. Dependency and secret problems are caught by CI rather than by chance.
7. The security posture is written down so the review can be repeated.

## Non-goals

- Per-user admin accounts, organiser accounts, roles. One admin password remains the only login.
- A second factor for the admin login.
- Changing how deck-upload and feedback links work (they already die on submission).
- Multi-replica support. The in-memory rate limiters and captcha replay store stay in-memory; the single-instance assumption is documented instead.
- Formal agreements with mtgtop8, Moxfield or Hadouken (noted in the risk register as an accepted risk).

## Anti-goals

- An organiser who opens a link and works in one sitting must notice no difference.
- The public site must not lose features: every page that shows cards today still shows them.
- No migration may break the previous release (see the additive-migration rule in `CLAUDE.md`).

## Constraints

- Follow `CLAUDE.md`: additive migrations only (next number is 019), routes go in the matching domain router followed by `npm run gen:routes`, `db.utcnow_naive()` for timestamps, no new frontend styling system, cache invalidation through `state.set_decks()` / `state.touch()`.
- Work is committed directly on `staging`; the owner promotes to `master`.
- Each of the three parts below ships on its own and leaves the app working.

---

## Part 1 — Quick hardening

### 1.1 Link tokens out of the logs (R2)

The request logger in `api/main.py` logs `request.url.path`, which contains the token for `/api/v1/upload/{token}`, `/api/v1/upload/{token}/feedback`, `/api/v1/upload/{token}/decklist` and `/api/v1/event-edit/{token}`. The frontend pages that carry the token in their own URL are served by the SPA catch-all and logged the same way.

Decided: the logged path (both the message and the `path` extra) has the token segment replaced with `***`. This applies to the API routes above and to the matching frontend routes. The builder finds the frontend route shapes in `web/src/App.tsx`.

### 1.2 Event-edit links close after the sitting (R2)

Today `GET /api/v1/event-edit/{token}` marks the link used, but `require_admin_or_event_edit` and `require_admin_or_event_edit_deck` only check `expires_at`, so the token keeps working until its 7-day expiry.

Decided:

- On first open, the link's `expires_at` is pulled in to *now + 12 hours* (never extended past its existing expiry). No schema change is needed.
- Unopened links keep the default 7-day expiry.
- The 12 hours is the builder's proposal accepted by the owner; make it a named constant.

An organiser returning the next day gets "link expired" and asks the owner for a new one. This is accepted.

### 1.3 Admin session (R1)

Decided:

- Admin JWT lifetime drops from 7 days to 12 hours (`JWT_EXP_SECONDS` in `api/dependencies.py`).
- The frontend already clears the token and returns to login on a 401; confirm that path gives a clear "session expired, log in again" experience mid-sitting rather than a silent failure.
- `docs/` gets a short note: changing `JWT_SECRET` in Railway logs out every session and invalidates outstanding captcha tokens.

### 1.4 Login throttle that can't be sidestepped (R1)

`client_ip()` in `api/services/rate_limit.py` trusts `X-Real-IP`. Railway's docs say its edge sets that header; they do not say whether a client-supplied value is overwritten.

Decided: first test it — send a request to staging with a forged `X-Real-IP` and see which address the app logs. If the forged value wins, change `client_ip()` to a source the client cannot control (builder's choice, based on what Railway actually sends). If Railway overwrites it, record that finding in a comment and change nothing.

### 1.5 Public endpoints (R3)

Decided:

- `POST /api/v1/cards/lookup` accepts fewer names per request. The builder first measures the largest batch the frontend sends (deck pages, compare, archetype pages) and sets the cap just above it; if a legitimate page needs more than about 150, the frontend batches instead. Builder's call on the number.
- Names that are missing from the `cards` table must not trigger live Scryfall calls for anonymous callers. Preferred: the public endpoint never uses the Scryfall fallback, while admin-triggered paths (deck import, analyse) still may. If that split is awkward in `card_lookup.py`, the fallback for anonymous callers is limited to a handful of names per request. Builder's call, provided an anonymous request can never cause more than a few outbound calls.
- A per-IP rate limit, using the existing `RateLimiter`, on the public write endpoints: the four `/upload/{token}` routes and `/cards/lookup`. Limits generous enough that a real user never meets them.
- FastAPI's `/docs`, `/redoc` and `/openapi.json` are disabled when deployed (`is_deployed()`), left on locally.

### 1.6 Browser protection headers (R7)

Decided: one middleware adds `Strict-Transport-Security` (deployed only), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` (also keeps link tokens out of Referer headers) and a `Content-Security-Policy`.

The CSP must allow what the app really loads: its own scripts and styles, inline styles (the frontend uses `style={{…}}` throughout), and card images from `cards.scryfall.io`. The builder derives the exact policy from the built frontend and verifies every page type in a browser with the console open. If a strict CSP cannot be finished safely, ship it as `Content-Security-Policy-Report-Only` first and say so.

### 1.7 Small leaks (R10)

- `POST /api/v1/feedback` returns a generic "could not create issue" message; GitHub's error text goes to the log only.
- If `PUBLIC_APP_URL` is unset when deployed, log a warning at startup (emailed links would otherwise be built from the request's Host header). Confirm it is set in Railway production and staging.

### 1.8 Supply chain (R6)

Decided:

- Dependabot config for pip, npm (`web/`), GitHub Actions and Docker.
- CI gains `pip-audit` against `requirements.txt` and `npm audit --omit=dev --audit-level=high` in `web/`. Builder's call whether a finding fails the build or warns at first; failing is preferred once the baseline is clean.
- The Dockerfile runs the app as a non-root user. The `/data` volume (`DATA_DIR`) must stay writable by that user — verify on staging before production, since the volume already exists with root-owned files.
- Owner action, not code: turn on GitHub secret scanning and push protection for the repository.

---

## Part 2 — Recovery

### 2.1 Whole-database rewind (R4)

Production is a Railway Postgres 17 service (`postgres-ssl:17`) with its own volume. Railway offers scheduled volume backups and point-in-time recovery (about four weeks of history). Whether the owner's plan includes them, and whether either is on, is unknown.

Decided:

- First step is to check the Railway dashboard / `railway postgres pitr` for what is available and enabled.
- If available: enable point-in-time recovery (or, failing that, a daily backup schedule) on production.
- If not available on the plan: fall back to a scheduled `pg_dump` to a Railway bucket, keeping 14 days. This fallback needs the owner's go-ahead before it is built, since it adds a service.
- Either way: perform one real restore into the staging environment, and write the steps as a runbook in `docs/`.

### 2.2 Event snapshots

Purpose: "I broke one event and want it back as it was an hour ago."

The app already round-trips an event through `build_event_export` (`api/services/event_export.py`) and the event import service. A snapshot is that export, including player emails, stored in a new table.

Decided:

- New table (migration 019), holding: event id, event name at the time, created-at, the reason (which action triggered it), and the export JSON.
- A snapshot is taken automatically, inside the same transaction and before any change, by: event delete, event merge (both events), Hadouken apply, clear-decks (every event), and a re-scrape that touches an event that already exists.
- Snapshots are not taken for ordinary single-deck or matchup edits; the change log (2.3) covers those.
- Settings page: a list of snapshots (event, when, why) with a Restore button, admin only. Restore first snapshots the event's current state, then replaces the event with the snapshot contents, then reloads the in-memory decks. Restoring a deleted event recreates it.
- Retention: keep the newest 10 snapshots per event and drop anything older than 90 days. Builder's call; make both numbers constants.
- Snapshots contain player emails, so the listing and restore endpoints are admin only and the JSON is never returned to event-edit link holders.

Left to the builder: whether restore reuses the import service as it stands or needs a "replace" mode; how to keep clear-decks from producing an unreasonably large number of rows (one snapshot per event is the intent — if the dataset makes that too slow, say so before choosing something else).

### 2.3 Change log

Purpose: know what changed, when, and through which door, so the right snapshot can be chosen and link misuse is visible.

Decided:

- New table (same migration): when, actor, action, event id, deck id (both nullable), and a short human-readable summary.
- Actor is `admin` or the link, identified by its label and type — never by the token itself.
- Written by every mutating endpoint that changes events, decks, matchups, players, aliases or settings, including the public upload-link endpoints.
- Shown on the Settings page as a simple newest-first list with an event filter. No diff viewer.
- Retention: 180 days. Builder's call.

### 2.4 Corrections survive a re-scrape

Today `upsert_deck` overwrites name, player, rank and card lists of an existing scraped deck with whatever mtgtop8 returns. A hand-set archetype already survives because the scraper sends none.

Decided:

- Each deck remembers which of its fields were edited by hand: a nullable JSON column on `decks` (same migration), listing field names among name, player, rank, archetype, commanders, mainboard, sideboard.
- A field is marked when it is changed through an admin or link endpoint (deck edit, upload-link update, feedback, decklist) and the new value differs from the old one.
- The scrape path leaves marked fields alone and refreshes the rest. This holds for a forced re-scrape too.
- Event-level fields follow the same principle where the scrape refreshes them (name, date, format, store, location under `refresh_events`): an event edited through the event edit endpoint keeps its hand-set values. The builder may implement this with the same mechanism on `events`.
- Known limit, accepted: corrections made before this ships are not marked. The pre-re-scrape snapshot (2.2) is the safety net for those.

Left to the builder: whether to offer a per-deck "reset to mtgtop8" action. Not required.

---

## Part 3 — Paperwork

- `SECURITY.md`: how to report a problem, what is in scope.
- `docs/RISK_REGISTER.md`: the R1–R10 table from the review, each with its treatment and status, plus the accepted risks (single admin password without second factor; dependence on mtgtop8 / Moxfield / Hadouken; single-instance in-memory limiters; production credentials on the owner's machine). Reviewed after each release that touches auth, links or data handling.
- A short privacy note on the site (R5): what is stored about players (names and results from public tournament pages; emails only when the owner adds them to send links), that emails are never shown publicly, and how to ask for correction or removal. Placement is the builder's call — a footer link to a small page fits the existing layout. The removal procedure itself (what the owner does when asked) goes in `docs/`.
- `CLAUDE.md` updated for anything that changes how the project is worked on: snapshots and when they are taken, the hand-edited-fields rule, the 12-hour session and link windows.

## Order

Part 1, then Part 2, then Part 3. Within Part 1, items 1.1 and 1.2 first. Within Part 2, 2.1 first because it is mostly configuration and protects everything else while the rest is built.

## Done means

- A token from a real upload link and a real event-edit link cannot be found in staging logs after use.
- An event-edit link opened yesterday is rejected today.
- An admin token older than 12 hours is rejected.
- A 1,000-name lookup from an anonymous client is refused, and a request full of made-up card names causes at most a few outbound calls.
- Every page type loads with no CSP violations in the browser console.
- CI runs the two audits; the container runs as non-root on staging and can write to `/data`.
- An event deleted on staging is restored from the Settings page with its decks, matchups and emails intact.
- A deck whose player name was corrected by hand keeps the correction after a forced re-scrape of its event.
- One database restore into staging has been performed and the runbook exists.
- Both test suites, lint and the route index check pass.
