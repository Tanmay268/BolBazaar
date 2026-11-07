# BolBazaar — Security Test Results

Run: 2026-11-08 · `cd backend && .venv/Scripts/python.exe -m pytest` · **178 passed, 1 skipped** (full suite, three consecutive green runs after the flaky assertion was fixed, then repeated 8× for the concurrency tests).
The one skip is the PostgreSQL atomicity test (needs `SECTEST_PG_URL`). It was run separately against a throwaway PostgreSQL 16 container (port 55432, stopped afterwards; your `bolbazaar-db` container was not touched) and **passed**.

| Suite | Tests | Result |
|---|---|---|
| Original functional suite (accounts, api, domain, metrics, providers) | 81 | PASS (one assertion updated: retry back-off now has jitter) |
| `tests/security/test_credit_protection.py` | 38 | PASS |
| `tests/security/test_auth_and_api.py` | 44 | PASS |
| `tests/security/test_ledger_and_baseline.py` | 16 | PASS (15 + PostgreSQL test run separately) |

All providers are counting mocks; **0 real provider calls, 0 credits used.**

## The ten required credit scenarios

| # | Scenario | Result | Mocked provider calls |
|---|---|---|---|
| 1 | 100 sequential requests to an expensive endpoint | PASS | LLM calls = accepted requests ≤ 12 (per-minute quota); the other 88 got 429 + `Retry-After`. Baseline with protections off: **100 of 100 reached the provider** |
| 2 | Quota of 5, 50 simultaneous | PASS | Exactly **5** reservations of 50 (SQLite file; PostgreSQL ×3 rounds; two guard instances 40 → 5). HTTP level (50 simultaneous captures): ≤ 5 LLM calls. In-flight burst: max 2 running at once |
| 3 | Multiple accounts, same IP | PASS | 5 registrations per hour per IP, then 429; global sign-up cap holds with a new IP per request; 6 accounts × 4 rounds with a global ceiling of 10 → exactly **10** provider calls |
| 4 | Duplicate requests | PASS | Same key ×11 → **1** call; 15 simultaneous → **1** call; 10 simultaneous retries of a failed capture → **1** call. Baseline with the claim removed: more than 1 (duplicate execution reproduced) |
| 5 | Global provider ceiling / breaker | PASS | Ceiling 3 → 3 calls, 5 further requests 503 `PROVIDER_BUDGET_EXCEEDED`; breaker opens after 3 failures (calls stop at 3, then 7× `PROVIDER_UNAVAILABLE`); credit error opens it after 1 call; half-open trial recovers |
| 6 | Provider timeout | PASS | Gnani/Azure timeouts with 50/99 configured retries → exactly 4 HTTP attempts, 3 back-offs; a failing capture retried 8× → 3 calls then `TOO_MANY_ATTEMPTS`; no keys/bodies in errors |
| 7 | Oversized/abusive audio | PASS | Over-bytes (413), over-duration (400), fake magic (400), script as `.wav` (400), `.exe`/bad MIME (400), empty (400), over-long text/correction/question (413/422): **0 STT/LLM calls** |
| 8 | Disabled provider | PASS | Gnani off → audio 503, **0 STT**, text capture still works; Azure off → capture and manager-ask 503, **0 LLM**, rest of app 200; master switch → **0 calls**; admin runtime switch takes effect without restart, admin-only |
| 9 | Missing authentication | PASS | 9 paid routes → 401/422, **0 calls**; every route in the OpenAPI schema except the 4 public ones → 401 |
| 10 | Quota-store failure | PASS | Dropped `usage_counters` → 5/5 requests 503 `QUOTA_UNAVAILABLE`, **0 calls**; dropped `provider_switches` → 503, 0 calls; unsupported dialect → 503, 0 calls (fail closed) |

## Authentication and authorization (44 tests)

| Check | Result |
|---|---|
| Unauthorized access to all routes | PASS |
| JWT: wrong key, expired, `alg=none`, tampered payload, missing claims, old public secret, empty/garbage | PASS (all 401) |
| Role in token not trusted; deactivated user and demoted manager lose access immediately | PASS |
| JWT secret policy (random in dev, required ≥32 chars outside dev) | PASS |
| IDOR on captures (read, correct, confirm, cancel, retry, audio), cross-territory records | PASS |
| Privilege escalation (rep→manager/admin, manager→admin, manager creating captures), manager/admin sign-up | PASS |
| Mass assignment (register, corrections, commitments) | PASS (422) |
| Login brute force (per account, per IP), correct password refused while throttled | PASS |
| Account enumeration on login (identical response; timing within 2×) | PASS |
| Per-IP and per-user limits with `Retry-After`; `X-Forwarded-For` spoofing with 0 and 1 trusted proxy | PASS |
| Pagination / query caps | PASS |
| SQL injection (6 payloads, queries and login), stored markup inert + `nosniff`, path traversal, HTTP method tampering | PASS |
| Security headers, HSTS outside development, CORS (allowed/denied origin, no credentials), docs hidden in production, no provider wiring in `/health`, no stack traces | PASS |
| WebSocket authorization | NOT APPLICABLE (no WebSocket routes; connection attempts fail) |
| Risky-configuration warnings | PASS |

## Ledger and baseline (16 tests)

Exact limit then refusal with `Retry-After` · window roll-over with other windows still binding · user isolation vs shared global ceiling · `0` means blocked · unit limits (characters, audio seconds) · all-or-nothing reservation (refused attempt leaves no trace) · failed calls not refunded · provider-reported tokens recorded separately and no prices computed · provider concurrency bounded, waiters fail fast · cleanup · atomic reservation SQLite (50 → 5) and PostgreSQL · ffmpeg `-t` cap and junk never spawns ffmpeg · magic-byte sniffing · **baseline reproductions** (spam drains provider; concurrent retry double charges).

## Vulnerabilities reproduced, then fixed and retested

| Finding | Reproduction | Retest |
|---|---|---|
| C1 unlimited paid calls | 100/100 requests reached the provider with protections off | 12 calls max |
| H3 duplicate paid execution | >1 provider call from simultaneous retries with the claim disabled | exactly 1 |
| H1 public dev JWT secret | token signed with the old constant is a valid credential when that secret is configured | rejected by default |
| M1 enumeration timing | old dummy hash cost ~1 iteration | within 2× of a real check |
| C2, H2, H4, H5, M2–M4 | by code review and unit tests of the new controls (no safe way to run the original against live services) | PASS |

## Static analysis and scans

| Tool | Result |
|---|---|
| Exact-value secret scan (every secret in both `.env` files against 737 files) | 0 hits outside the `.env` files |
| Generic key-pattern scan | 0 hits |
| `pip-audit` (locked dependencies, via OSV/PyPI; sends package names only) | No known vulnerabilities |
| `npm audit --omit=dev` | 0 vulnerabilities (dev dependencies not audited) |
| Bandit (`src`) | 6 Low, 1 Medium, all reviewed: bind-all default (documented), retry jitter `random`, demo password (H6), argv-list subprocess |
| Semgrep, Gitleaks, Trivy, ZAP, Burp | NOT TESTED (not installed; not installed to avoid third-party transfer) |

## NOT TESTED

Live Gnani/Azure behaviour (deliberately not called), Render/Neon/Vercel deployment and Neon pooler, `TRUSTED_PROXY_COUNT` behind Render, real ffmpeg on hostile media, multi-instance in-memory limiter behaviour, OTP/password reset/OAuth/refresh tokens (do not exist), load/throughput.
