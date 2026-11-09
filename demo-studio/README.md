# BolBazaar Demo Studio

Generates a 75–90 s, 1080p, 30 fps product demo (`artifacts/demo/bolbazaar-demo.mp4`) from the **real** BolBazaar app: Playwright drives the actual UI and backend, Remotion adds the cinematic layer, FFmpeg finishes the audio. No manual recording or editing.

```
fixtures/*.wav ──► Chromium fake microphone ──► real app (record → STT → extract → correct → confirm → manager)
                                                     │ scene recordings + event timeline (cursor, clicks, element boxes)
narration text ──► TTS provider (cached) ────────────┤
                                                     ▼
                                   Remotion composition ──► FFmpeg loudnorm ──► MP4 ──► ffprobe validation ──► report
```

Architecture details and the exact selectors/routes are in [PROJECT_MAP.md](PROJECT_MAP.md).

## Quick start

```bash
cd demo-studio
npm install
npx playwright install chromium
cp .env.example .env            # defaults work for the isolated offline demo
npm run demo:check              # preflight, no app started, no spend
npm run demo:all                # everything, ends with artifacts/demo/bolbazaar-demo.mp4
```

| Command | Does |
|---|---|
| `npm run demo:check` | Tools, config, fixtures, safety gates (and app + accounts when it is already running) |
| `npm run demo:voice` | Generate or reuse narration clips + manifest |
| `npm run demo:record` | Start the isolated stack, record the scenes, verify the app's behaviour |
| `npm run demo:render` | Plan the timeline, render with Remotion, loudness-normalise with FFmpeg |
| `npm run demo:validate` | ffprobe/ffmpeg validation, writes `demo-report.json` and `.md` |
| `npm run demo:all` | check → voice → record → render → validate → report |
| `npm run demo:cleanup` | Delete the throw-away database, audio, auth state, raw recordings |
| `npm run studio` | Remotion Studio for tweaking the visuals (after one render, `.runtime/plan.json` has the props) |

Useful flags for `demo:all` (after `--`): `--scenes=manager` re-records only those scenes (`rep-order`, `rep-correct-confirm`, `manager`; earlier data is kept), `--skip-record` re-renders from existing recordings, `--force-voice` regenerates narration, `--headed` shows the browser, `--debug` saves screenshots to `artifacts/demo/debug`.

## Prerequisites

Node ≥ 20, FFmpeg + ffprobe on `PATH`, the backend environment (`cd backend && uv sync`) and the web dependencies (`cd web && npm install`), Playwright Chromium. Windows is what this was built and tested on (the stack launcher uses `backend/.venv/Scripts/python.exe` and `taskkill`).

## What the studio starts (safety)

By default (`DEMO_MANAGE_ENV=true`) it starts **its own** backend on `127.0.0.1:8100` and Vite on `127.0.0.1:5273`, with a fresh SQLite file in `demo-studio/.runtime/` and separate audio storage. Your normal dev database is never opened. Provider keys are blanked in that process unless you opt in to live mode. Rules enforced in code:

- Remote URLs are refused unless `DEMO_ALLOW_REMOTE=true` (use a staging stack, never production).
- Live providers need both `DEMO_PROVIDER_MODE=live` **and** `DEMO_ALLOW_PAID_APIS=true`; the managed backend also gets `GNANI_DAILY_CALL_BUDGET=DEMO_MAX_PAID_CALLS` and preflight fails if the expected call count (~6 per run) exceeds `DEMO_MAX_PAID_CALLS`.
- Authentication is never bypassed: tokens come from the real login form. Credentials come from `.env`, are typed into the page headlessly and never appear in recordings (the password field is masked and login is not recorded). `.env`, tokens (`.runtime/state-*.json`), audio and videos are git-ignored.
- Verification is read-only (`GET /v1/orders`); nothing is deleted or modified in an existing environment.
- Any failed expectation (wrong retailer, quantity, total, missing success state…) stops the run. No video is produced and the report says why; stale outputs from earlier runs are deleted first.

