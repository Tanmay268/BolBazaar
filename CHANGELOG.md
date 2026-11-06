# Changelog

Format: newest first. Every iteration adds an entry.

## [Unreleased]

## 2026-11-04 – Build iteration 6: call agent
### Added
- Payment-promise **call agent** (`CALL_AGENT.md`): deterministic state machine (`domain/calls.py`) over a strict-schema classifier of the retailer's reply (`CallReply`), lazy-cached Gnani TTS for each agent line, STT for audio replies, human approval before anything is filed. Endpoints under `/v1/calls`; models `CallSession`, `CallTurn`; offline and Azure `interpret_call_reply`.
- Web: call screen (live transcript, agent voice with a credit-saving toggle, you play the retailer by voice, text or sample replies, outcome review card), rep Promises "Call" button and recent calls, manager Calls tab.
- 27 call tests (96 total).
### Changed
- Calls are stored as visits with purpose `phone_call`; visits-today and conversion metrics exclude them.
### Verified
- Live: 10 Hinglish replies classified by Azure; full browser flow on live Gnani TTS + Azure (call → confirm → outcome → approve → manager sees the filed call), no console errors.
### Not verified / not built
- Real phone calls: Gnani's published API has no telephony; a provider must be chosen (see CALL_AGENT.md). Streaming/low-latency turns, native-speaker review of the Hindi/Hinglish scripts, and regulatory sign-off for real outbound calls.

## 2026-11-04 – Build iteration 5: UI/UX redesign
### Changed
- Rebuilt the web client's design system and screens (`docs/DESIGN.md`): landing/sign-in, rep Today / Visits / centre Talk / Promises / You with a bottom bar, ripple-orb voice control that follows the real microphone level, three-step processing read-out, draft shown as confidence-tagged cards, success screen with spoken reply, manager Overview / Ask / Activity with ring gauges and gradient bars. Saffron-to-coral on warm paper or deep indigo; light and dark themes.
- UI language toggle (English / Hinglish); speaking language remains a separate choice.
- Mobile-first layout: framed phone column for reps on wide screens, two-column workspace for managers ≥900 px, no horizontal overflow from 360 px up, reduced-motion support.
### Verified
- Driven in headless Chrome against the live backend with a fake microphone: recorder starts and the level meter updates, WAV reaches the API and a friendly no-speech message is shown, sample visit → draft → confirm → success, manager dashboard and Ask. Screenshots in `docs/screenshots/`. No console errors other than the expected 422 from the fake (silent) microphone.
### Not verified
- Real human speech through the mic, a physical phone/Android device, Safari/iOS.

## 2026-11-04 – Build iteration 4: clients, live verification, deployment config
### Added
- `web/`: React + TypeScript + Vite client with role-based shell. Rep app: hold-to-talk recorder (live level meter, 16 kHz mono WAV on every platform), visit thread with draft ledger, inline clarification (choices / number / date, with spoken question), voice and typed correction, confirm with idempotency key, spoken confirmation playback, history, follow-ups. Manager dashboard: KPI tiles, overdue payments, pending follow-ups, conversion, declining products, quiet retailers, latest visits, intent-based "ask".
- Device offline queue (IndexedDB) that replays `POST /captures` with stored idempotency keys when connectivity returns.
- Capacitor Android project with microphone permission; debug APK builds.
- `backend/eval/`: 15 labelled cases, field-level scoring on the application draft, latency and modelled time-saved, optional WER over user clips, offline baseline.
- `render.yaml`, `backend/Dockerfile`, `web/vercel.json`, `DEMO_MODE` setting (seeds the demo organisation outside development; `JWT_SECRET` still required), `DEPLOYMENT.md`, `DEMO_SCRIPT.md`.
### Fixed
- Live voice correction ("make Parle-G 15") was rejected because the model returned `/order/items/0/quantity`; paths are now normalised before the unchanged whitelist (3 new tests, 69 total).
- Extraction prompt: items sharing a sentence were dropped (second order line), promised payments lacked a payment follow-up commitment, and a delivery date produced a duplicate follow-up commitment.
- `docs/api/api-reference.md`: draft shape now shows the single `order`.
### Verified (live)
- Gnani TTS (`timbre-v2.5`, Poorvi, `hi-en`) → WAV; Gnani STT (`prisma-v3.0`, `hi-IN,en-IN`, `codemix`) on that audio returned a mostly-Devanagari transcript in ~1 s. 2 calls total.
- Azure strict JSON-schema extraction works on the configured deployment (2–6 s).
- Full API flow on live providers: capture → correction → confirm → spoken reply audio → manager summary/ask.
- Evaluation, three live runs after the prompt fixes: 15/15, 15/15 (final two); earlier runs 10–14/15 as issues were found. Offline baseline 6/15.
- Production-mode boot with demo seeding and CORS (run natively; the Docker image was not built because the Docker daemon was not running).
### Not verified
- UI in a browser (the browser extension was not connected), real human speech, a physical Android device, Render/Vercel deployment, Postgres. Credit cost of the live calls is not yet read from app.gnani.ai.

