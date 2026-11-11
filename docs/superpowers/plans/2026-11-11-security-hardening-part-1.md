# Security Hardening — Part 1 (Quick Hardening) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make leaked link and session tokens short-lived and invisible in logs, stop anonymous visitors from exhausting the server, and add browser and supply-chain protections.

**Architecture:** Small, independent changes to the existing FastAPI app: a path-masking helper used by the request logger, a shortened expiry written when an event-edit link is first opened, a capped card lookup with a bounded Scryfall fallback, a reusable rate-limit dependency, and one response-headers middleware. No schema change. Frontend changes are limited to batching card lookups and a "session expired" message.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / pytest; React + TypeScript / Vitest; GitHub Actions; Docker; Railway.

**Spec:** `docs/superpowers/specs/2026-11-11-security-hardening-and-recovery-design.md` (Part 1 only — sections 1.1 to 1.8). Parts 2 and 3 get their own plans.

## Global Constraints

- Follow `CLAUDE.md`. Use `python3`, not `python`. Use `db.utcnow_naive()` for timestamps.
- No database migration in this plan.
- Commit directly on `staging`, one commit per task. No feature branches, no PRs.
- No new frontend styling system: inline styles or existing classes in `web/src/style.css`.
- After any route change run `npm run gen:routes`.
- An organiser who opens a link and works in one sitting must notice no difference.
- Every page that shows cards today must still show them.
- Exact values from the spec: admin session **12 hours**; opened event-edit link **12 hours**; unopened links keep the **7-day** default.
- Before each commit: `npm run lint`. Before finishing the plan: `python3 -m pytest`, `cd web && npx vitest run`, `cd web && npm run build`, `npm run gen:routes:check`.

## Review Focus

Conditions the spec implies but does not spell out, most likely first. Each has a test in the task named.

1. **Many players at one venue share an IP** and submit decks within the same few minutes. They must not be rate limited. (Task 6)
2. **A deck page with more unique card names than the lookup cap.** Every card must still get its image; the frontend splits the request. (Task 5)
3. **An event-edit link whose own expiry is sooner than 12 hours.** Opening it must not extend its life. (Task 2)
4. **An organiser keeps working after opening the link.** The token must keep authorising edits for the rest of the sitting, even though the link is marked used. (Task 2)
5. **A token followed by more path** (`/upload/<token>/feedback`). Only the token is masked; the rest of the path stays readable for debugging. (Task 1)

---

### Task 1: Keep link tokens out of the request log

**Files:**
- Modify: `api/logging_config.py` (add helper next to `redact_secrets`)
- Modify: `api/main.py:122-164` (`log_requests`) and `api/main.py:167-184` (`unhandled_exception_handler`)
- Test: `tests/test_logging_alerts.py`

**Interfaces:**
- Produces: `mask_link_tokens(path: str) -> str` in `api/logging_config.py`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("raw,expected", [
    ("/api/v1/upload/AbC-123_x", "/api/v1/upload/***"),
    ("/api/v1/upload/AbC-123_x/feedback", "/api/v1/upload/***/feedback"),
    ("/api/v1/upload/AbC-123_x/decklist", "/api/v1/upload/***/decklist"),
    ("/api/v1/event-edit/AbC-123_x", "/api/v1/event-edit/***"),
    ("/upload/AbC-123_x", "/upload/***"),
    ("/api/v1/decks/42", "/api/v1/decks/42"),
    ("/api/v1/settings/upload-links", "/api/v1/settings/upload-links"),
])
def test_mask_link_tokens(raw, expected):
    assert mask_link_tokens(raw) == expected


