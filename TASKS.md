# Tasks

## Completed
- [x] Phase 1–3: reference analysis, opportunity analysis, scope tiers, design direction
- [x] Backend core (69 passing tests): domain, draft engine, providers, audio, persistence, capture lifecycle, commitments, manager metrics, auth
- [x] Live verification: one Gnani TTS → STT round trip and Azure strict-schema extraction (see CHANGELOG)
- [x] Voice-correction path bug found live and fixed (model path spellings normalised)
- [x] Web client `web/`: login, rep visit thread (hold-to-talk with level meter, 16 kHz WAV, draft ledger, clarification, voice/text correction, confirm, spoken reply, history, follow-ups), manager dashboard (KPIs, five panels, ask)
- [x] Device-side offline queue (IndexedDB, replays `POST /captures` with stored idempotency keys)
- [x] Capacitor Android project; debug APK builds (`web/android`)
- [x] Evaluation harness (`backend/eval`): 15 labelled cases + WER mode for your own clips
- [x] Render blueprint + Dockerfile, Vercel config, `DEMO_MODE` seeding for hosted demo
- [x] Call agent (simulated call): state machine, API, tests, web call screen, manager Calls tab; plan in CALL_AGENT.md
- [x] Docs: README, DEPLOYMENT, DEMO_SCRIPT, API reference draft shape, TESTING

## Next (owner actions first)
- [ ] **Deploy**: Render (API) then Vercel (web) — steps in DEPLOYMENT.md; needs your accounts and keys
- [ ] **Read the credit cost** of the 2 live Gnani calls at app.gnani.ai and tune `GNANI_DAILY_CALL_BUDGET`
- [ ] **Test the UI by hand** with a real microphone and real speech, then the APK on a phone (the UI was exercised in headless Chrome with a fake microphone, see CHANGELOG)
- [ ] Rebuild the APK after setting `VITE_API_URL` (the last APK predates the redesign)
- [ ] Record 10–20 real voice clips + `.txt` references into a folder and run `eval/run_eval.py --clips DIR` for real WER
- [ ] Record the 60-second demo from DEMO_SCRIPT.md; take screenshots into `docs/screenshots/`
- [ ] Rotate any key that was ever pasted into a chat or shared screen

## Later
- [ ] Real telephony adapter for the call agent (choose a provider, webhook auth, 8 kHz audio, latency); regulatory review first
- [ ] Alembic migrations and a Postgres run
- [ ] Native-speaker review of Hindi/Tamil/Marathi strings (UI and spoken confirmations); the web UI language selector offers Hinglish/Hindi/English only
- [ ] Periodic audio retention job (purges at start-up only)
- [ ] Voice input for the manager copilot (today text only)

## Known limitations
- Offline reasoner is a rule-based stand-in (Latin-script Hinglish/English only); live quality comes from Azure.
- Live Gnani coverage is one synthetic round trip (TTS audio fed to STT). Real human speech, noisy rooms, accents, long recordings, 429 behaviour and `timbre-v3.0` are untested.
- Android build is a debug APK, never run on a device or emulator in this session. It needs `VITE_API_URL` pointing at the deployed API before building.
- Render's free plan resets SQLite data on restart; Postgres is untested.
- One Gnani request at a time per key; long recordings are transcribed segment by segment.
- Extraction output varies between runs (temperature 0 is not deterministic on every deployment).
