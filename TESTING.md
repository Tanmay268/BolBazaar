# Testing and Evaluation

Status: strategy only; no tests exist yet.

## 1. Test layers

| Layer | Scope | Approach |
|---|---|---|
| Unit | Date normalisation, entity resolution, unit conversion, patch application, state machine | pytest, pure functions, table-driven |
| Provider contract | Gnani STT/TTS and LLM adapters | Injected fake clients/transports: request shape, retries and backoff, error categories, no secret/payload leakage |
| API integration | Real FastAPI routes with test Postgres and the offline provider | Full capture→clarify→correct→confirm; idempotent replay; stale revision; RBAC; tenant isolation |
| Atomicity | Commit rollback | Inject failure mid-commit and assert nothing persisted |
| Resilience | TTS failure after commit, provider timeouts, malformed LLM JSON | Assert order stays committed / graceful error |
| Frontend | Component and state tests; Playwright for the browser flow | Mock API |
| Live smoke | Real Gnani + LLM | Separate, opt-in, budget-capped |
| Offline/sync | Queue, duplicate upload, reconnect | Simulated network loss |

## 2. Evaluation harness (the hackathon differentiator)

A labelled dataset (target 40–60 utterances, mixed Hindi/English/Hinglish, some with background noise, some with deliberate ambiguity) stored with gold annotations: transcript, customer, products and quantities, collections, complaints, commitments with dates.

| Metric | Definition | Method |
|---|---|---|
| Transcription accuracy | Word error rate against human transcripts | Gnani `verbatim` vs `transcribe` compared |
| Extraction accuracy | Per-field precision/recall for customer, product, quantity, unit, date | Exact match after normalisation |
| Order accuracy | % of utterances where the final order matches gold | End-to-end |
| Task extraction accuracy | Commitment recall/precision, due-date correctness | |
| Clarification rate | Questions asked per capture; % necessary | Compare with ambiguity labels |
| Latency | Record end → draft ready (p50/p95); stage breakdown | Timing logs |
| Sync reliability | Successful offline→online syncs with zero duplicates | Fault-injection runs |
| Time saved | Timed manual CRM entry vs voice flow, same tasks | Small timed trial; report n |

Baselines: manual entry time; extraction with no catalogue/validation; ASR `verbatim` only. Report results honestly, including failures; do not extrapolate from a few samples.

## 2a. Credit budget rules (5,000 Gnani credits, unit unknown)
1. Day one: make a single real STT call and a single TTS call and read the dashboard to learn the cost unit, then size everything from that.
2. Default `PROVIDER_MODE=offline`; live only for smoke tests, the evaluation run and rehearsals.
3. `GNANI_DAILY_CALL_BUDGET` is a hard stop in the client; a 402 aborts the run cleanly.
4. Cache transcripts by audio hash so reruns of the evaluation do not re-bill; cache TTS by text+voice.
5. Reserve at least 30% of credits for demo rehearsals and the final recording.
6. Evaluation set stays small (40–60 clips of ≤28 s) and each clip is transcribed once per configuration compared.

## 2b. Android and browser parity
Every end-to-end scenario runs on both targets (Android device, desktop browser). A release is blocked if the 10-step scenario passes on one and not the other.

## 3. Running tests
```
cd backend
uv sync
uv run pytest -q          # 72 tests, ~15 s, no network, no keys
uv run python eval/run_eval.py            # live extraction evaluation (needs Azure keys)
uv run python eval/run_eval.py --offline  # rule-based baseline, no keys
uv run python eval/run_eval.py --clips DIR  # adds WER on DIR/<name>.wav + <name>.txt (spends Gnani calls)
cd ../web && npm run typecheck && npm run build
```
Not written: frontend unit tests, automated browser tests, live smoke tests in CI.

### Evaluation results (15 labelled cases, `backend/eval/cases.json`)
Scored on the application's draft after catalogue matching, not on raw model output. A case passes only if every labelled field is right; ambiguous cases pass only if the draft asks instead of guessing.

| Run | Fully correct | Notes |
|---|---|---|
| Azure, before prompt fixes | 10–14 / 15 | dropped second order line; missing payment follow-up; delivery date duplicated as a commitment |
| Azure, final prompt (2 runs) | 15 / 15, 15 / 15 | median 3.0 s, p95 5.4–6.5 s per extraction |
| Offline rule-based baseline | 6 / 15 | fails ambiguity asks, money, Devanagari |

Caveats: the cases were written by the developer who also tuned the prompt against them, so these numbers are optimistic; the set is small; text transcripts only (speech recognition error is not included); results vary between runs. "Modelled time per visit" printed by the harness (~26 s vs 240 s manual) rests on stated assumptions (speaking rate, review time, manual entry time) and has not been measured with users. WER is not yet measured: it needs real recorded clips.

### Live checks done by hand (2026-11-04)
One Gnani TTS call produced a 200 KB WAV; one STT call on that audio returned the transcript in about a second. The full API flow (capture → correction → confirm → spoken reply → manager views) ran on live providers. This used synthetic speech, not a human voice.

### What the 72 tests cover today
| File | Covers |
|---|---|
| `tests/test_domain.py` | Normalisation, number words, date resolution (incl. ambiguity), units, fuzzy matching ties, draft build/validate/patch, offline extraction of the Hinglish and English demo transcripts, correction whitelist |
| `tests/test_providers.py` | WAV splitting at silence, unsupported audio, Gnani request shapes (STT multipart, TTS JSON), retries and backoff, 402/401 handling with no secret leakage, daily budget stop, empty transcript, Azure strict schema, invalid-output rejection, Foundry route (all with mocked HTTP) |
| `tests/test_calls.py` | Call state machine (dates never guessed, amount above balance rejected, partial payments, corrections, turn limit), offline classifier, scripts in 3 languages, full call API incl. approval creating the promise, no commitment before approval, scoping, metrics exclusion |
| `tests/test_metrics_extra.py` | The manager numbers the UI shows: 30-day visit trend, next payment follow-up date per retailer, order value per rep |
| `tests/test_api.py` | The 10-step demo scenario end to end; audio upload path; idempotent create and confirm; stale revisions; STT failure then retry; no-speech error; TTS failure after commit; **atomic rollback**; auth and role checks; rep/territory isolation; manager metrics and ask; commitment updates; error envelope |

### Honest limits of the current suite
The automated suite uses mocked HTTP built from the documentation; live behaviour was checked once by hand (above) and by the evaluation harness. The first live calls matched the documented request shapes, but only one synthetic round trip has been made. The offline extractor is deliberately simple. The web client has no automated tests and its UI was not exercised in a browser in this session.

## 4. Definition of done for a module
Unit tests green, contract tests green, one end-to-end test through the API, error paths covered, docs and CHANGELOG updated.