def test_request_log_never_contains_link_token(caplog):
    caplog.set_level(logging.INFO)
    TestClient(app).get("/api/v1/upload/SECRET-TOKEN-VALUE")
    assert "SECRET-TOKEN-VALUE" not in caplog.text
    assert all("SECRET-TOKEN-VALUE" not in str(getattr(r, "path", "")) for r in caplog.records)
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_logging_alerts.py -k "mask_link or never_contains" -v` — expected: FAIL (`mask_link_tokens` not defined).

- [ ] **Step 3: Implement `mask_link_tokens`** as one regex substitution: the segment after `/upload/` or `/event-edit/` becomes `***`. The pattern must require a `/` before `upload` so `/settings/upload-links` is untouched.

- [ ] **Step 4: Use it in `api/main.py`** for every place `request.url.path` is logged: the message and the `path` extra in `log_requests`, and both in `unhandled_exception_handler`.

- [ ] **Step 5: Run** the same pytest command — expected: PASS. Then `python3 -m pytest tests/test_logging_alerts.py -v` — all pass.

- [ ] **Step 6: Commit** — `git commit -m "fix(security): mask upload and event-edit tokens in request logs"`

---

### Task 2: Event-edit links close 12 hours after first open

**Files:**
- Modify: `api/db.py` (near `mark_upload_link_used`, ~line 872; constant near `DEFAULT_LINK_EXPIRY_DAYS`)
- Modify: `api/routers/upload.py:173-183` (`get_event_edit_link_info`) and the `mark_used` branch of `_get_validated_upload_link`
- Test: `tests/test_db_upload_links.py`, `tests/test_api.py`

**Interfaces:**
- Produces: `EVENT_EDIT_SITTING_HOURS = 12` and `mark_upload_link_used(session, token: str, *, sitting_hours: int | None = None) -> bool` in `api/db.py`. With `sitting_hours`, `expires_at` becomes the earlier of its current value and `utcnow_naive() + sitting_hours`; a NULL `expires_at` is treated as "no limit" and gets the sitting window.

Context: after the link is opened the frontend keeps the token in `sessionStorage` and sends it as `X-Event-Edit-Token`. `require_admin_or_event_edit*` in `api/dependencies.py` check only `expires_at`, so shortening `expires_at` is the whole mechanism. Do not add a `used_at` check there.

- [ ] **Step 1: Write the failing DB tests** in `tests/test_db_upload_links.py` (use the existing `db_session_rollback` fixture and the file's existing link-creation pattern):

```python
def test_sitting_window_shortens_a_seven_day_link(db_session_rollback):
    # link created with default expiry (7 days)
    db.mark_upload_link_used(session, token, sitting_hours=12)
    remaining = row.expires_at - db.utcnow_naive()
    assert timedelta(hours=11, minutes=59) < remaining <= timedelta(hours=12)
    assert row.used_at is not None


def test_sitting_window_never_extends_a_shorter_link(db_session_rollback):
    soon = db.utcnow_naive() + timedelta(hours=1)
    # link created with expires_at=soon
    db.mark_upload_link_used(session, token, sitting_hours=12)
    assert row.expires_at == soon


def test_mark_used_without_sitting_hours_leaves_expiry_alone(db_session_rollback):
    before = row.expires_at
    db.mark_upload_link_used(session, token)
    assert row.expires_at == before
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_db_upload_links.py -k sitting -v` — expected: FAIL (unexpected keyword `sitting_hours`). Needs `TEST_DATABASE_URL`; without it the tests skip, which is not a pass.

- [ ] **Step 3: Implement** the constant and the new keyword in `api/db.py`.

- [ ] **Step 4: Wire it in** `api/routers/upload.py`: `_get_validated_upload_link` gains `sitting_hours: int | None = None`, passed through to `mark_upload_link_used` when `mark_used` is true; `get_event_edit_link_info` passes `sitting_hours=_db.EVENT_EDIT_SITTING_HOURS`. Other callers are unchanged.

- [ ] **Step 5: Write the API tests** in `tests/test_api.py`, next to the existing `client_as_event_editor` tests:

```python
def test_event_edit_token_still_works_after_link_is_opened(...):
    # open GET /api/v1/event-edit/{token} -> 200
    # PUT /api/v1/events/{event_id} with X-Event-Edit-Token -> not 401


