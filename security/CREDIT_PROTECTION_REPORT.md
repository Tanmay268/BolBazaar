# BolBazaar — Credit Protection Report (Azure + Gnani)

## 1. Integration inventory

| Provider | Where the key lives | Code path | Operations that cost money |
|---|---|---|---|
| **Gnani** (`GNANI_API_KEY`) | Environment only. Sent only as `X-API-Key-ID` from `providers/gnani.py`. Not in any API response, log line, frontend bundle or git history (no git). | `GnaniClient.post` ← `GnaniSTT.transcribe`, `GnaniTTS.synthesize` | STT per ≤28 s segment (`POST /stt/v3`); TTS per reply or clarification question (`POST /api/v1/tts/inference`). Gnani's own cost per call is unknown (noted in project memory) — **no price is assumed anywhere**. |
| **Azure OpenAI** (`AZURE_OPENAI_API_KEY`) | Environment only, header `api-key` from `providers/azure.py`. | `AzureReasoner._chat` ← `extract`, `patch`, `parse_manager_query` | One chat completion per extraction, per LLM-routed correction, per manager question. |

The browser and the Android app never talk to either provider; they only call this API.

## 2. Credit-consuming endpoints

| Endpoint | Paid calls | Guarded by |
|---|---|---|
| `POST /v1/captures` (audio) | n × STT (n = segments) + 1 LLM | user in-flight, STT quota (requests, audio seconds), LLM quota, global Gnani + Azure ceilings, attempt cap, atomic claim |
| `POST /v1/captures` (text) | 1 LLM | same, minus STT; 4000-char cap |
| `POST /v1/captures/{id}/corrections` | 0–1 LLM | LLM quota; 500-char cap |
| `POST /v1/captures/{id}/corrections/audio` | n × STT + 0–1 LLM | STT + LLM quotas |
| `POST /v1/captures/{id}/retry` | STT + LLM | atomic claim, 4 attempts per capture, quotas |
| `POST /v1/captures/{id}/confirm` | 1 TTS (once; cached) | TTS quota, striped lock, 600-char cap |
| `GET /v1/captures/{id}/question-audio` | 1 TTS per distinct question (cached) | TTS quota, striped lock |
| `POST /v1/manager/ask` | 1 LLM | LLM quota, 400-char cap |

Request flow for every paid operation (`costguard.py`):

1. Authenticate and authorise (JWT + database check) → per-user and per-IP request limits.
2. Validate input and audio **locally** (size, type, magic bytes, duration, text length). Failures cost nothing.
3. Take a per-user in-flight slot (`USER_MAX_CONCURRENT_AI`, default 2).
4. Check kill switches (env flags and the live database switch) and the circuit breaker.
5. **Atomically reserve** user and global quota in one transaction. Any refusal rolls all counters back.
6. Take a per-provider concurrency slot (bounded wait, then fail fast).
7. Call the provider (bounded timeout, at most 3 retries with exponential backoff and jitter, every HTTP attempt charged to a per-process budget).
8. Record provider-reported usage (`actual_tokens`), update the breaker. Reservations are **not refunded** after a call was attempted.

## 3. Rate limits (existing before the audit vs now)

| Operation | Before | Now (default, all configurable, `0` = blocked) |
|---|---|---|
| Login | none | 20/min/IP; 8 attempts per 15 min per account (charged up front, cleared on success); 30 failures per 15 min per IP |
| Registration | none | 5/hour/IP; **300/day global** (database); optional `REP_SIGNUP_CODE`; manager code unchanged |
| General API | none | 240/min/IP (all `/v1`), 120/min/user |
| STT (Gnani) | none per user | per user 8/min, 60/h, 120/day, 3600 audio-seconds/day |
| TTS (Gnani) | none per user | per user 6/min, 40/h, 80/day, 15 000 chars/day; 600 chars/request |
| Azure LLM | none | per user 12/min, 100/h, 250/day, 400 000 estimated tokens/day |
| Concurrency | Gnani semaphore with unbounded wait; Azure none | 2 in flight per user; Gnani 1 and Azure 4 per provider, wait ≤ 3 s then 503 |
| Uploads | 15 MB checked after full receipt | body limit enforced before parsing (15 MB + 1 MB overhead for audio routes, 256 KB elsewhere); ffmpeg 2 at a time |
| Global Gnani | in-process 200 calls/day, counted per HTTP attempt | **database-backed** and shared across processes/restarts: 30/min, `GNANI_DAILY_CALL_BUDGET`/day (200), 7200 audio-s/day, 60 000 TTS chars/day; in-process attempt budget kept as a backstop |
| Global Azure | none | 60/min, 800/day, 1 500 000 estimated tokens/day; in-process attempt budget 2400/day (retries included); output capped at 2048 tokens |

