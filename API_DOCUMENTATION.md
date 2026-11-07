# API Documentation

Status: **implemented and tested** (backend, offline providers; live Gnani/Azure adapters are contract-tested against mocked HTTP only). Interactive docs at `/docs` when the server runs. Deeper notes: [docs/api/api-reference.md](docs/api/api-reference.md).

## Conventions
- Base path `/v1`, JSON, camelCase. Auth: `Authorization: Bearer <JWT>` from `/v1/auth/login`.
- `Idempotency-Key` (8–200 chars of `[A-Za-z0-9._:-]`) is **required on `POST /captures` and `POST /captures/{id}/confirm`**. Other edits are protected by the draft `revision` (`409 STALE_REVISION`).
- Errors: `{"error":{"code","message","details"},"requestId"}`; the same ID is in the `X-Request-Id` header.
- Money is integer paise in responses (`...Paise`); amounts in requests that say `Rupees` are rupees.
- Dates are `YYYY-MM-DD`, resolved in the organisation's timezone.

## Roles
`rep` (own captures, own territory's retailers), `manager` (their territories, read-only on captures), `admin` (all).

## Endpoints

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | /health | none | Liveness and provider mode |
| POST | /v1/auth/login | none | `{username,password}` → `{token,user}` |
| GET | /v1/me | any | Current user |
| GET | /v1/customers?q= | any | Search retailers in scope |
| GET | /v1/products?q= | any | Catalogue |
| POST | /v1/captures | rep | Multipart: `audio` **or** `transcript`, `language`, `customerId?`, `capturedAt?` |
| GET | /v1/captures, /v1/captures/{id} | any | List / full state |
| POST | /v1/captures/{id}/answers | rep | `{revision, answer}` for the open question |
| POST | /v1/captures/{id}/corrections | rep | `{revision, text}` spoken/typed correction or answer |
| POST | /v1/captures/{id}/corrections/audio | rep | Multipart `audio`, `revision`; transcribed then applied |
| POST | /v1/captures/{id}/confirm | rep | `{revision, speakReply}` (+ Idempotency-Key) |
| POST | /v1/captures/{id}/cancel, /retry | rep | Abandon / re-run a failed capture |
| GET | /v1/captures/{id}/question-audio | rep | Spoken clarification question (TTS, cached) |
| GET | /v1/captures/{id}/reply-audio | any | Spoken confirmation after commit |
| GET | /v1/visits, /v1/visits/{id} | any | Committed visits with order, collections, complaints, commitments |
| GET | /v1/orders, /v1/orders/{id} | any | Orders |
| GET | /v1/commitments?status=&overdue= | any | Follow-ups |
| PATCH | /v1/commitments/{id} | owner/manager | `{status}` and/or `{dueDate}` |
| GET | /v1/manager/summary | manager | KPI strip |
| GET | /v1/manager/overdue-payments, inactive-retailers?days=, pending-commitments, conversion?days=, declining-products?days= | manager | Named SQL queries |
| POST | /v1/manager/ask | manager | `{text}` → intent → query → answer text |

## Capture response (abridged)
```json
{
  "id": "cap_…", "state": "NEEDS_CLARIFICATION", "revision": 1, "language": "hinglish",
  "transcript": "…",
  "draft": { "customer": {}, "visit": {}, "order": {"items": [], "deliveryDate": null},
             "collections": [], "complaints": [], "competitorNotes": [], "commitments": [], "totalPaise": 0 },
  "clarification": { "code": "AMBIGUOUS_PRODUCT", "fieldPath": "order.items.1", "answerPath": "order.items.1.productId",
                     "answerType": "choice", "question": "\"Real juice\" se aapka matlab kaun sa product hai?",
                     "options": [{"value": "prd_…", "label": "Real Mango Juice 1L"}] },
  "openIssues": ["AMBIGUOUS_PRODUCT"], "error": null, "visitId": null, "reply": null
}
```
States: `RECORDED → TRANSCRIBING → EXTRACTING → NEEDS_CLARIFICATION ⇄ READY_FOR_REVIEW → COMMITTED`, plus `FAILED` (retryable) and `CANCELLED`.

Edit responses (`answers`, `corrections`) add `patch: [{path, old, new}]` and `unsupported: [text]`. A correction that changes nothing returns the same revision and lists the request under `unsupported` rather than dropping it.

**Languages:** `hinglish` (default), `hi-IN`, `en-IN`, `ta-IN`, `mr-IN`, `te-IN`, `kn-IN`, `ml-IN`, `bn-IN`, `gu-IN`, `pa-IN`. Clarification questions and spoken confirmations are localised for these.

**Confirm response:** `{captureId, visitId, orderId, orderTotalPaise, collectionIds, commitmentIds, customer, confirmationText, language, reply:{status: READY|FAILED|SKIPPED, url?}}`. A TTS failure never fails the request.

## Error codes
`AUTH_REQUIRED`, `INVALID_TOKEN`, `INVALID_CREDENTIALS`, `FORBIDDEN`, `VALIDATION_ERROR`, `IDEMPOTENCY_KEY_REQUIRED`, `IDEMPOTENCY_CONFLICT`, `STALE_REVISION`, `INVALID_STATE`, `NO_OPEN_QUESTION`, `ALREADY_COMMITTED`, `DRAFT_INVALID`, `UNSUPPORTED_LANGUAGE`, `UNSUPPORTED_AUDIO`, `AUDIO_TOO_LARGE`, `NO_SPEECH`, `PROVIDER_ERROR` (details: `stage`, `category`, `captureId`), `CAPTURE_NOT_FOUND`, `VISIT_NOT_FOUND`, `ORDER_NOT_FOUND`, `COMMITMENT_NOT_FOUND`, `INTERNAL_ERROR`.

## Offline sync
There is no separate sync endpoint. The device queue replays `POST /captures` with the same `Idempotency-Key` it generated offline; the server de-duplicates by key and content fingerprint.

## Cost-protection behaviour (added by the security audit)

New responses clients must handle (all use the standard error envelope; 429/503 carry `Retry-After` seconds):

| Status | `error.code` | Meaning |
|---|---|---|
| 429 | `RATE_LIMITED` | Too many requests from this IP or user. |
| 429 | `LOGIN_THROTTLED` | Too many sign-in attempts for this account or IP. |
| 429 | `QUOTA_EXCEEDED` | The user's per-minute/hour/day AI allowance is used up (`details.limit`, `details.window`). |
| 429 | `CONCURRENCY_LIMIT` | The user already has the maximum number of AI requests running. |
| 429 | `TOO_MANY_ATTEMPTS` | One capture was retried too many times; record it again. |
| 503 | `PROVIDER_BUDGET_EXCEEDED` | A global provider ceiling was reached; the feature returns after the window resets. |
| 503 | `PROVIDER_DISABLED` | The provider was switched off (env flag or admin switch). |
| 503 | `PROVIDER_UNAVAILABLE` / `PROVIDER_BUSY` | Circuit breaker open, or no provider slot free within the wait. |
| 503 | `QUOTA_UNAVAILABLE` | Usage accounting is unreachable; paid calls fail closed. |
| 503 | `SIGNUP_LIMIT` | The global daily sign-up cap was reached. |
| 413 | `REQUEST_TOO_LARGE`, `AUDIO_TOO_LARGE`, `TEXT_TOO_LONG` | Body, recording or text over the configured limit. |

Admin-only endpoints (role `admin`):

- `GET /v1/admin/usage` — today's global usage vs ceilings, top users, breaker state, switches.
- `PUT /v1/admin/providers/{gnani|azure|all}` with `{"enabled": false, "reason": "..."}` — runtime kill switch (no redeploy).

Other changes: `/docs`, `/redoc`, `/openapi.json` are served only when `APP_ENV=development` (or `EXPOSE_DOCS=true`);
`/health` omits `providers` outside development; `Authorization` is checked against the database on every request
(a deactivated user or changed role applies immediately); text fields are length-capped; uploads must be real audio.

## Catalogue endpoints

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/v1/products?q=&includeInactive=` | any signed-in user | Reps see active items only; `includeInactive=true` is honoured for managers/admins. Returns `id, name, baseUnit, unitsPerPack, pricePaise, active, aliases`. |
| POST | `/v1/products` | manager, admin | `{name, baseUnit (kg\|packet\|bottle\|piece), priceRupees, unitsPerPack?, aliases?}` → 201. 409 `DUPLICATE_PRODUCT`, `CATALOGUE_FULL`; 422 `INVALID_UNIT`; 429 `CATALOGUE_LIMIT`. |
| PATCH | `/v1/products/{id}` | manager, admin | Any of `name, baseUnit, priceRupees, unitsPerPack, aliases, active`. Price changes affect new orders only. |
| DELETE | `/v1/products/{id}` | manager, admin | Retires the product (`active=false`); history is kept. |

Adding an item during a visit: when a spoken item is unknown, the clarification (`UNKNOWN_PRODUCT` / `AMBIGUOUS_PRODUCT`) includes an option with value `__new__`.
Answering with it (`POST /captures/{id}/answers`, or by saying "add karo, 60 rupaye kilo" through `/corrections` or `/corrections/audio`) marks the draft line with `newProduct`
and may ask `NEW_PRODUCT_UNIT` and `NEW_PRODUCT_PRICE`. The product is created only at `/confirm`.

Whole catalogue from one passage (manager/admin; AI-assisted, two steps):

- `POST /v1/products/draft` (multipart: `audio` **or** `text`, optional `language`) → `{transcript, items[], truncated, note}`. Each item: `name, baseUnit, priceRupees, unitsPerPack, aliases, evidence, issues[] (missing_price|missing_unit|missing_name|duplicate|repeated), duplicateOf, include`. **Saves nothing.** Costs one LLM call (plus STT for audio); same quotas, kill switches and limits as visits.
- `POST /v1/products/bulk` `{items:[{name, baseUnit, priceRupees, unitsPerPack?, aliases?}]}` (max 100) → 201 `{created[], skipped[{name, reason}]}`. Every item is re-validated server-side; duplicates and invalid rows are skipped; 300 products/day (`USER_BULK_PRODUCTS_PER_DAY`).

## Bug reports

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/v1/bug-reports` | any signed-in user | `{category: broken\|wrong_result\|voice\|suggestion\|other, title (3-120), description (10-2000), context?: {page, appVersion, platform, language, lastError?: {code, requestId, status, path}}}` -> 201. Unknown context keys are refused; query strings are stripped from `path`. 429 `BUG_REPORT_LIMIT` after 10/day per user; 503 after 500/day overall. |
| GET | `/v1/bug-reports/mine` | any signed-in user | Only the caller's own reports, with status and admin note. |
| GET | `/v1/admin/bug-reports?status=` | admin | All reports in the organisation, with reporter name and role. |
| PATCH | `/v1/admin/bug-reports/{id}` | admin | `{status: open\|in_progress\|resolved\|wontfix, note?}` |