def test_event_edit_token_rejected_once_sitting_window_has_passed(...):
    # open the link, then set row.expires_at to one minute ago
    # PUT /api/v1/events/{event_id} with X-Event-Edit-Token -> 401, detail "Event edit link expired"
```

- [ ] **Step 6: Run** `python3 -m pytest tests/test_db_upload_links.py tests/test_api.py -k "sitting or event_edit" -v` — expected: PASS.

- [ ] **Step 7: Commit** — `git commit -m "fix(security): event-edit links expire 12 hours after first open"`

---

### Task 3: Admin session lasts 12 hours, with a clear expiry message

**Files:**
- Modify: `api/dependencies.py:37` (`JWT_EXP_SECONDS`)
- Modify: `web/src/api.ts:45-48` and `:68-71` (the two 401 branches)
- Modify: `web/src/pages/Login.tsx`
- Create: `docs/SECURITY_OPERATIONS.md`
- Modify: `.env.example` (the `JWT_SECRET` comment), `CLAUDE.md` (Environment section)
- Test: `tests/test_api.py`, `web/src/api.test.ts`

**Interfaces:**
- Produces: `sessionStorage` key `session_expired` (value `'1'`), set by `api.ts` when a 401 arrives **and** an `admin_token` was present; read and removed by `Login.tsx`.

- [ ] **Step 1: Write the failing backend test**

```python
def test_admin_token_lifetime_is_twelve_hours():
    from api import dependencies as deps
    assert deps.JWT_EXP_SECONDS == 12 * 3600
    claims = jwt.decode(deps._create_admin_token(), deps._JWT_KEY, algorithms=[deps.JWT_ALGORITHM])
    assert 0 < claims["exp"] - time.time() <= 12 * 3600
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_api.py -k twelve_hours -v` — FAIL. Change the constant. Run again — PASS.

- [ ] **Step 3: Write the failing frontend test** in `web/src/api.test.ts`: with `localStorage.admin_token` set and `fetch` mocked to return 401, calling any `fetchApi`-based function leaves `sessionStorage.getItem('session_expired') === '1'` and removes `admin_token`; with no `admin_token` set, a 401 does **not** set `session_expired`.

- [ ] **Step 4: Run** `cd web && npx vitest run src/api.test.ts` — FAIL. Implement in both 401 branches of `api.ts` (extract one small shared function rather than duplicating). Run again — PASS.

- [ ] **Step 5: Show the message.** In `Login.tsx`, on mount, if `session_expired` is set, remove it and show exactly: `Your session expired. Log in again to continue.` Use the page's existing notice/error styling.

- [ ] **Step 6: Write `docs/SECURITY_OPERATIONS.md`** with these sections, a few lines each: *Admin sessions* (12-hour lifetime; token lives in the browser's localStorage); *Logging everyone out* (change `JWT_SECRET` in Railway and redeploy — this also invalidates outstanding feedback captchas); *Edit links* (7 days unopened, 12 hours once opened; issue a new link if an organiser returns later); *Single instance* (login and feedback throttles and the captcha replay store are in memory — do not run more than one replica without moving them to the database). Update the `.env.example` comment and the `CLAUDE.md` Environment bullet to say 12 hours.

- [ ] **Step 7: Commit** — `git commit -m "fix(security): 12-hour admin session with expiry notice"`

---

### Task 4: Confirm the login throttle cannot be sidestepped

**Files:**
- Modify: `api/services/rate_limit.py:67-72` (`client_ip`)
- Test: `tests/test_rate_limit.py`

This task starts with a measurement on **staging**; the code change depends on the result. Task 1 must be deployed to staging first.

- [ ] **Step 1: Measure.** Send `curl -s -H "X-Real-IP: 203.0.113.9" -H "X-Forwarded-For: 203.0.113.9" https://<staging-host>/api/v1/info`, then read the staging request log line for `/api/v1/info` and note its `client_ip`. To see the raw headers the app received, temporarily log `request.headers.get("x-real-ip")` and `x-forwarded-for` at DEBUG on staging if the log line alone is not conclusive; remove that logging afterwards.

