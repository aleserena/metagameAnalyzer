# Security operations

Short operating notes for the person running the site. Design background: `docs/superpowers/specs/2026-11-11-security-hardening-and-recovery-design.md`.

## Admin sessions

- Logging in returns a token that is valid for **12 hours** (`JWT_EXP_SECONDS` in `api/dependencies.py`). After that the next admin action returns to the login page with "Your session expired".
- The token is kept in the browser's `localStorage`. Use the admin side only from a browser profile you trust.
- There is one admin password (`ADMIN_PASSWORD`) and no second factor. Use a long random password from a password manager.

## Logging everyone out

Change `JWT_SECRET` in the Railway service variables and redeploy. Every existing admin session stops working immediately. Feedback-form captchas issued before the change also stop working; visitors simply get a new one.

Do this if the admin password or a session token may have leaked. Change `ADMIN_PASSWORD` at the same time.

## Upload, feedback and event-edit links

- A link that has not been opened expires after **7 days** (`DEFAULT_LINK_EXPIRY_DAYS`).
- Deck upload and feedback links stop working once the form is submitted.
- An event-edit link is meant for one sitting. Once opened it keeps working for **12 hours** (`EVENT_EDIT_SITTING_HOURS`), never longer than its original expiry. If an organiser comes back later, send a new link.
- Link tokens are masked in the request log (`/upload/***`, `/event-edit/***`). Treat a link like a password anyway: send it only to the person who needs it.
- To cancel links early, delete them on the Settings page.

## Single instance

The login throttle, the feedback throttle and the captcha replay store live in the API process memory. They reset on restart and are not shared between replicas. Run **one replica**; move these to the database before scaling out.

## Dependencies

- Dependabot (`.github/dependabot.yml`) opens weekly update PRs against `staging` for Python, the frontend, GitHub Actions and the Docker base images. `requirements*.txt` are generated, so after merging a Python update run `npm run deps:compile`.
- CI fails on a known vulnerability in `requirements.txt` (`pip-audit`) or a high-severity one in the frontend's runtime dependencies (`npm audit --omit=dev --audit-level=high`).
- Turn on **secret scanning**, **push protection** and **Dependabot alerts** in the GitHub repository settings (Code security).

## Accepted risks

- **The container runs as root.** Railway mounts volumes as root, so a non-root user cannot write to `DATA_DIR` (`/data`). Revisit if the app stops needing a volume.
