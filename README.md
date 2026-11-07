# BolBazaar

> A voice-first execution layer for field sales teams. A representative talks; the system turns the conversation into **verified** visits, orders, collections, complaints and follow-ups, and speaks the result back.

**Status: backend (72 tests), rep + manager web app, Android wrapper and evaluation harness are built; live Gnani and Azure calls have been exercised end to end.** Render/Vercel deployment is configured but not yet deployed. The status column below says what is real.

## The problem

A rep visiting 15–20 retailers a day loses selling time to CRM data entry, forgets commitments, and gives managers a delayed, unreliable picture. BolBazaar removes the form: the rep speaks naturally (Hindi/English/Hinglish and other Indian languages), corrects by voice, and confirms once.

## What makes it different

| Differentiator | Meaning |
|---|---|
| Conversational correction | "No, Parle-G Rs 10 pack, not the 5" fixes the draft by voice; no re-recording |
| Commitment extraction | Promises ("he'll pay 5,000 tomorrow") become dated tasks, not notes |
| Context-aware references | "Same as last time", "that complaint from Monday" resolve against the customer's history |
| Multilingual input | Language chosen per capture; Gnani STT/TTS cover 10 Indian languages |
| Offline-first capture | Audio is recorded and queued offline; **transcription happens when online** (we do not claim offline STT) |
| Manager copilot | Questions answered by database queries, never by LLM guesses |

## Core rule

**AI proposes, application code commits.** LLM output is untrusted. Nothing is written to business tables until it passes schema validation, business validation and explicit rep confirmation.

## Feature status

| Module | Priority | Status |
|---|---|---|
| A. Voice interaction engine (record → Gnani STT → Gnani TTS) | P0 | Done. Hold-to-talk recorder with live level meter, 16 kHz WAV on web and Android. One live STT and one live TTS round trip verified; not yet tested with real human speech or on a physical phone |
| B. Visit & CRM management | P0 | Done (visit thread, history) |
| C. Smart order management (catalogue-validated) | P0 | Done; prices recomputed server-side |
| D. Commitment & follow-up engine | P0 | Done (extraction, due dates, complete/reschedule) |
| E. Manager dashboard + copilot | P1 | Done (SQL metrics + intent-based ask; text questions only, no voice) |
| F. Offline queue & sync | P1 | Done: IndexedDB queue replays `POST /captures` with stored idempotency keys. Transcription still needs a connection |

## Stack

React + TypeScript + Vite (`web/`, one codebase: rep app and manager dashboard by role) · Capacitor Android wrapper · Python FastAPI + SQLAlchemy (SQLite for dev/demo; Postgres untested) · Gnani STT/TTS over plain HTTP · Azure OpenAI strict JSON-schema extraction · Render (API) + Vercel (web). Cut from the MVP: Redis, Celery, AWS, text-to-SQL. See ADR-001.

## Screens

Mobile-first, with a framed phone layout on desktop and a two-column manager workspace. Design notes: [docs/DESIGN.md](docs/DESIGN.md); screenshots in [docs/screenshots/](docs/screenshots/).

## Evaluation (see [TESTING.md](TESTING.md))

15 labelled Hinglish/Hindi/English utterances scored on the application's own draft: 15/15 fully correct on each of the last two live runs (10–14/15 before the prompt was fixed; offline rule-based baseline 6/15); every ambiguous case asked instead of guessing; median extraction latency ~3 s. Small, developer-written and tuned against, so optimistic; text only, so speech-recognition error is not included. Not a benchmark.

## Documentation map

| File | Purpose |
|---|---|
| [PROJECT_PLAN.md](PROJECT_PLAN.md) | Opportunity analysis, scope tiers, roadmap, design direction |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Components and interactions |
| [API_DOCUMENTATION.md](API_DOCUMENTATION.md) | Endpoint summary (draft contract) |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | Tables and relationships |
| [TASKS.md](TASKS.md) | Done / pending / upcoming |
| [CHANGELOG.md](CHANGELOG.md) | Change history |
| [TESTING.md](TESTING.md) | Test and evaluation strategy |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | 60-second demo |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Environments and deployment |
| [docs/](docs/) | Deep-dive architecture, API reference, ADRs, screenshots |

## Originality

This project was designed independently. It uses general engineering lessons from a reference voice-order project (provider abstraction, idempotency, versioned drafts, post-commit TTS) but shares no code, schema, prompts, workflow or UI with it. See ADR-001.

## Setup

Backend (Python ≥ 3.11, [uv](https://docs.astral.sh/uv/), ffmpeg recommended for non-WAV audio):

```
cd backend
uv sync
uv run pytest -q                 # 81 tests, no keys needed
cp ../.env.example .env          # optional; defaults run offline (SQLite)
uv run bolbazaar-api            # http://localhost:8000  (docs at /docs)
```

Optional local PostgreSQL (needs Docker): `docker compose up -d db`, then `uv sync --extra postgres` and set
`DATABASE_URL=postgresql+psycopg://bolbazaar:bolbazaar@localhost:5432/bolbazaar` in `backend/.env`.
Tables are created on startup. Users can create their own accounts from the sign-up screen.

Web client (Node ≥ 20):

```
cd web
npm install
npm run dev                      # http://localhost:5173, talks to VITE_API_URL (default http://localhost:8000)
```

Sign in with the demo chips: `asha` opens the rep visit thread, `meera` the manager dashboard. Deployment (Render + Vercel + Android APK): [DEPLOYMENT.md](DEPLOYMENT.md). Demo script: [DEMO_SCRIPT.md](DEMO_SCRIPT.md). Evaluation: `uv run python eval/run_eval.py`.

Demo users (development only, password `demo123`): reps `asha` (Delhi), `ravi` (Chennai), `priya` (Pune); manager `meera`; `admin`.

Try it with no keys (typed transcript instead of audio):

```
TOKEN=$(curl -s localhost:8000/v1/auth/login -H 'content-type: application/json' \
  -d '{"username":"asha","password":"demo123"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s localhost:8000/v1/captures -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: demo-key-0001" \
  -F language=hinglish \
  -F "transcript=Sharma ji ne aaj bees packet Parle-G liye aur das bottle Real juice kal dena hai. Woh paanch hazaar rupaye kal dega."
```

To go live, set `PROVIDER_MODE=live`, `GNANI_API_KEY`, and the `AZURE_OPENAI_*` values (see [.env.example](.env.example)); never commit real keys.