- [ ] **Step 2a — if the logged `client_ip` is your real address** (Railway overwrote the forged header): change no behaviour. Extend the `client_ip` docstring with one sentence stating that Railway's edge overwrites a client-supplied `X-Real-IP`, with the date verified. Skip to Step 4.

- [ ] **Step 2b — if the logged `client_ip` is `203.0.113.9`** (the forged value won): write the failing test, then fix.

```python
def test_client_ip_ignores_a_forged_real_ip_header():
    # request with X-Real-IP: 203.0.113.9 and X-Forwarded-For: "203.0.113.9, 198.51.100.7"
    assert client_ip(request) == "198.51.100.7"
```

Implement: take the **last** entry of `X-Forwarded-For` (the one appended by the edge), falling back to the socket peer. If Step 1 showed that Railway does not append to `X-Forwarded-For` either, stop and report the observed headers instead of guessing.

- [ ] **Step 3: Run** `python3 -m pytest tests/test_rate_limit.py -v` — PASS (update `test_client_ip_prefers_x_real_ip` only if 2b applied).

- [ ] **Step 4: Commit** — `git commit -m "fix(security): verify client IP source for rate limiting"` and record the measured result in the commit body.

---

### Task 5: Cap the public card lookup and bound its Scryfall fallback

**Files:**
- Modify: `src/mtgtop8/card_lookup.py:381-420` (`lookup_cards`)
- Modify: `api/schemas/auth_feedback.py:20-21` (`CardLookupBody`)
- Modify: `api/routers/cards.py:18-23`
- Modify: `web/src/api.ts:225-231` (`getCardLookup`)
- Test: `tests/test_card_lookup.py`, `tests/test_api.py`, `web/src/api.test.ts`

**Interfaces:**
- Produces: `lookup_cards(card_names: list[str], *, strict: bool = False, max_fallback: int | None = None) -> dict[str, dict]`. `None` keeps today's behaviour. With a number, at most that many names missing from the `cards` table go to the Scryfall fallback; the remaining missing names are returned as `{"error": "not_found"}` and are **not** written to the not-found cache.
- Produces: `MAX_LOOKUP_NAMES = 200` and `PUBLIC_FALLBACK_NAMES = 5` in `api/routers/cards.py`.

Decision: the endpoint stays public. An admin (valid Bearer token, via `optional_admin`) gets the unlimited fallback; everyone else gets `PUBLIC_FALLBACK_NAMES`. All other `lookup_cards` callers are unchanged — they look up names already stored in decks.

- [ ] **Step 1: Write the failing library tests** in `tests/test_card_lookup.py` (patch `_scryfall_lookup_cards` and the table lookup as the existing tests in that file do):

```python
def test_max_fallback_limits_names_sent_to_scryfall(monkeypatch):
    # cards table knows nothing; 20 unknown names requested with max_fallback=5
    assert len(names_passed_to_scryfall) == 5
    assert all(result[n] == {"error": "not_found"} for n in the_other_15)


def test_names_over_the_fallback_limit_are_not_cached_as_not_found(monkeypatch):
    assert all(n not in card_lookup._card_cache for n in the_other_15)


def test_max_fallback_none_sends_every_missing_name(monkeypatch):
    assert len(names_passed_to_scryfall) == 20
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_card_lookup.py -k fallback -v` — FAIL. Implement. Run — PASS.

- [ ] **Step 3: Write the failing API tests** in `tests/test_api.py`:

```python
def test_card_lookup_rejects_more_than_200_names(client):
    r = client.post("/api/v1/cards/lookup", json={"names": [f"Card {i}" for i in range(201)]})
    assert r.status_code == 422


def test_card_lookup_accepts_200_names(client):  # lookup_cards patched
    assert r.status_code == 200


def test_anonymous_card_lookup_bounds_the_fallback(client, monkeypatch):
    # capture kwargs passed to lookup_cards
    assert captured["max_fallback"] == 5


def test_admin_card_lookup_has_unbounded_fallback(admin_client, monkeypatch):
    assert captured["max_fallback"] is None
```

- [ ] **Step 4: Run** — FAIL. Set `CardLookupBody.names` `max_length` to 200 and update the router. Run — PASS. Run `npm run gen:routes` (the auth column for the route may change).

- [ ] **Step 5: Write the failing frontend test** in `web/src/api.test.ts`: `getCardLookup` called with 450 distinct names makes 3 `fetch` calls with bodies of 200, 200 and 50 names and returns one merged object with 450 keys; called with 10 names it makes 1 call.

- [ ] **Step 6: Run** `cd web && npx vitest run src/api.test.ts` — FAIL. Implement batching inside `getCardLookup` (batch size constant `CARD_LOOKUP_BATCH = 200`, requests in parallel, results merged). No caller changes. Run — PASS.

- [ ] **Step 7: Commit** — `git commit -m "fix(security): cap public card lookup and bound its Scryfall fallback"`

---

### Task 6: Per-IP rate limit on public write endpoints

**Files:**
- Modify: `api/services/rate_limit.py`
- Modify: `api/routers/upload.py` (the four `/api/v1/upload/{token}…` routes), `api/routers/cards.py` (lookup)
- Modify: `tests/conftest.py:56-63` (reset fixture)
- Test: `tests/test_rate_limit.py`, `tests/test_api.py`

**Interfaces:**
- Produces, in `api/services/rate_limit.py`: `rate_limited(limiter: RateLimiter) -> Callable[[Request], None]` — a FastAPI dependency factory. The dependency raises `HTTPException(429, "Too many requests. Try again later.")` with a `Retry-After` header when `limiter.allow(ip)` is false, otherwise records the request.
- Produces: `UPLOAD_LIMITER = RateLimiter(120, 60)` in `api/routers/upload.py`; `LOOKUP_LIMITER = RateLimiter(600, 60)` in `api/routers/cards.py`.

The limits are deliberately loose: a whole tournament may submit from one venue IP, and a single deck page fires several lookups plus one per card hover.

- [ ] **Step 1: Write the failing tests**

```python
def test_rate_limited_dependency_blocks_and_sets_retry_after():
    limiter = RateLimiter(2, 60)
    dep = rate_limited(limiter)
    dep(request); dep(request)
    with pytest.raises(HTTPException) as exc:
        dep(request)
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) >= 1


def test_a_venue_of_players_on_one_ip_is_not_limited(client):
    # 100 requests to GET /api/v1/upload/<unknown-token> from one IP
    assert all(r.status_code != 429 for r in responses)


def test_upload_endpoint_returns_429_after_the_limit(client, monkeypatch):
    # monkeypatch UPLOAD_LIMITER.max_events = 3
    assert [r.status_code for r in four_responses][-1] == 429
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_rate_limit.py tests/test_api.py -k "rate_limited or venue or 429" -v` — FAIL.

- [ ] **Step 3: Implement** `rate_limited`, add it to `dependencies=[…]` of the five routes, and extend the autouse reset fixture in `tests/conftest.py` to reset both new limiters.

- [ ] **Step 4: Run** the same command — PASS. Run `npm run gen:routes`.

- [ ] **Step 5: Commit** — `git commit -m "feat(security): per-IP rate limit on public upload and lookup endpoints"`

---

### Task 7: Security headers, no public API docs, quieter errors

**Files:**
- Create: `api/security_headers.py`
- Modify: `api/config.py` (add `docs_kwargs`), `api/main.py` (app construction at line 94, new middleware, startup warning in `lifespan`)
- Modify: `api/routers/feedback.py:95-104`
- Modify: `.env.example`
- Test: `tests/test_security_headers.py` (new), `tests/test_config.py`, `tests/test_api.py`