## 2026-11-04 – Build iteration 3: backend core
### Added
- `backend/`: FastAPI service, 66 passing tests. Domain layer (dates, units, fuzzy resolution, draft build/validate/patch), providers (offline set, Gnani HTTP client, Azure strict-schema reasoner), audio segmentation, SQLAlchemy models and demo seed, capture lifecycle, commitments, records, manager metrics with intent-based `ask`, JWT auth with roles and territory scoping.
- Localised clarification questions and spoken confirmations (Hinglish, English, Hindi, Tamil, Marathi; drafts needing native review).
### Changed
- API: idempotency keys required only for create and confirm; edits use revision checks. Added `/corrections/audio` and named manager endpoints. Open question is derived from the draft's issues instead of a separate table.
- Schema: commitments use `due_date`; removed `sync_ops` (offline queue replays `POST /captures` with stored keys); added `reply_audio`.
- `.env.example` rewritten to match settings (per-language Gnani profiles replace global format/voice settings).
### Verified
- Server starts and serves `/health` and `/v1/auth/login`; the Hinglish demo scenario runs on the offline providers from speech upload to manager dashboard.
### Not verified
- Live Gnani and Azure calls (no keys used yet).

## 2026-11-04 – Planning iteration 2 (Phase 3 inputs)
### Changed
- Verified Gnani STT/TTS against docs.gnani.ai; replaced SDK-derived assumptions in the API reference.
- ARCHITECTURE: added the 30 s STT cap, single-request concurrency gate, format rules and Android/browser recorder parity.
- ADR-001 amended: no Gnani SDK (stale), segment-then-transcribe, call gate, TTS model choice by listening test.
- PROJECT_PLAN: programme-fit table (awards), resolved inputs, remaining open items.
- `.env.example`: added STT model/format and TTS model options; credit-safety settings.
### Notes
- Pricing and credit units are not published in the docs; unresolved.

## 2026-11-04 – Planning iteration 1
### Added
- Project documentation set: README, PROJECT_PLAN, ARCHITECTURE, API_DOCUMENTATION, DATABASE_SCHEMA, TASKS, TESTING, DEPLOYMENT, `.env.example`, `.gitignore`.
- `docs/` tree: system architecture, data flow, sequence diagrams, ERD, API reference, ADR-001 (technology stack), ADR-002 (database selection). Diagrams use Mermaid.
- Opportunity analysis, scope tiers (P0/P1/P2) and a design direction deliberately distinct from the reference app.
### Decisions
- Cut Redis/Celery/AWS from the MVP; keep PostgreSQL; fixed manager query intents instead of text-to-SQL.
### Notes
- No application code yet. Reference project (BolBazaar) was not modified.