Limits are windows in UTC (minute, hour, day). Responses are HTTP 429 (user) or 503 (global/provider) with `Retry-After` computed from the failing window. The defaults are starting points sized for a small field team; compare them with your measured usage after the first staging week. Note the global Gnani request ceiling (200/day) equals the owner-chosen existing budget and is now the binding constraint for the whole team.

## 4. Per-user quotas

Counters live in table `usage_counters (scope, metric, window)` with `used`. Tracked per user: STT requests, audio seconds, TTS requests, TTS characters, LLM requests, estimated tokens, plus provider-reported `actual_tokens` for Azure. Daily, hourly and per-minute usage is visible through `GET /v1/admin/usage` (global totals and top users).
No cost in currency is computed: no reliable price list was provided, so estimated cost is intentionally omitted. `est_*` figures are heuristics (≈3 characters per token plus 600 output tokens); `actual_tokens` is provider-reported and only monitored.

## 5. Global quota, atomicity and concurrency

- One statement per counter: `INSERT … ON CONFLICT (scope, metric, window) DO UPDATE SET used = used + n WHERE used + n <= limit RETURNING used`. No row returned = limit would be exceeded.
- All counters of one reservation share one transaction, so refusals leave no partial charge (tested).
- **Verified results:** 50 simultaneous reservations with 5 remaining → exactly 5 succeed on SQLite (file) and on **PostgreSQL 16**, three repeated rounds, and across two independent guard instances sharing the database (40 simultaneous → exactly 5). At HTTP level, 50 simultaneous captures with a quota of 5 → at most 5 provider calls.
- Sign-ups, per-capture attempts and the global sign-up ceiling use the same primitive.
- In-flight limits and the in-memory request limiter are **per process** (see remaining risks).

## 6. Retry protection

- Gnani and Azure: retries hard-capped at 3 regardless of configuration; exponential backoff with jitter; only 429/5xx/network are retried; auth/credit errors are not; every HTTP attempt consumes the in-process daily budget (tested with a 99-retry setting: exactly 4 calls).
- Provider calls never run inside a database transaction (unchanged).
- Capture level: an atomic state claim means N concurrent `/retry` or same-key `POST /captures` pay once; a capture can be processed at most `MAX_PROCESS_ATTEMPTS_PER_CAPTURE` (4) times.
- Idempotency: same `Idempotency-Key` + same content never re-runs a completed capture (tested sequentially and 15-way concurrent).
- Web client: no retry loops; the offline queue stops at the first failure; the manager dashboard polls only free endpoints.

## 7. Emergency shutdown, circuit breaker, monitoring

- Env flags: `AI_SERVICES_ENABLED`, `GNANI_ENABLED`, `AZURE_ENABLED` (restart).
- **Runtime switch, no redeploy:** `PUT /v1/admin/providers/{gnani|azure|all}` `{"enabled": false, "reason": "…"}` (admin only, audited in `audit_log`). Effective on all instances within ~2 s. Disabled features return 503 `PROVIDER_DISABLED` and never reach the provider; non-AI features (and text captures when only Gnani is off) keep working (tested).
- Circuit breaker per provider: opens after 5 consecutive health failures (60 s, doubling to 15 min), immediately for 401/402/403-class errors (15 min), half-open with a single trial call (tested).
- Fail closed: if the usage ledger or the switch table cannot be read, paid operations return 503 `QUOTA_UNAVAILABLE` (tested by dropping the tables, and for an unsupported database dialect).
- Warnings are logged once when a global counter crosses 80 % (`budget_warning`) and when a ceiling is hit (`provider_budget_exhausted`); breaker trips log `circuit_open`. Logs contain no keys, transcripts or audio.

