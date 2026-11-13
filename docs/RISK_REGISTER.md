# Risk register

The security risks identified for this project, how each is treated, and what remains. It follows the ISO 31000 cycle: identify, analyse, evaluate, treat, then monitor and review.

- **First assessment:** 2026-11-11 (static review of the code and the Railway setup).
- **Last updated:** 2026-11-13, after the hardening and recovery work.
- **Owner:** the site maintainer (the only admin).
- **Review:** after any release that touches authentication, one-time links, the public endpoints or how data is stored, and at least once a year. Re-rate each risk, add new ones, and record the date above.

Ratings are Low / Medium / High for likelihood (L) and consequence (C). "Level before" is the rating at the first assessment; "Level now" is the rating with the treatment in place.

## Register

| # | Risk | Level before | Treatment | Level now | Status |
|---|---|---|---|---|---|
| R1 | Admin credential compromise | High | Reduced | Medium | Treated, residual accepted |
| R2 | Link tokens leak through logs or outlive their use | High | Reduced | Low | Treated |
| R3 | Anonymous visitors exhaust the server or get it blocked by Scryfall | High | Reduced | Low | Treated |
| R4 | No recovery from destructive actions or database loss | Medium | Reduced | Low | Treated |
| R5 | Personal-data handling without notice or a removal process | Medium | Reduced | Low | Treated |
| R6 | Supply chain and change control | Medium | Reduced | Medium | Partly treated |
| R7 | No browser hardening headers | Medium | Reduced | Low | Treated |
| R8 | Data sources withdraw access | Medium | Accepted | Medium | Accepted |
| R9 | Production secrets on the maintainer's machine | Medium | Accepted | Medium | Accepted |
| R10 | Minor information exposure | Low | Reduced | Low | Treated |

## Detail

### R1 — Admin credential compromise

One password grants every destructive action.

- **Done:** session shortened from 7 days to 12 hours; a "session expired" notice; the login throttle verified against a forged visitor address on Railway (2026-11-12); changing `JWT_SECRET` documented as the way to log everyone out; the app refuses to start on Railway without `JWT_SECRET` and `ADMIN_PASSWORD`.
- **Accepted residual:** a single shared password with no second factor and no per-person accounts. Reasonable while there is one admin using one computer. Revisit if a second person needs admin access.
- **Accepted residual:** the session token is kept in the browser's `localStorage`; the content security policy (R7) is what limits a script from reading it.

### R2 — Link tokens

Upload, feedback and event-edit links are bearer secrets carried in the URL.

- **Done:** tokens masked in the request log; database error text no longer includes query values; an opened event-edit link stays valid for 12 hours instead of 7 days; `Referrer-Policy: no-referrer` keeps tokens out of Referer headers.
- **Residual:** Railway's own edge logs record full URLs and are outside the app's control. Treat a link like a password.

### R3 — Resource exhaustion

- **Done:** card lookup capped at 200 names per request; anonymous callers get the card table and cache plus a small budgeted Scryfall fallback (5 names per request, 6 requests per minute per address, 30 per minute site-wide); per-address rate limits on the public upload and lookup endpoints.
- **Residual:** deck, player and metagame analysis pages still use the unlimited fallback for card names stored in decks. Exposure is low: it needs a valid link to store an unknown name, and misses are cached for 7 days.
- **Residual:** the limiters live in process memory, so the app must run as one replica.

### R4 — Recovery

- **Done:** Railway point-in-time recovery on the staging and production databases (about four weeks), with a restore drill on staging (2026-11-12); automatic event snapshots before delete, merge, Hadouken import, clear-decks and re-scrape, restorable from the Settings page; a change log of every data change; hand-edited fields survive a re-scrape. Runbook: `docs/BACKUP_RESTORE.md`.
- **Residual:** loading a deck file over existing decks takes no snapshot; undoing a merge takes two restores; corrections made before the feature shipped are not protected.
- **Monitor:** check `railway postgres pitr status` monthly and repeat the drill after a Postgres or plan change.

### R5 — Personal data

Player names and results come from public tournament pages; emails are added by the admin to send links.

- **Done:** a Privacy page on the site; a written removal procedure (`docs/PRIVACY_REQUESTS.md`); emails are never public, never in exports for non-admins, never in the change log, and kept out of GitHub issues.
- **Residual:** the player-aliases list is public and shows name variants. Removed data persists in backups for about four weeks and in snapshots for up to 90 days.

### R6 — Supply chain and change control

- **Done:** Dependabot for Python, the frontend, GitHub Actions and Docker; `pip-audit` and `npm audit` in CI; dependencies pinned.
- **Open (maintainer action):** turn on GitHub secret scanning, push protection and Dependabot alerts in the repository settings.
- **Accepted residual:** work is committed directly to `staging` without a second reviewer, and git hooks can be bypassed; CI is the gate. The container runs as root because Railway mounts volumes as root.
- **Watch:** Railway stops reading `railway.json` on 2026-12-01. The deploy settings were copied onto the Railway service on 2026-11-13; confirm the first deploy after the cutoff still runs the migration and the health check.

### R7 — Browser hardening

- **Done:** Content-Security-Policy, HSTS, `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy` on every response; the policy was checked in a browser against 18 page types.
- **Residual:** admin pages while logged in and card-hover popups were not part of that browser check. If something fails to load after a frontend change, set `CSP_REPORT_ONLY=1` while fixing the policy.

### R8 — Data sources

The site depends on scraping mtgtop8.com, on Moxfield's unofficial API, on Scryfall and on a league site.

- **Accepted:** no agreement with any of them. If one blocks access, the affected feature stops; stored data is unaffected. Scrape politely (one worker by default) and keep the MTGJSON card data synced so Scryfall is rarely needed.

### R9 — Production secrets on a developer machine

- **Accepted:** `.env.prod` on the maintainer's computer allows scripts to run against production. Maintenance scripts print their target database before acting. Keep the disk encrypted and the file out of backups that leave the machine.

### R10 — Minor information exposure

- **Done:** interactive API docs are not served when deployed; the feedback form no longer echoes GitHub's error text; a startup warning if `PUBLIC_APP_URL` is missing.

## Opportunities noted in the assessment

| Opportunity | Status |
|---|---|
| Audit trail as a feature (change history, undo) | Done: change log and event snapshots |
| Organiser self-service through hardened links | Done: links hardened; organisers keep editing through them |
| A written security policy and a repeatable review | Done: `SECURITY.md` and this register |
| Per-user admin accounts | Not pursued: one admin today |
| Agreements with data sources | Not pursued |
