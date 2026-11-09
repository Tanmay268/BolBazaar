# BolBazaar project map (for the demo studio)

Everything below was read from the repository, not assumed. Paths are relative to the repo root.

## Architecture

| Layer | What it is | Where |
|---|---|---|
| Web app | React 18 + TypeScript + Vite 5. One bundle; the role in the JWT decides rep UI or manager UI. Capacitor wraps it for Android. | `web/src` (`App.tsx` picks `RepApp` or `ManagerApp`) |
| API | Python FastAPI + SQLAlchemy, SQLite for dev/demo. Routes under `/v1`, health at `/health`. | `backend/src/bolbazaar/api/routes.py` |
| Auth | `POST /v1/auth/login` returns a JWT. The web app stores it in `localStorage` (`ff.token`, `ff.user`) and sends `Authorization: Bearer`. | `web/src/api.ts`, `backend/.../security.py` |
| Speech-to-text | Gnani (`GnaniSTT`, live) or `OfflineSTT` (stub). Selected by `SPEECH_MODE`/`PROVIDER_MODE`. | `backend/.../providers/{gnani,offline,factory}.py` |
| Text-to-speech | Gnani TTS (live) or `OfflineTTS` (a 0.3 s chirp). Used for the spoken confirmation after Confirm. | same |
| Extraction | Azure OpenAI strict JSON schema (live) or rule-based `OfflineReasoner`. Output is untrusted; the server validates, resolves customers/products against the catalogue and computes dates and prices. | `providers/azure.py`, `providers/offline.py`, `services/captures.py`, `domain/*` |
| Cost guard | Atomic DB quota ledger, kill switches, circuit breaker, per-user and global limits. | `backend/.../costguard.py`, `.env.example` |
| Manager analytics | Fixed SQL queries; the LLM only picks the query. | `services/metrics.py`, `POST /v1/manager/ask` |

Core rule of the product: **AI proposes, application code commits.** Nothing is written to business tables until the rep taps Confirm.

## Voice recording (web)

`web/src/recorder.ts` (`WavRecorder`) calls `navigator.mediaDevices.getUserMedia({audio})`, buffers PCM through a `ScriptProcessorNode`, downsamples to 16 kHz mono and encodes a WAV blob. Two controls use it:

- `rep/VoiceOrb.tsx` – main recorder. Tap (<450 ms) toggles recording, long press is push-to-talk.
- `rep/HoldToTalk.tsx` – spoken correction. Press and hold, release to send.

Because capture goes through the real `getUserMedia`, Chromium's fake-audio flags work: `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream --use-file-for-fake-audio-capture=<file.wav>%noloop`. The WAV is played once from the moment the stream opens. One browser process can use only one file, so the order and the correction are recorded in separate browser launches; the draft is resumed from the app's own "Waiting for you" list in between.

## Rep flow and the elements the studio uses

| Step | UI | Locator used |
|---|---|---|
| Sign in | login form | `getByLabel("Username")`, `getByLabel("Password")`, `getByRole("button",{name:"Sign in"})` |
| Skip first-run tour | dialog | `getByRole("button",{name:/^Skip/})` |
| Start | Today screen | `getByRole("button",{name:"Log a Visit"})` |
| Record | orb | `getByRole("button",{name:"Tap to record"})` → `"Stop recording"` → `"Stop and send"` |
| Review | `.rv` list | heading `Review Visit`; rows `.rv-row` (Retailer, Order, Delivery, Payment…, Follow-ups, Complaint); items `.rv-item`; `.rv-total b` |
| Clarification | `.block-ask` | chips (`.chip`) by product name |
| Correct | Edit toggle → hold-to-talk or typed field | `getByRole("button",{name:"Edit",exact:true})`, `getByRole("button",{name:/Hold to correct/})`, `getByLabel("Type a correction")`, `getByRole("button",{name:"Apply correction"})`, banner `.notice` |
| Confirm | footer | `getByRole("button",{name:/^Confirm/})` |
| Saved | `.saved` | heading `Visit Saved`, `.saved-quote`, `.saved-stats` |
| Resume | Log screen list | `getByRole("button",{name:/Ready to confirm\|Has a question/})` |

No change to application code was needed; the class-name locators are used only for read-only inspection of list rows that have no accessible name. If those classes change, add `data-testid` to `ReviewList.tsx` rows (non-functional) and update `scripts/record-demo.ts`.

## Manager flow

| Step | Locator |
|---|---|
| Overview | heading level 1 "Area Operations", `.mpanel` panels (Overdue Payments, Team Performance) |
| Ask | sidebar `getByRole("button",{name:"Ask",exact:true})`, `getByRole("textbox",{name:"Ask"})`, `.ask-go`, result `.answer` |

Question used: "Which retailers have overdue payments?" (one of the app's own suggestion chips; answered from the `overdue_payments` SQL query).

## API contracts the studio touches

`POST /v1/auth/login` · `POST /v1/captures` (multipart `audio`, `language`, header `Idempotency-Key`) · `GET /v1/captures` · `GET /v1/captures/{id}` · `POST /v1/captures/{id}/answers` · `/corrections` (typed) · `/corrections/audio` (multipart `audio`, `revision`) · `/confirm` (`Idempotency-Key`, `speakReply`) · `GET /v1/captures/{id}/reply-audio` · read-only verification: `GET /v1/orders` · `POST /v1/manager/ask` · `GET /health` (reports `speech=…,reasoner=…`).

## Data used

Seeded when `APP_ENV=development` (`backend/.../seed_data.py`): rep `asha` (Delhi), manager `meera`, password `demo123` (public dev password, `DEMO_PASSWORD`). Retailer "Sharma General Store" (alias "sharma ji"), products "Parle-G Biscuit" (₹10) and "Real Mango Juice 1L" (₹110). The studio starts its own backend on port 8100 with a throw-away SQLite file, so the main dev database is never touched.

## Existing tests and fixtures

- `backend/tests` (pytest, 178 tests incl. `tests/security`): no keys needed.
- `backend/eval/clips/recordings/*/*.wav` (git-ignored): real human recordings of Hinglish utterances with transcripts (`.txt`). `hinglish/hg01-order.wav` ("Sharma ji ne bees packet Parle-G liye aur das bottle Real mango kal dena hai.") is the order fixture.

## Demo prerequisites and honest limits

1. **Providers.** In offline mode the speech-to-text stub ignores the audio and returns a canned Hinglish transcript (`DEMO_TRANSCRIPTS`); extraction is rule-based. That transcript says "Real juice", which is ambiguous in the catalogue, so the app (correctly) asks which juice. The studio answers that question through the real UI. For results derived from the actual audio, run with live providers.
2. **Spoken correction** needs live speech-to-text *and* a `correction.wav` fixture. The repository has none; without it the studio uses the app's typed correction field and says so in the report.
3. **Spoken confirmation** is a real voice only with live TTS (offline it is a 0.3 s chirp, which the studio excludes from the video).
4. Claims to avoid (from `DEMO_SCRIPT.md`): offline transcription, accuracy numbers.
