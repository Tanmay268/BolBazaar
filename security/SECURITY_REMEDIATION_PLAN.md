# BolBazaar — Security Remediation Plan

Status: **READY FOR CONTROLLED STAGING · NOT READY FOR PUBLIC RELEASE.**
Fixed in code: C1, C2, H1–H5, M1–M4, L1–L3. Open: the items below.

## Release blockers

| # | Item | Why it blocks | Exact fix |
|---|---|---|---|
| B1 | **Demo accounts with public password `demo123`** — *mitigated in code: the real `admin` now takes a private `ADMIN_PASSWORD`, and a public view-only `recruiter` account replaces it for reviewers (set `ADMIN_PASSWORD` in Render to finish)* (`admin`, `meera`, `asha`, `ravi`, `priya`), seeded because `render.yaml` sets `DEMO_MODE=true` | Anyone can sign in as admin or manager. The admin can read usage and flip the new kill switches. | Set `DEMO_PASSWORD` to a strong value in Render, or set `DEMO_MODE=false` and create real users. If the database already holds the seeded users, change their password hashes (seeding is skipped once an organisation exists, so the env var alone does not change existing users). |
| B2 | **Open sign-up** with live providers | Anyone can create accounts that each spend a personal quota; only global ceilings bound it. | Set `REP_SIGNUP_CODE` (and distribute it to reps), or `ALLOW_SIGNUP=false` and onboard users, or add Cloudflare Turnstile to `/v1/auth/register`. The web sign-up form currently sends a code only for managers; add a code field for reps before enabling `REP_SIGNUP_CODE`. |
| B3 | **`TRUSTED_PROXY_COUNT` unset on Render** | With 0, every client shares the proxy address, so per-IP limits become one shared limit (5 sign-ups/hour for the whole world, 20 logins/min total). | Set `TRUSTED_PROXY_COUNT=1` in Render (one proxy hop). Verify on staging that two different clients get different limits. `render.yaml` was not edited (deployment config). |
| B4 | **Provider-side spend caps not configured** | Application limits are not enough on their own. | Azure: budget + alerts, deployment TPM/RPM quota. Gnani: confirm per-key limits/alerts in the console. See CREDIT_PROTECTION_REPORT §11. |
| B5 | **One pass against the real providers on staging** | `max_tokens` on the Azure payload and the new limits were only tested with mocks. | Run a few real captures (≈10 calls) on a staging key. Confirm no 400 on `max_tokens` (switch to `max_completion_tokens` for o-series/GPT-5), extraction is not truncated at 2048 tokens (raise `AZURE_MAX_OUTPUT_TOKENS` if needed), and `/v1/admin/usage` totals match the provider dashboards. |

## Required deployment configuration (production)

```
APP_ENV=production            JWT_SECRET=<48+ random bytes>      DEMO_PASSWORD=<strong> or DEMO_MODE=false
TRUSTED_PROXY_COUNT=1         CORS_ORIGINS=<exact web origin(s)>  REP_SIGNUP_CODE=<code>   MANAGER_SIGNUP_CODE=<code>
GNANI_DAILY_CALL_BUDGET=<calls you can afford>   GLOBAL_AZURE_REQUESTS_PER_DAY / _EST_TOKENS_PER_DAY=<…>
```
Review every `USER_*` and `GLOBAL_*` default in `.env.example` against measured usage after one staging week. Everything is an environment variable; none needs code changes.
Rotate the Gnani and Azure keys only if you have ever shared the `.env` files; this audit did not copy any key value into any file or output.

## Prioritised remaining work

| Pri | Item | Fix |
|---|---|---|
| P1 | Per-process request limiter / in-flight slots (breaks if you run more than one instance) | Put limits at the edge (Cloudflare, Render/Vercel) or add a Redis-backed `SlidingWindowLimiter` (same interface: `hit`, `blocked_for`, `record`, `reset`). The database-backed quotas already work across instances. |
| P1 | M5: managers can read any capture in the org | In `CaptureService._load`, for `manager` scope by `Customer.territory_id` the same way `RecordsService._customer_scope` does; add an IDOR test for manager vs foreign territory. |
| P2 | M6: stranger sign-up exposes a territory's retailers and balances | Decide whether new reps need approval; if yes, add an `approved` flag (needs a migration; the app uses `create_all`, which does not alter existing tables). |
| P2 | L4: PBKDF2 120k iterations | Raise `ITERATIONS` to ≥600 000 and rehash on successful login (verification already reads the iteration count from each hash). Measure login CPU first; the login limits cap the amplification. |
| P2 | L6: captures stuck in `TRANSCRIBING`/`EXTRACTING` after a crash | Add a reaper that sets such captures to `FAILED` after N minutes, or allow `/retry` when `updated_at` is older than N minutes. |
| P3 | L5: token in `localStorage`; Android `allowBackup="true"` | Set `allowBackup="false"`; shorten `JWT_TTL_MINUTES`; add refresh-token rotation if the session length matters; keep a strict CSP on the web host (Vercel headers). |
| P3 | PostgreSQL statement timeout | Neon's pooler rejects the `options` startup parameter, so set it on the role: `ALTER ROLE <app_role> SET statement_timeout = '15s'`. Use a least-privilege role without DDL rights once `create_all` is replaced by migrations. |
| P3 | Data growth | Add retention for `audit_log`, `idempotency_keys`, `outbox_events` (no consumer exists) and old `usage_counters` rows (3-day cleanup already runs inside the guard). |
| P3 | Log retention and monitoring | Ship logs to a store with alerts on `budget_warning`, `provider_budget_exhausted`, `circuit_open`, `quota_ledger_unavailable`, and on 429 spikes. |
| P3 | Tooling | Add Semgrep, Gitleaks, `pip-audit` and `npm audit` to CI; run ZAP against staging. |

## Operating the kill switches

- Immediate stop of one provider: `PUT /v1/admin/providers/azure` with `{"enabled": false, "reason": "runaway"}` (use `gnani` or `all` likewise). Re-enable with `{"enabled": true}`.
- Check spend: `GET /v1/admin/usage` (global counters vs ceilings, top users, breaker and switch state).
- If you cannot authenticate: set `AI_SERVICES_ENABLED=false` (or `GNANI_ENABLED`/`AZURE_ENABLED`) in the host environment and restart.
- Revoke a key: rotate it at the provider, update the environment variable, restart.

## Production go-live checklist

- [ ] B1 demo password changed or demo mode off; seeded users reviewed
- [ ] B2 sign-up gated (code, CAPTCHA or disabled)
- [ ] B3 `TRUSTED_PROXY_COUNT=1` verified with two real clients
- [ ] B4 Azure budget + TPM/RPM quota; Gnani limits/alerts confirmed
- [ ] B5 staging run against real providers (`max_tokens`, truncation, usage totals)
- [ ] `JWT_SECRET` ≥ 32 random chars; `APP_ENV=production` (docs and provider wiring hidden)
- [ ] `CORS_ORIGINS` lists only the real web/app origins
- [ ] `GNANI_DAILY_CALL_BUDGET` and the global Azure ceilings set to what you can afford
- [ ] `/v1/admin/usage` works for an admin; kill switch rehearsed once on staging
- [ ] Alerts on the log events above; someone owns them
- [ ] Single instance, or a shared limiter/edge limits (P1)
- [ ] `allowBackup="false"` and a rebuilt Android app (P3)
- [ ] Full test run green: `cd backend && pytest` (set `SECTEST_PG_URL` to include the PostgreSQL test)