**Interfaces:**
- Produces: `security_headers(*, deployed: bool, report_only: bool = False) -> dict[str, str]` in `api/security_headers.py`.
- Produces: `docs_kwargs(environ: Mapping[str, str] = os.environ) -> dict` in `api/config.py` — `{"docs_url": None, "redoc_url": None, "openapi_url": None}` when `is_deployed(environ)`, else `{}`.
- Env: `CSP_REPORT_ONLY=1` switches the CSP header name to `Content-Security-Policy-Report-Only`.

Starting policy (adjust in Step 5 from evidence, not guesswork):

```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
img-src 'self' data: https://cards.scryfall.io https://svgs.scryfall.io;
font-src 'self' data:; connect-src 'self'; frame-ancestors 'none';
base-uri 'self'; form-action 'self'; object-src 'none'
```

- [ ] **Step 1: Write the failing tests** in `tests/test_security_headers.py`:

```python
def test_headers_when_deployed():
    h = security_headers(deployed=True)
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer"
    assert h["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert "https://cards.scryfall.io" in h["Content-Security-Policy"]


def test_no_hsts_when_not_deployed():
    assert "Strict-Transport-Security" not in security_headers(deployed=False)


def test_report_only_switches_header_name():
    h = security_headers(deployed=True, report_only=True)
    assert "Content-Security-Policy-Report-Only" in h and "Content-Security-Policy" not in h


def test_every_response_carries_the_headers():
    r = TestClient(app).get("/api/v1/info")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
```

and in `tests/test_config.py`:

```python
def test_docs_disabled_when_deployed():
    assert docs_kwargs({"RAILWAY_ENVIRONMENT_NAME": "production"}) == {
        "docs_url": None, "redoc_url": None, "openapi_url": None}


def test_docs_enabled_locally():
    assert docs_kwargs({}) == {}
```

and in `tests/test_api.py`:

```python
def test_feedback_does_not_echo_github_error_text(client, monkeypatch):
    # GitHub responds 422 {"message": "Validation Failed: label does not exist"}
    assert r.status_code == 502
    assert r.json()["detail"] == "Could not create issue. Try again later."
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_security_headers.py tests/test_config.py tests/test_api.py -k "headers or docs_ or github_error" -v` — FAIL.