## Environment variables

See [.env.example](.env.example). The important ones:

| Variable | Default | Meaning |
|---|---|---|
| `DEMO_MANAGE_ENV` | `true` | Start/stop the isolated backend + web. `false` = use `DEMO_WEB_URL`/`DEMO_API_URL` that you run yourself |
| `DEMO_PROVIDER_MODE` | `offline` | `live` = real Gnani STT/TTS and Azure OpenAI (keys come from `backend/.env`) |
| `DEMO_ALLOW_PAID_APIS`, `DEMO_MAX_PAID_CALLS` | `false`, `12` | Spending gate and ceiling for live mode |
| `DEMO_REP_USER/PASSWORD`, `DEMO_MANAGER_USER/PASSWORD` | `asha`/`meera`, `demo123` | Demo accounts (seeded dev accounts; override for staging data) |
| `TTS_PROVIDER` | `edge` | `edge`, `elevenlabs`, `sapi` |
| `EDGE_VOICE` | `en-IN-NeerjaExpressiveNeural` | Voice for the free Edge neural provider |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL` | – | ElevenLabs |
| `TTS_MAX_CHARS_PER_RUN`, `TTS_MAX_REQUESTS_PER_RUN` | `2500`, `12` | TTS request/spend ceiling |
| `DEMO_WEBSITE_URL` | – | Shown on the outro when set |

Expected demo data (retailer, products, quantities, payment, question) lives in `config/demo.config.ts` (`expect`) and the narration in `config/scenes.ts`. Edit those to change the story; the recorder asserts against them.

## Audio fixtures

The app records through `getUserMedia`, so fixtures are fed to Chromium's fake microphone (`--use-file-for-fake-audio-capture`). Requirements: RIFF WAV, ideally 16 kHz mono 16-bit PCM, 1–28 s (the speech API caps a segment at ~30 s).

- `fixtures/rep-order.wav` — the initial visit. The repository's `backend/eval/clips/recordings/hinglish/hg01-order.wav` is used (a real recording: *"Sharma ji ne bees packet Parle-G liye aur das bottle Real mango kal dena hai."*). For the full story of `DEMO_SCRIPT.md` (payment, complaint, next visit) record that whole utterance instead: `cd backend && uv run python eval/clips/record_clips.py --list-devices`, or record any WAV and convert with `ffmpeg -i in.m4a -ac 1 -ar 16000 -sample_fmt s16 fixtures/rep-order.wav`.
- `fixtures/correction.wav` — *"Parle-G pandrah kar do"* (about 2 s). Optional; with live providers it enables the **spoken** correction. Without it the typed correction field is used and the narration/report say so.

WAVs are git-ignored (they are personal voice recordings).

## Narration and TTS

`config/scenes.ts` holds Hinglish narration (Latin script) and the English subtitle for each line. `lib/tts.ts` has a small provider interface (`edge`, `elevenlabs`, `sapi`); add another by implementing `TtsProvider` and registering it in `getProvider`.

- **edge** (default): Microsoft Edge neural voices via `msedge-tts`. Free, no key, needs internet, and sends only the public narration script. Indian-English voice reading Hinglish.
- **elevenlabs**: set `ELEVENLABS_API_KEY` and an Indian-accent `ELEVENLABS_VOICE_ID`, `TTS_PROVIDER=elevenlabs`.
- **sapi**: offline Windows voices (English only, robotic).
- **Manual fallback**: drop your own recordings in `assets/generated-voice/manual/<scene>-<n>.mp3|wav|m4a` (for example `intro-1.mp3`); they take precedence over any provider.

Clips are cached by SHA-256 of voice + text in `assets/generated-voice/`, so reruns cost nothing. Edit a line and only that clip is regenerated. `npm run demo:voice -- --force` regenerates everything. Spoken correction swaps in a different line for the correction scene (`SPOKEN_CORRECTION_LINE`) so the narration never claims something the recording does not show.

## How the video is made

1. `record-demo.ts` records three scenes (`rep-order`, `rep-correct-confirm`, `manager`) with Playwright `recordVideo`, plus a JSON timeline of semantic events: mouse path, clicks, markers, and the bounding boxes of real elements. Playwright's video has no cursor, so the cursor is drawn later from that timeline.
2. `lib/plan.ts` turns narration lengths and markers into a frame-accurate plan: scene durations, piecewise speed-ramps of the recordings (never altering content), zoom keys, focus boxes, subtitles (also exported as `assets/subtitles/bolbazaar-demo.srt`), music ducking.
3. `remotion/` renders brand scenes, device frames, camera zoom, focus boxes, cursor, waveform of the *real* fixture audio, subtitles and transitions. Only recorded footage supplies app content; overlays contain labels from the app's own UI and values read back from the DOM.
4. FFmpeg normalises loudness (−16 LUFS, −1.5 dBTP). Music and sound effects are synthesised from scratch by `lib/synth.ts` (no third-party material) and ducked under narration.

## Validation and reports

`npm run demo:validate` checks: recordings, clips and subtitles exist; MP4/H.264/AAC; 1920×1080; 30 fps; duration 75–90 s; audio present, audible, not clipping; audio/video lengths in sync; matches the plan; full decode without errors; no blank scene (2 sampled frames each); no console/page/5xx errors and no failed interaction during recording. Output: `artifacts/demo/demo-report.json` and `demo-report.md` with a per-scene table.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Executable doesn't exist … chromium` | `npx playwright install chromium` |
| `Timed out waiting for backend /health` | Read `.runtime/backend.log`; run `cd backend && uv sync` |
| Port 8100/5273 in use | Change `DEMO_API_URL`/`DEMO_WEB_URL`, or stop the stale processes (`npm run demo:cleanup`) |
| `Expectation failed: …` | The app's behaviour differs from `config.expect`. Run with `--headed --debug` and look at `artifacts/demo/debug/*-failure.png` |
| Microphone permission / "Stop recording" never appears | Fixture missing or not a WAV; run `npm run demo:check` |
| `Review Visit` never appears (live mode) | STT returned nothing: check the fixture is audible speech; see `.runtime/backend.log` and the app's cost guard limits |
| Subtitles overflow or timing feels off | Shorten the line in `config/scenes.ts`, then `npm run demo:voice` |
| Video over 90 s | Shorten narration or reduce `minSeconds`/`tail` in `config/scenes.ts` |
| First render downloads a browser | Remotion fetches Chrome Headless Shell once (~130 MB) |

