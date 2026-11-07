# BolBazaar — Security Audit Report

Audit date: 2026-11-08 · Scope: `BolBazaar/backend` (FastAPI), `BolBazaar/web` (React/Capacitor), deployment files.
Method: source review of the whole backend, local test-driven verification against mocked providers, secret scan, dependency scan.
No live Gnani or Azure call was made, no credits were spent, nothing was deployed, no credential was read into this report or modified.

## Verdict

**READY FOR CONTROLLED STAGING. NOT READY FOR PUBLIC RELEASE** until the five conditions in
[SECURITY_REMEDIATION_PLAN.md](SECURITY_REMEDIATION_PLAN.md#release-blockers) are met (demo password, sign-up gating,
proxy setting, provider-side spend caps, a staging pass against the real providers).
Code-level credit-drain and access-control gaps found in the audit are fixed and regression-tested (178 tests pass, 1 PostgreSQL test run separately and passed).

## 1. Architecture and attack surface

| Layer | What exists |
|---|---|
| Frontend | React 18 + Vite PWA, wrapped for Android with Capacitor. Bearer JWT kept in `localStorage`. No `innerHTML`/`dangerouslySetInnerHTML` sinks. No keys in `src`, `dist` or the Android build (exact-value scan of 737 files: 0 hits). |
| Backend | FastAPI, sync routes, SQLAlchemy 2. Services: accounts, captures (voice → STT → LLM → draft → commit), records, metrics. |
| Database | SQLite (dev/tests) or PostgreSQL (Neon pooler in the Render blueprint). No Alembic; `create_all` at start. |
| Auth | Username + password (PBKDF2-SHA256, 120k), HS256 JWT, 12 h TTL, roles `rep` / `manager` / `admin`. No OTP, password reset, OAuth, refresh tokens, cookies, WebSockets, file-serving routes, background workers or queues exist. |
| Paid providers | Gnani (`api.vachana.ai`: STT `/stt/v3`, TTS `/api/v1/tts/inference`) and Azure OpenAI (`chat/completions`). Keys come from environment variables only and are used only in `providers/gnani.py` and `providers/azure.py`. |
| Hosting | Render (Docker) + Vercel. Env files `.env` and `backend/.env` hold live keys; both are git-ignored (the folder is not a git repository). |

Trust boundaries: browser/app → API (JWT) → providers. The model only proposes; `captures._commit` validates and writes.

## 2. API inventory

Cost column: **STT** = Gnani speech-to-text, **TTS** = Gnani speech, **LLM** = Azure OpenAI. Limits shown are the defaults in `config.py`.

| Endpoint | Method | Authentication | Authorization | External cost | Risk after fixes |
|---|---|---|---|---|---|
| `/health` | GET | none | – | none | Low (no provider wiring outside development) |
| `/v1/auth/login` | POST | none | – | none (PBKDF2 CPU) | Low: 20/min/IP, 8 attempts/15 min/account, 30 failures/15 min/IP |
| `/v1/auth/register` | POST | none | rep open; manager needs code; optional rep code | none directly; **creates quota-bearing accounts** | **Medium**: 5/h/IP, 300/day global; open unless `REP_SIGNUP_CODE` set |
| `/v1/auth/territories` | GET | none | – | none | Low |
| `/v1/me`, `/v1/customers`, `/v1/products` | GET | JWT | org / territory scoped | none | Low |
| `/v1/captures` | POST | JWT | rep | **STT per ≤28 s segment + LLM** | Low: quotas, in-flight, global ceilings, attempt cap |
| `/v1/captures` , `/v1/captures/{id}` | GET | JWT | owner (rep) or org (manager) | none | Low (manager scope note, M5) |
| `/v1/captures/{id}/answers` | POST | JWT | owner rep | none | Low |
| `/v1/captures/{id}/corrections` | POST | JWT | owner rep | LLM (when rule parser cannot resolve) | Low |
| `/v1/captures/{id}/corrections/audio` | POST | JWT | owner rep | **STT + LLM** | Low |
| `/v1/captures/{id}/confirm` | POST | JWT | owner rep | TTS (once per capture, result cached) | Low |
| `/v1/captures/{id}/cancel`, `/retry` | POST | JWT | owner rep | `/retry` = STT + LLM | Low: atomic claim + 4-attempt cap |
| `/v1/captures/{id}/question-audio` | GET | JWT | owner rep | TTS (cached by text) | Low |
| `/v1/captures/{id}/reply-audio` | GET | JWT | owner / org | none (stored file) | Low |
| `/v1/visits`, `/orders`, `/commitments` (+ `/{id}`) | GET | JWT | owner or territory | none | Low |
| `/v1/commitments/{id}` | PATCH | JWT | owner / manager / admin | none | Low |
| `/v1/manager/*` (6 GET) | GET | JWT | manager, admin | none | Low |
| `/v1/manager/ask` | POST | JWT | manager, admin | **LLM** | Low: quotas |
| `/v1/admin/usage` | GET | JWT | admin | none | Low *(new)* |
| `/v1/admin/providers/{gnani\|azure\|all}` | PUT | JWT | admin | none (disables spend) | Medium while the seeded `admin` has a public password (see H6) *(new)* |
| `/docs`, `/redoc`, `/openapi.json` | GET | none | – | none | Closed outside development *(was open)* |

