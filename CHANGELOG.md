# Changelog

Format: newest first. Every iteration adds an entry.

## [Unreleased]

## 2026-11-06 – Build iteration 7: redesign to the supplied design board
### Changed
- Whole web client restyled to the owner's design board (`docs/DESIGN.md`): ink-and-red on paper, heavy headlines, square blocks, outline icons, light theme only. Rep app: Today (storefront art, red visits block), Log a Visit (red orb: tap to record with pause/stop and clock, or press and hold), Review Visit (ruled list, Edit / Confirm), Visit Saved (red screen), Visits, Orders, More. Manager: black sidebar workspace (Overview, Ask, Visits, Orders, Promises, Retailers, Team) with an off-canvas drawer on phones.
- Backend metrics gained real fields for the board's numbers: `visits30d` / `visitsPrev30d` (summary), `nextDueDate` (overdue payments), `orderValuePaise` (conversion by rep). 3 new tests (72 total).
- Elements the board shows that have no data behind them were replaced honestly (see DESIGN.md): the GPS heatmap became a 28-day visit-activity grid; only the real 30-day visit delta is shown; "Visit Completion" is shown as order conversion; Reports and voice-Ask are omitted. The product name stays BolBazaar and lives in `web/src/brand.tsx`.
### Fixed
- The orb's decorative ring covered the button and swallowed taps (found by driving the UI in headless Chrome).
### Verified
- Headless Chrome against the live backend: tap-to-record with pause (clock freezes) and stop, sample visit → review → confirm → saved, all rep tabs, every manager page, drawer on phones, 390/360/768/1280/1440 widths, no horizontal overflow, no console errors beyond the expected 422 from a silent fake microphone. Screenshots in `docs/screenshots/`.
### Not verified
- Real speech through the mic, a physical phone, Safari/iOS. The Android APK predates this redesign and must be rebuilt.

## 2026-11-06 – Scope decision: call agent dropped
### Removed
- The payment-promise call agent (built on 2026-11-05 as a browser-simulated call) and everything it touched: `/v1/calls` API, `CallSession`/`CallTurn` models, the call state machine and classifier methods, the web call screen, the Calls tab and Call buttons, `CALL_AGENT.md`, its tests (back to 69) and screenshots. The visit/conversion metric filter added for it was reverted.
### Why
- Gnani's published API has no telephony; the only documented alternative (Sarvam) is a competing speech vendor, which does not fit a Gnani hackathon entry, and onboarding risk was too high for the remaining time.

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