## Cleaning up demo data

In the default managed mode all demo records (users, retailers, orders, visits, audio) live only in `demo-studio/.runtime/` and are deleted at the next start or by `npm run demo:cleanup` (`--all` also removes recordings and the video). With `DEMO_MANAGE_ENV=false` the studio creates one visit/order in whatever environment you point it at. It never deletes records there; remove the order for the demo retailer manually (staging DB) and restart or reset that environment.

## API spending

Offline mode spends nothing. Live mode makes roughly: 1 STT + 1 LLM for the order, 1 LLM (typed) or 1 STT + 1 LLM (spoken) for the correction, 1 TTS for the confirmation reply, 1 LLM for the manager question ≈ 5–6 calls per run, bounded by `DEMO_MAX_PAID_CALLS` and by the backend's own cost guard. Narration is cached, so TTS cost is paid once per line; `TTS_MAX_*` caps it. Do not run `demo:all` in a loop in live mode; use `--skip-record` to re-render, and `--scenes=` for a single re-recording.

## Known limitations

- Recorded against offline providers, the speech-to-text step is the app's stub (it ignores the audio and returns its canned transcript) and extraction is rule-based. The recorded pipeline is real, the transcript is not derived from the fixture. The report states the provider mode of every run.
- Playwright video is 1× device pixels: zooms are limited to ~1.4× to keep text crisp.
- Edge/ElevenLabs read Latin-script Hinglish with an English-leaning accent; for the best pronunciation record the narration yourself (manual fallback above) or pick a Hindi-capable voice.