No development-only, test or forgotten admin routes exist (the OpenAPI schema is asserted to contain only `/v1/*` and `/health`).

## 3. Confirmed findings

Severity reflects impact on credits and data. "Reproduced" = shown by an automated test that passes against the fixed code and, where stated, fails/shows the drain with the protection switched off.

| ID | Sev | Finding | Evidence | Status |
|---|---|---|---|---|
| C1 | **Critical** | No rate limit or per-user quota on any paid endpoint, plus open self-signup. One person could script unlimited accounts and unlimited STT/LLM/TTS calls. | Original `routes.py` (no limiter anywhere), `accounts.py:36-63`. Reproduced: with protections off, 100 of 100 spam requests reach the provider (`test_baseline_without_protections_spam_drains_the_provider`). | **Fixed** |
| C2 | **Critical** | Azure OpenAI had no budget, no concurrency limit, no output-token cap and no global ceiling. Only Gnani had a per-process counter. `/v1/manager/ask` and every extraction/correction were unbounded. | Original `providers/azure.py:80-106`, `metrics.py:170`. | **Fixed** |
| H1 | High | Development JWT secret was a public constant used whenever `JWT_SECRET` was empty. `backend/.env` is exactly that case (`APP_ENV=development`, empty secret) **and** `HOST=0.0.0.0`, `PROVIDER_MODE=live`, demo users seeded: anyone on the network could forge an admin token. | Original `config.py:75-79`. A token signed with the old constant is now rejected (`test_dev_server_without_secret_uses_a_secret_nobody_knows`). | **Fixed** (random per-process secret; ≥32 chars enforced outside development). Your `.env` files were not edited. |
| H2 | High | Unbounded text sent to the LLM: `transcript` form field and `CorrectionRequest.text` had no limit (multipart parts allow ~1 MB ≈ 250k tokens per call). | Original `routes.py:44`, `captures.py:155-161`. | **Fixed** (4000 / 500 chars; `TEXT_TOO_LONG`) |
| H3 | High | Duplicate paid execution: two simultaneous `/retry` (or same-key `/captures`) both saw state `FAILED`/`RECORDED` and both ran STT + LLM; `confirm` could synthesise TTS twice. | Original `captures.py:177-212`. Reproduced with the claim disabled: >1 provider call (`test_baseline_without_the_claim_…`). | **Fixed** (atomic `UPDATE … WHERE state IN (…)` claim, striped locks, attempt cap) |
| H4 | High | Upload size was checked only after Starlette had received and spooled the whole multipart body; no request-body limit existed (bandwidth, disk, memory DoS). | Original `routes.py:126-128`, `main.py`. | **Fixed** (ASGI body limit before parsing; Content-Length and streamed byte count) |
| H5 | High | `Gnani` gate blocked worker threads indefinitely (`with self._gate`); a slow upstream could occupy the whole 40-thread pool and make the entire API unresponsive. | Original `gnani.py:96`. | **Fixed** (bounded wait, then 503 `PROVIDER_BUSY`) |
| H6 | High | Seeded demo accounts use the public password `demo123`, including `admin` and `meera` (manager). `render.yaml` sets `DEMO_MODE=true`, so they exist on the hosted API. Anyone can sign in as admin/manager. | `seed_data.py:9-20`, `render.yaml`. | **Mitigated, release blocker.** `DEMO_PASSWORD` setting + start-up warning added; default unchanged to keep your demo working. |
| M1 | Medium | No login brute-force control. Unknown users were also cheaper to reject than wrong passwords (dummy hash used 1 iteration), a timing oracle for usernames. | Original `routes.py:63-71`. | **Fixed** (per-IP/per-account throttle, real-cost dummy hash) |
| M2 | Medium | Tokens stayed valid for 12 h after a user was deactivated or demoted (role/org were read from the token). | Original `deps.py:41-44`. | **Fixed** (principal loaded from the database every request) |
| M3 | Medium | ffmpeg decode had no output cap (a small compressed file can expand to GBs of PCM), no concurrency limit, and junk files still spawned it. | Original `audio.py:65-79`. | **Fixed** (`-t` cap, 2 slots, magic-byte check first) |
| M4 | Medium | Audio retention ran only at process start, so uploaded audio accumulated while the server stayed up. | Original `main.py:45`. | **Fixed** (purged every 10 min on upload) |
| M5 | Medium | A manager can read any capture in the organisation, ignoring the territory scoping used for visits/orders. | `captures.py:_load` | **Open** (low impact in a single-org demo; fix in plan) |
| M6 | Medium | Open sign-up lets a stranger pick any territory and read its retailer list and outstanding balances. | `accounts.py`, `records.customers` | **Mitigated** (`REP_SIGNUP_CODE`, rate limits); business decision needed |
| L1 | Low | `/docs`, `/openapi.json` public in production; `/health` named the live providers. | Original `main.py` | **Fixed** |
| L2 | Low | No security headers (nosniff, frame, referrer, CSP, HSTS, no-store). | – | **Fixed** |
| L3 | Low | CORS allowed `*` methods and headers (origins were already an explicit list, no credentials). | Original `main.py:54` | **Fixed** (narrowed) |
| L4 | Low | PBKDF2 uses 120k iterations (OWASP 2023 guidance is 600k for SHA-256). | `security.py:17` | **Open** (migrate-on-login in plan) |
| L5 | Low | JWT in `localStorage`; Android `allowBackup="true"`. No XSS sink found, but a future one would expose tokens. | `web/src/api.ts`, `AndroidManifest.xml:5` | **Open** (informational) |
| L6 | Low | A process crash mid-processing leaves a capture in `TRANSCRIBING`/`EXTRACTING`, which `/retry` refuses. | `captures._process` | **Open** |

