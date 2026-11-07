# BolBazaar — Security Implementation Guide

What is implemented in the project for security, how each part works, where it lives and which setting controls it.
All paths are under `backend/src/bolbazaar/` unless stated. Every limit is an environment variable (see `.env.example`).
Convention: a limit of `0` means **blocked**, never "unlimited".

## 1. How a request is protected (end to end)

```
Client
  │
  ▼ guard.py  GuardMiddleware (before any body is read)
  │   1. resolve client IP            4. security headers on every response
  │   2. per-IP rate limits           5. 429 / 413 rejected here, before routing
  │   3. body-size limit (Content-Length + streamed byte count)
  ▼ CORS (explicit origins, no credentials)
  ▼ api/deps.py  get_principal
  │   JWT verified → per-user rate limit → user loaded from DB (active? role? org?)
  ▼ route (role check, pydantic validation: extra fields forbidden, length caps)
  ▼ service (ownership / territory checks)
  ▼ costguard.py  — only for paid operations
  │   in-flight slot → kill switch → breaker → atomic quota reservation
  │   → provider slot → provider call (timeout, bounded retries) → record usage
  ▼ Gnani / Azure OpenAI
```
Validation that costs nothing (size, type, magic bytes, duration, text length) always runs **before** quota is reserved, and quota is always reserved **before** a provider is called.

## 2. Credit protection (Gnani + Azure)

### 2.1 Atomic quota ledger — `costguard.py`, table `usage_counters`
- Each counter is a row `(scope, metric, window)` with `used`. Scopes: `user:<id>`, `global`, `capture:<id>`.
- Windows are fixed UTC buckets: minute (`m:`), hour (`h:`), day (`d:`), or lifetime (`life`).
- A reservation is **one SQL statement per counter**:
  `INSERT … ON CONFLICT DO UPDATE SET used = used + n WHERE used + n <= limit RETURNING used`.
  If no row comes back, the limit would be exceeded and the request is refused.
- All counters for one reservation (user minute/hour/day, units, global minute/day, global units) share **one transaction**. If any refuses, all roll back, so a refusal never leaves a partial charge.
- Because the check and the increment are the same statement, 50 simultaneous requests with 5 units left produce exactly 5 winners. Proven on SQLite and PostgreSQL 16, across two independent instances.
- No refunds after a provider call was attempted (the provider may have billed it, and refunds would let a client loop for free).
- Fail closed: if the database cannot be read or written, or the dialect is unsupported, the request gets 503 `QUOTA_UNAVAILABLE` and the provider is **not** called.

### 2.2 What is metered
| Operation | Per user | Global (all users) |
|---|---|---|
| STT (Gnani) | 8/min, 60/h, 120/day requests; 3600 audio-seconds/day | 30/min; `GNANI_DAILY_CALL_BUDGET` per day (200); 7200 audio-s/day |
| TTS (Gnani) | 6/min, 40/h, 80/day; 15 000 chars/day; 600 chars per request | 60 000 chars/day (shares the Gnani request ceilings) |
| LLM (Azure) | 12/min, 100/h, 250/day; 400 000 estimated tokens/day | 60/min; 800/day; 1 500 000 estimated tokens/day |
| Sign-ups | – | 300/day |
| One capture | 4 processing attempts in its lifetime | – |

`est_tokens` is a heuristic (about 3 characters per token plus 600 output tokens). Azure's real `usage.total_tokens` is stored separately as `actual_tokens` for monitoring. No currency cost is computed because no price list was provided.

### 2.3 Kill switches
- Env flags: `AI_SERVICES_ENABLED`, `GNANI_ENABLED`, `AZURE_ENABLED` (need a restart).
- **Runtime switch**, no redeploy: `PUT /v1/admin/providers/{gnani|azure|all}` with `{"enabled": false, "reason": "…"}`. Stored in table `provider_switches`, cached for about 2 s per process, admin role only, written to `audit_log`.
- A disabled provider returns 503 `PROVIDER_DISABLED` and is never contacted. Features that do not need it keep working (for example text captures still work with Gnani off).
- If the switch table cannot be read, the guard treats the provider as disabled.

### 2.4 Circuit breaker (per provider, per process)
- Opens after 5 consecutive health failures (network, 5xx, 429, config) for 60 s, doubling up to 15 min.
- Opens immediately for auth or credit errors (401/402/403 class) for 15 min, so a drained or revoked key is not hammered.
- After the cool-down it is half-open and lets exactly one trial call through; success closes it, failure re-opens it.
- Bad audio or an empty transcript do not count as provider failures.