## 8. Account farming and automation

| Attack | Result |
|---|---|
| Hundreds of accounts from one IP | Stopped at 5/hour/IP (tested). |
| Accounts from rotating IPs | Global 300/day cap (tested with a distinct address per request); global provider ceilings are independent of how many accounts exist (6 accounts × 4 rounds → exactly 10 provider calls when the ceiling is 10, tested). |
| Spoofing `X-Forwarded-For` | Ignored unless `TRUSTED_PROXY_COUNT` > 0; then only the entry appended by the trusted proxy counts (tested). IPv6 is grouped by /64. |
| Trial reuse / log out and re-register | Not preventable without identity proof; bounded by global ceilings. `REP_SIGNUP_CODE` closes it for strangers. |
| Unverified accounts calling paid APIs | There is no email/phone in this app, so email verification is impossible. Compensating controls: sign-up code, per-IP and global caps, per-account quotas. |
| Anonymous endpoints | Paid endpoints all require a JWT (tested for 9 paid routes plus every `/v1` route). |

## 9. Audio and text abuse

Rejected before any paid call (tested, provider call count 0): oversized body, over-duration audio, wrong magic bytes with an audio extension, scripts posing as audio, unsupported MIME/extension, empty file, over-long text/correction/question. Decompression bombs are bounded by ffmpeg `-t` (max seconds + 2). Repeated identical audio is bounded by the quotas; no cross-account caching of user audio exists (the only cache is clarification-question audio keyed by question text, returned only to the capture's owner). TTS strings are truncated at 600 characters.

## 10. Remaining credit-drain vectors

1. **Per-process limiters.** Request rate limits and in-flight slots are in memory. With more than one backend instance each instance enforces its own copy; the database-backed quotas and ceilings stay exact. Fix: Redis-backed limiter or platform edge limits before scaling out.
2. **Open sign-up** (unless `REP_SIGNUP_CODE` is set). Each fresh account gets a full personal quota; only the global ceilings bound a determined farmer. Add CAPTCHA/Turnstile or an invite code before public release.
3. **Global ceilings are shared**: one abuser can exhaust the daily Gnani budget for everyone (availability, not extra spend). Per-user quotas (default 120 STT/day) make this take at least two accounts at the 200/day default.
4. **No provider-side hard stop is configured by this code.** Application limits are not a substitute for Azure/Gnani limits (section 11).
5. **Estimated tokens are heuristics.** Azure `actual_tokens` is recorded but not enforced; a very token-dense request can exceed its estimate by a bounded amount (input capped at 4000 chars, output at 2048 tokens).
6. **Demo accounts with a public password** (H6) are valid users with full personal quotas.
7. **Quota consumed by failures** is intentional (no refunds), so a flaky provider drains user allowances; the breaker limits that.
8. **Gnani cost per call is unknown**; ceilings are in calls, seconds and characters, not credits. Check Gnani's console to translate them into your 5 000-credit budget.

## 11. Provider-side controls to configure (not changed by this audit)

**Azure OpenAI** (documented Azure capabilities; configure in the portal):
- Set a **Cost Management budget with alerts** at e.g. 50/80/100 % of the $100 credit, and attach an action group (email/webhook) that can disable the key. A budget alone only alerts; it does not stop spend.
- Lower the **tokens-per-minute / requests-per-minute quota on the `gpt-4.1-mini` deployment** to a value that matches the team; this is a hard throughput cap enforced by Azure.
- Use a **separate resource/key for staging and production**, rotate keys (regenerate key 1 then 2) after any exposure, and prefer Entra ID/managed identity if you move off Render.
- Credit-based subscriptions normally carry a spending limit; confirm it is enabled.

**Gnani:** I could not verify from the repository whether Gnani offers per-key spend limits, usage alerts, IP allow-listing or key scoping. Ask Gnani / check the console for: per-key daily caps, low-balance alerts, a second key for staging, and rotation. Until confirmed, treat `GNANI_DAILY_CALL_BUDGET` plus the global seconds/characters ceilings as the only hard stops.