Scanner output was not reported as findings without verification. Bandit's 6 Low and 1 Medium items were reviewed: binding `0.0.0.0` is required by the container (and is now reported by `Settings.warnings()` when combined with live providers), `random` is used only for retry jitter, `demo123` is H6, and the subprocess call passes an argument list with no user-controlled argv.

## 4. Areas tested with no finding

- **IDOR / BOLA:** one rep cannot read, correct, confirm, cancel, retry or fetch audio of another rep's capture (404/403); reps cannot see other territories' customers, visits or orders.
- **Privilege escalation / mass assignment:** every body model is `extra="forbid"`; `role` is a `Literal["rep","manager"]`; a manager code is compared in constant time; managers and reps cannot reach `/v1/admin/*`.
- **JWT:** wrong key, expired, `alg=none`, tampered payload, missing claims, old public secret: all 401. A validly signed token claiming `admin` for a rep is still 403 because the database decides.
- **Injection:** SQL payloads in `q` and credentials return nothing and break nothing (ORM parameters). No NoSQL, no command injection (ffmpeg gets an argv list and stdin), no SSRF (provider URLs are server config), no path traversal (`AudioStore._path`, server-generated keys).
- **XSS / CSRF:** responses are JSON with `nosniff`; auth is a bearer header with no cookies, so CSRF does not apply; CORS rejects unlisted origins and sends no credentials header.
- **Secrets:** no key value from either `.env` appears anywhere else in 737 scanned files; no generic key patterns found; error responses and provider errors never include keys, bodies or tracebacks (tested).
- **Dependencies:** `pip-audit` on the locked set (97 requirement lines): no known vulnerabilities. `npm audit --omit=dev`: 0 vulnerabilities.
- **Prompt injection:** the LLM output is schema-constrained (`strict` JSON schema) and re-validated by domain rules; model prompts include only the caller's own catalogue; the manager LLM only chooses a named intent that maps to fixed SQL. No tool execution, no RAG store, no cross-user retrieval.

## 5. Not applicable (feature does not exist)

OTP send/verify/replay, password reset, refresh tokens, session fixation, OAuth state, WebSocket authorization, file-download ACLs, Firestore/Storage rules, account deletion, background queues/dead-letter, backup handling in code.

## 6. Untested areas

- Behaviour against the **live** Gnani and Azure APIs (deliberately not called). `max_tokens` was added to the Azure payload; it is valid for `gpt-4.1-mini` on `2024-10-21` but must be confirmed once on staging (o-series/GPT-5 deployments need `max_completion_tokens`).
- The hosted Render/Neon/Vercel environment, TLS, and `TRUSTED_PROXY_COUNT` behind Render's proxy.
- PostgreSQL behind **PgBouncer/Neon pooler** (atomic reservation was proven on PostgreSQL 16 directly, 50 and 40 simultaneous requests, repeated, two independent guard instances).
- DAST with OWASP ZAP/Burp, Semgrep, Gitleaks, Trivy: not installed here and not installed to avoid sending anything to third parties. Substituted by Bandit, a custom exact-value secret scan and the manual review above.
- Real ffmpeg decode of hostile media (ffmpeg is not installed here); the `-t` cap and the pre-ffmpeg magic check are tested with a stub.
- Throughput/load numbers: tests count mocked provider calls, they are not performance tests.

## 7. Files changed

New: `src/bolbazaar/costguard.py`, `guard.py`; `tests/security/*`; `security/*.md`.
Modified: `config.py`, `errors.py`, `models.py` (2 new tables, no change to existing tables), `main.py`, `security.py`, `audio.py`, `seed.py`,
`api/deps.py`, `api/routes.py`, `services/captures.py`, `accounts.py`, `metrics.py`, `providers/base.py`, `gnani.py`, `azure.py`, `tests/conftest.py`
(relaxed request-rate limits for functional tests), `tests/test_providers.py` (backoff now has jitter), `.env.example`, `API_DOCUMENTATION.md`.

Breaking changes (documented): `/docs` and `/openapi.json` disappear outside development; `/health` no longer returns `providers` outside development;
clients now receive 429/503 with `Retry-After` when limits are hit; a blank `JWT_SECRET` in development gives a random per-process secret (tokens do not survive a restart).