- [ ] **Step 3: Implement** `security_headers`, `docs_kwargs`, the middleware in `api/main.py` (headers computed once at import, applied to every response without overwriting a header a route already set), `FastAPI(..., **docs_kwargs())`, and the generic feedback message (keep the `logger.warning` with GitHub's text).

- [ ] **Step 4: Startup warning.** In `lifespan`, when `is_deployed()` and `PUBLIC_APP_URL` is empty, log at WARNING with `extra={"event": "public_app_url_missing"}`: `PUBLIC_APP_URL is not set: emailed links will be built from the request Host header`. Document `CSP_REPORT_ONLY` in `.env.example`.

- [ ] **Step 5: Verify the policy against the real frontend.** Run `cd web && npm run build`, then search the output for external origins: `grep -rhoE "https?://[a-zA-Z0-9.-]+" web/dist | sort -u`. Add to the policy only origins the app loads at runtime (images, fonts, scripts); links the user clicks need no entry. Then start the API with the built frontend and, with the browser console open, visit: home, an event, a deck, deck compare, metagame, an archetype, matchups, a player, a commander page, feedback, login, settings, scrape, and an upload-link page. Expected: zero CSP violation messages and every card image visible. If a violation cannot be resolved without `'unsafe-eval'` or a wildcard source, set `CSP_REPORT_ONLY=1` in Railway for now and say so in the commit body.

- [ ] **Step 6: Run** the pytest command from Step 2 — PASS. Run `npm run gen:routes:check`.

- [ ] **Step 7: Commit** — `git commit -m "feat(security): response security headers, hide API docs when deployed, generic feedback errors"`

---

### Task 8: Supply-chain checks and a non-root container

**Files:**
- Create: `.github/dependabot.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `Dockerfile`
- Test: `tests/test_deploy_config.py`

- [ ] **Step 1: Write the failing tests** in `tests/test_deploy_config.py` (same file-reading style as the existing tests there):

```python
def test_image_does_not_run_as_root():
    lines = [ln.strip() for ln in dockerfile_text.splitlines()]
    user_lines = [ln for ln in lines if ln.startswith("USER ")]
    assert user_lines and user_lines[-1] not in ("USER root", "USER 0")


def test_ci_audits_dependencies():
    assert "pip-audit" in ci_text
    assert "npm audit --omit=dev --audit-level=high" in ci_text


def test_dependabot_covers_all_ecosystems():
    ecosystems = {u["package-ecosystem"] for u in yaml_or_text_parsed_updates}
    assert ecosystems == {"pip", "npm", "github-actions", "docker"}
```

(If PyYAML is not installed, assert on the four `package-ecosystem: "<name>"` strings instead of parsing; do not add a dependency for this.)

- [ ] **Step 2: Run** `python3 -m pytest tests/test_deploy_config.py -v` — the three new tests FAIL.

- [ ] **Step 3: Add `.github/dependabot.yml`** — weekly, four entries: `pip` at `/`, `npm` at `/web`, `github-actions` at `/`, `docker` at `/`. Group minor and patch updates per ecosystem so it opens few PRs.

- [ ] **Step 4: Add the audits to CI.** Backend job, after install: `pip install pip-audit && pip-audit -r requirements.txt`. Frontend job, after `npm ci`: `npm audit --omit=dev --audit-level=high`. Run both locally first; if either reports existing findings, fix them with `npm run deps:compile` / `npm audit fix` in this task so the build starts green.

- [ ] **Step 5: Non-root user in the Dockerfile.** In the final stage, create a system user with a fixed uid (`10001`), `chown` `/app` to it, and add `USER 10001` before `CMD`. Keep the port and `CMD` unchanged.

- [ ] **Step 6: Run** `python3 -m pytest tests/test_deploy_config.py -v` — PASS. Build locally: `docker build -t mtg-test .` and `docker run --rm mtg-test id -u` — expected output `10001`.

- [ ] **Step 7: Verify on staging before production.** After pushing to `staging`, confirm in the staging logs that startup succeeded and that the deployment marker under `DATA_DIR` (`/data`, an existing root-owned volume) was written without a permission error. Expected: no `PermissionError`. If the volume is not writable by uid 10001, do **not** work around it with a root entrypoint: revert Step 5 only, keep the rest of the task, and report it so "container runs as root" goes into the risk register as an accepted risk with the reason.

- [ ] **Step 8: Commit** — `git commit -m "chore(security): dependabot, dependency audits in CI, non-root container"`

- [ ] **Step 9: Owner action (not code).** Tell the owner to enable, in the GitHub repository settings under *Code security*: secret scanning, push protection, and Dependabot alerts. Also ask them to confirm `PUBLIC_APP_URL` is set in both Railway environments.

---

## Final verification

- [ ] `npm run lint` — clean.
- [ ] `python3 -m pytest` with `TEST_DATABASE_URL` set — all pass, none of the new DB tests skipped.
- [ ] `cd web && npx vitest run` — all pass.
- [ ] `cd web && npm run build` — succeeds.
- [ ] `npm run gen:routes:check` — up to date.
- [ ] On staging, after using a real upload link and a real event-edit link: search the logs for each token — no match.
- [ ] On staging: `curl -sI https://<staging-host>/` shows the security headers; `curl -s -o /dev/null -w "%{http_code}" https://<staging-host>/docs` does not return API docs (the SPA shell is acceptable; a Swagger page is not).
