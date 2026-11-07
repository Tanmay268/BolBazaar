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

**Languages:** `hinglish` (default), `hi-IN`, `en-IN`, `ta-IN`, `mr-IN`. Clarification questions and spoken confirmations are localised for these.

**Confirm response:** `{captureId, visitId, orderId, orderTotalPaise, collectionIds, commitmentIds, customer, confirmationText, language, reply:{status: READY|FAILED|SKIPPED, url?}}`. A TTS failure never fails the request.

## Error codes
`AUTH_REQUIRED`, `INVALID_TOKEN`, `INVALID_CREDENTIALS`, `FORBIDDEN`, `VALIDATION_ERROR`, `IDEMPOTENCY_KEY_REQUIRED`, `IDEMPOTENCY_CONFLICT`, `STALE_REVISION`, `INVALID_STATE`, `NO_OPEN_QUESTION`, `ALREADY_COMMITTED`, `DRAFT_INVALID`, `UNSUPPORTED_LANGUAGE`, `UNSUPPORTED_AUDIO`, `AUDIO_TOO_LARGE`, `NO_SPEECH`, `PROVIDER_ERROR` (details: `stage`, `category`, `captureId`), `CAPTURE_NOT_FOUND`, `VISIT_NOT_FOUND`, `ORDER_NOT_FOUND`, `COMMITMENT_NOT_FOUND`, `INTERNAL_ERROR`.

## Offline sync
There is no separate sync endpoint. The device queue replays `POST /captures` with the same `Idempotency-Key` it generated offline; the server de-duplicates by key and content fingerprint.