### 2.5 Concurrency and queueing
- Per user: at most `USER_MAX_CONCURRENT_AI` (2) paid operations in flight; extra requests get 429 `CONCURRENCY_LIMIT` immediately and reserve nothing.
- Per provider: Gnani `GNANI_MAX_CONCURRENT_REQUESTS` (1), Azure `AZURE_MAX_CONCURRENT_REQUESTS` (4). A waiter blocks at most `QUEUE_WAIT_SECONDS` (3 s) and then gets 503 `PROVIDER_BUSY`. This replaced an unbounded wait that could occupy every worker thread.
- ffmpeg conversions: 2 at a time, 3 s wait, 30 s timeout.

### 2.6 Retries and duplicate execution
- `providers/gnani.py`, `providers/azure.py`: retries are hard-capped at 3 whatever the config says; only 429, 5xx and network errors are retried; exponential back-off with jitter; every HTTP attempt (retries included) is charged to a per-process daily budget (`GNANI_DAILY_CALL_BUDGET`, `AZURE_DAILY_CALL_BUDGET`); Azure output is capped by `AZURE_MAX_OUTPUT_TOKENS` (2048).
- `services/captures.py` `_claim`: processing starts with `UPDATE captures SET state=… WHERE id=… AND state IN ('RECORDED','FAILED')`. Of N simultaneous `/retry` or same-key `POST /captures`, exactly one wins and pays; the rest return the current view.
- A capture can be processed at most `MAX_PROCESS_ATTEMPTS_PER_CAPTURE` (4) times (429 `TOO_MANY_ATTEMPTS`).
- Idempotency keys (existing) still make the same key plus same content a no-op.
- Striped locks make concurrent confirms or identical question-audio requests pay for TTS once; results are cached.

### 2.7 Input limits that prevent paid abuse
- Transcript text 4000 chars (413 `TEXT_TOO_LONG`), corrections 500, manager question 400, TTS text 600 (truncated), query strings 80, pagination capped.
- Audio: byte limit (`MAX_AUDIO_BYTES`, enforced by the middleware before parsing), duration limit (`MAX_AUDIO_SECONDS`), declared type/extension **and** magic bytes (`audio.looks_like_audio`), so junk and scripts never reach ffmpeg or a provider.
- ffmpeg decode is bounded with `-t` (max seconds + 2) so a small compressed file cannot expand into gigabytes of PCM.
- Audio files are purged every 10 minutes on upload, not only at start-up (`AUDIO_RETENTION_HOURS`).

### 2.8 Monitoring
- `GET /v1/admin/usage`: today's global counters against ceilings, top users, breaker state, switches.
- Log events (no keys, transcripts or audio): `budget_warning` at 80 %, `provider_budget_exhausted`, `circuit_open`, `quota_ledger_unavailable`, `provider_switch`, `security_config`.

## 3. Account and abuse controls

| Control | How it works | Where |
|---|---|---|
| Per-IP request limit | Sliding window, 240/min across `/v1`; 429 + `Retry-After` | `guard.py` |
| Login limits | 20/min/IP; 8 attempts per 15 min per account (charged **before** the password check so parallel guesses cannot slip past, cleared on success); 30 failures per 15 min per IP. A throttled account refuses even the right password | `guard.py`, `api/routes.py` `login` |
| Sign-up limits | 5/hour/IP, 300/day global (database), optional `REP_SIGNUP_CODE`, manager code `MANAGER_SIGNUP_CODE` (constant-time compare), role limited to rep/manager | `guard.py`, `services/accounts.py` |
| Bug reports | Any signed-in user may file one; 10/day per user and 500/day global (database counters); lengths capped; context is a whitelist (unknown keys refused, query strings stripped, no tokens); users read only their own reports; only admins list or triage; stored text is returned as JSON and rendered escaped by React | `services/bugs.py`, `api/routes.py` |
| Per-user request limit | 120/min after the token is verified | `api/deps.py` |
| Client IP | `X-Forwarded-For` ignored unless `TRUSTED_PROXY_COUNT` > 0; then only the entry appended by the trusted proxy (counted from the right) is used, so a client cannot choose its own. IPv6 grouped by /64 | `guard.client_ip` |
| Memory safety | Limiter keys are hashed and capped at 50 000 entries | `guard.SlidingWindowLimiter` |

The limiter and in-flight counters are **per process**. The quotas, global ceilings, sign-up cap, attempt cap and kill switches are in the database and are shared.

## 4. Authentication and authorization

- **Passwords:** PBKDF2-SHA256 with a per-user salt, iteration count stored in each hash, constant-time compare. Unknown users are verified against a real hash of production cost (`security.dummy_hash`), so timing does not reveal whether a username exists. Login responses are identical for unknown user and wrong password.
- **JWT:** HS256, 12 h TTL. Decoding requires `exp`, `iat`, `sub`, `org`, `role`; algorithm is pinned (so `alg=none` and wrong keys fail).
- **Secret policy (`config.py`):** outside development `JWT_SECRET` is required and must be at least 32 characters. In development with no secret, a random per-process secret is generated (the old public default is gone, so nobody can forge tokens against a LAN-reachable dev server).
- **Database is the source of truth (`api/deps.py`):** every request loads the user; a deactivated user or changed role/org takes effect immediately instead of when the token expires. A token claiming `admin` for a rep is still 403.
- **Roles:** `RepDep`, `ManagerDep` (manager, admin), `AdminDep` (admin) are enforced on the backend for every route; the OpenAPI schema is tested to confirm every route except login, register, territories and health returns 401 without a token.
- **Object-level access:** captures are loaded with org and owner checks (404 for other reps' captures, 403 for writes by non-owners); visits, orders, commitments and customers are scoped by owner or territory in `services/records.py`.
- **Mass assignment:** every request body model is `extra="forbid"`; privileged fields cannot be sent.
- **Idempotency and revision checks** (existing) protect writes from duplication and stale edits; business tables change only in `_commit` after validation. AI output only proposes.

## 5. Transport, headers, CORS, information exposure

- Headers on every response (`guard.py`): `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-site`, `Permissions-Policy`, `Cache-Control: no-store`, `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, and `Strict-Transport-Security` outside development.
- CORS (`main.py`): only origins in `CORS_ORIGINS`, only needed methods and headers, no credentials header; exposes `X-Request-Id` and `Retry-After`. Auth is a bearer header, so CSRF does not apply.
- `/docs`, `/redoc`, `/openapi.json` are served only when `APP_ENV=development` (or `EXPOSE_DOCS=true`); `/health` omits provider wiring outside development.
- Errors use one envelope and never include stack traces, keys, provider bodies or SQL; provider errors are sanitised (`ProviderError`).
- Request bodies: 256 KB for JSON, audio limit plus 1 MB only on the two audio routes, checked from `Content-Length` and by counting streamed bytes (413 before parsing).

## 6. Input handling and injection

- SQLAlchemy ORM with bound parameters everywhere; `q` is length-capped and used only inside parameterised `ILIKE`.
- ffmpeg is run with an argument list and data on stdin (no shell). Storage keys are server-generated and `AudioStore._path` rejects traversal.
- Provider URLs come from server configuration only (no user-controlled URLs, no SSRF).
- LLM output is schema-constrained (strict JSON schema), validated again by domain rules, and never executes tools or SQL; the manager assistant only selects a named intent mapped to fixed queries. Prompts contain only the caller's own catalogue.

## 7. Secrets and configuration safety

- Provider keys live only in environment variables and are used only inside the two provider clients; they never appear in responses, logs, the web bundle or the Android build (scanned).
- `.env` files are git-ignored. `.env.example` documents every setting without secrets.
- `Settings.warnings()` logs risky combinations at start-up: public demo password, live providers with demo accounts on a non-loopback host, open sign-up with live providers, `TRUSTED_PROXY_COUNT=0` behind a proxy, AI disabled.
- `DEMO_PASSWORD` sets the seeded accounts' password (default is still the public `demo123`, so set it on any shared deployment).

## 8. Tests that prove it (`backend/tests/security/`, 98 tests)

| File | Covers |
|---|---|
| `test_credit_protection.py` | The ten credit scenarios: request spam, 50-way concurrent quota, multi-account abuse, duplicates, global ceiling and breaker, timeouts and retry caps, bad audio and text, disabled providers, missing auth, quota-store failure |
| `test_auth_and_api.py` | Unauthorized access, JWT forgery and tampering, deactivation and demotion, IDOR, privilege escalation, mass assignment, brute force, enumeration and timing, rate limits and proxy-header spoofing, injection, XSS, traversal, headers, CORS, docs/health exposure |
| `test_ledger_and_baseline.py` | Window roll-over, isolation, all-or-nothing reservation, no refunds, unit limits, concurrency bounds, atomicity on SQLite and PostgreSQL, ffmpeg cap, magic bytes, and **baseline** tests that show the original drain and duplicate-charge behaviour with protections off |

Run: `cd backend && .venv/Scripts/python.exe -m pytest` (178 pass, 1 skipped). Set `SECTEST_PG_URL=postgresql+psycopg://user:pw@host:port/db` to include the PostgreSQL atomicity test. The security fixtures use mocked providers that count every billable call and a frozen ledger clock, so nothing can spend credits and window boundaries cannot make tests flaky.

## 9. What is not covered

Per-process request limiter with several instances, CAPTCHA/email verification (the app has no email), CAPTCHA-free sign-up for strangers unless `REP_SIGNUP_CODE` is set, provider-side budgets (Azure/Gnani consoles), manager scope on captures, PBKDF2 iteration count, and the items in `SECURITY_REMEDIATION_PLAN.md`.
