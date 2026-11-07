# BolBazaar Test Report Guide

How to test BolBazaar end to end and write a test report that a reviewer can trust. It complements [TESTING.md](TESTING.md) (strategy and the evaluation design) and [DEMO_SCRIPT.md](DEMO_SCRIPT.md). Follow the parts in order; each ends with what to record.

**Ground rules**
- Record what you observed, not what you expect. A failure written down honestly is worth more than a pass you cannot back up.
- Every number needs its sample size (n) and how it was measured. If n is small, say so next to the number.
- Attach evidence for every claim: command output, screenshot, screen recording or log line. Name the file in the report.
- Never put secrets in the report (API keys, tokens, anything from `.env`). Redact before pasting logs.
- Spend live credits deliberately (see Part 7). Default to `PROVIDER_MODE=offline` unless a step says live.

---

## 0. Report skeleton (copy this)

```
# BolBazaar Test Report
Version / commit:        Date:        Tester:
Environments tested:     (see Part 1)
Scope:                   what was tested; what was NOT tested and why
Summary:                 3-5 lines: pass rate, headline metrics, open blockers
1. Environment and setup
2. Automated tests            (Part 2)
3. Functional scenarios       (Part 3, table of IDs with pass/fail)
4. Voice and language tests   (Part 4)
5. Evaluation metrics         (Part 5)
6. Non-functional tests       (Part 6: performance, offline, security, usability)
7. Defects found              (table: ID, severity, steps, status)
8. Limitations and risks      (be specific)
9. Conclusion and go / no-go
Appendix: raw logs, screenshots, datasets, commands run
```

**Summary rules:** lead with the verdict, then the three numbers that matter most, then the open blockers. A reader who stops after the summary should not be misled.

---

## 1. Environment and setup (record all of it)

| Item | Record |
|---|---|
| App version / build | Git commit or date; `web/package.json` version; APK file name and size |
| Backend | Local or Render URL; Python version; `PROVIDER_MODE` (offline / live) |
| Speech models | `GNANI_STT_MODEL`, TTS model and voice per language |
| LLM | Provider and model name used for extraction |
| Web browsers | Browser and version (e.g. Chrome, Edge), desktop and mobile widths |
| Android devices | Phone model, Android version, RAM, network type (Wi-Fi / 4G) |
| Test accounts | Roles used (rep `asha`, manager `meera`), seed data used |
| Network | Speed and latency if measured; whether throttling was used |

**Setup steps**
1. Backend: `cd backend && uv sync`, copy `.env.example` to `.env`, set `PROVIDER_MODE`.
2. Web: `cd web && npm install && npm run dev` (or `npm run build && npx vite preview`).
3. APK: `npm run cap:sync`, then `gradlew assembleDebug` using Android Studio's JDK (Java 24 will not work with this Gradle), then install (see Part 3, A-series).
4. Reset data before each full pass (restart the service or reseed) so runs are comparable.

---

## 2. Automated tests

Run and paste the full result line each time.

| Check | Command | Record |
|---|---|---|
| Backend unit + API + security tests | `cd backend && uv run pytest -q` | Passed / failed / skipped counts, duration |
| Failures | `uv run pytest -q -x --tb=short` | Test name and error for each failure |
| Coverage (optional) | `uv run pytest --cov=bolbazaar` | Overall % and the weakest modules |
| Web typecheck | `cd web && npm run typecheck` | Pass / errors |
| Web build | `cd web && npm run build` | Pass; bundle size (JS and CSS, gzip) |
| Lint (if configured) | project linter | Warning / error count |

State plainly what has **no** automated tests (today: frontend unit tests, automated browser tests, live smoke tests in CI). A "not covered" list is part of an honest report.

---

## 3. Functional test scenarios

Run each scenario on **both targets**: desktop browser and the Android APK (TESTING.md rule: a release is blocked if a scenario passes on one and fails on the other). Record result per target.

Use this table in the report:

| ID | Scenario | Steps (short) | Expected | Browser | APK | Evidence | Notes |
|---|---|---|---|---|---|---|---|

### A. Install and launch
| ID | Scenario | Expected |
|---|---|---|
| A1 | Website install button, signed out | Circular download button at the bottom-right of the sign-in page; tapping it downloads `BolBazaar.apk` |
| A2 | Website install button, signed in | Button moves to the top-right; same download |
| A3 | Install APK on a real phone | Installs (after allowing unknown apps); app icon is the red sound-wave on paper background |
| A4 | Install button inside the APK | Not shown in the app |
| A5 | Favicon and tab icon | Sound-wave logo in the browser tab |
| A6 | Intro animation | Waveform bars bloom in, ripple like a live signal, then dissolve into the home page; about 4 s; no white flash before or after; no "BolBazaar" caption |
| A7 | Reduced motion | With the OS "reduce motion" setting on, the intro is skipped |
| A8 | Cold start time | Time from tap to usable home page. Record median of 5 launches |

### B. Authentication and roles
| ID | Scenario | Expected |
|---|---|---|
| B1 | Rep sign-in, valid | Lands on the rep home |
| B2 | Manager sign-in, valid | Lands on the manager workspace |
| B3 | Wrong password | Clear error; no lockout surprise; no detail leak |
| B4 | Session expiry / sign-out | Returns to sign-in; no stale data visible |
| B5 | Rep cannot open manager pages | Blocked (also by direct API call; see Part 6.4) |

### C. Core voice flow (the 10-step scenario)
| ID | Scenario | Expected |
|---|---|---|
| C1 | Hold mic, speak a visit in Hinglish | Live waveform follows your voice; draft appears |
| C2 | Draft correctness | Customer, products, quantities, units, payment, complaints, follow-ups match what you said |
| C3 | Totals and dates | Computed by the server (not the AI); dates resolved correctly ("kal", "agle Monday") |
| C4 | Ambiguity | Ambiguous customer/product makes the app ask a question instead of guessing |
| C5 | Voice correction | "Parle-G pandrah kar do" changes the quantity and recomputes the total without re-recording |
| C6 | Confirm and save | Saves once; spoken confirmation plays |
| C7 | Typed fallback | "Can't talk? Type it" and the sample visit go through the same pipeline |
| C8 | Manager sees the visit | Appears in totals, overdue payments and follow-up lists |
| C9 | Idempotency | Double-tapping Confirm, or retrying after a drop, never creates a duplicate order |
| C10 | Stale edit | Editing an outdated draft is rejected cleanly |

### D. Offline and sync
| ID | Scenario | Expected |
|---|---|---|
| D1 | Record in airplane mode | "1 recording waiting to upload" banner; no crash |
| D2 | Reconnect | Uploads automatically; one draft; zero duplicates |
| D3 | Close the app while queued | Queue survives restart |
| D4 | Repeat 10 times | Record the success rate and duplicate count (this is a metric) |

### E. Manager workspace
| ID | Scenario | Expected |
|---|---|---|
| E1 | Dashboard tiles | Numbers match the underlying visits (check by hand against the data) |
| E2 | Questions like "Which retailers have overdue payments?" | Correct list; no invented retailers |
| E3 | Tenant isolation | Manager sees only their organisation's data |

### F. UI, language and accessibility
| ID | Scenario | Expected |
|---|---|---|
| F1 | UI language toggle (EN / हि) | All visible strings switch; nothing clipped |
| F2 | Layouts | Check 360, 390, 768 and 1280 px widths; no horizontal scroll; nothing hidden behind the install button |
| F3 | Keyboard and screen reader | Tab order sensible; buttons have labels (install button has an accessible name) |
| F4 | Contrast and tap size | Tap targets about 40 px or more; text readable on the paper background |

---

## 4. Voice and language tests

The app supports 11 speech languages: Hinglish, Hindi, English (India), Marathi, Gujarati, Punjabi, Bengali, Tamil, Telugu, Kannada, Malayalam. Test each one; do not assume the same result as Hindi.

**Per language, record:**

| Language | Picker label correct? | STT works? | Draft quality (1-5) | Clarification question reads correctly? | Spoken confirmation plays and sounds right? | WER (if measured) | Notes |
|---|---|---|---|---|---|---|---|

**Steps (repeat for every language)**
1. Select the language in the picker (note: it is chosen per capture).
2. Speak 3 test utterances: a simple order, an order with a payment promise, and one deliberately ambiguous.
3. Check the transcript, the draft and the follow-up question text.
4. Confirm and listen to the spoken reply.
5. Have a **native speaker** judge the question text, confirmation text and voice naturalness. The Hindi, Tamil, Marathi and all newer translations are drafts until a native speaker has reviewed them; state who reviewed what, or say "not reviewed".

**Also test**
- Accents, speaking speed, and background noise (shop noise, traffic). Record the noise level or source.
- Numbers and money said in words ("paanch hazaar") vs digits. Note that number-to-digit formatting is documented only for Hindi and English; other languages may return spoken words.
- Mixed speech (Hindi + English words) in the non-Hinglish languages.
- Unsupported language code sent directly to the API returns `UNSUPPORTED_LANGUAGE`.

---

## 5. Evaluation metrics (the numbers section)

Run these on a labelled dataset (target 40-60 utterances: mixed languages, some noisy, some ambiguous). Keep the dataset and gold labels in the appendix. The existing harness is `backend/eval/run_eval.py` with `backend/eval/cases.json` (15 cases today; say so if you do not extend it).

```
cd backend
uv run python eval/run_eval.py --offline          # baseline, no keys
uv run python eval/run_eval.py                    # live extraction (needs keys)
uv run python eval/run_eval.py --clips DIR        # adds WER; spends Gnani credits
```

| Metric | Definition | How to compute | Report as |
|---|---|---|---|
| **Word error rate (WER)** | (substitutions + deletions + insertions) / words in the human transcript | Compare STT output with a human transcript per clip; compare `verbatim` vs `transcribe` | Mean and range per language, n clips |
| **Field precision / recall** | Per field (customer, product, quantity, unit, date, payment): correct / predicted and correct / gold | Exact match after normalisation | Table per field |
| **Order accuracy** | % utterances where the final order equals gold, every field right | End to end | `x / n` and % |
| **Task extraction accuracy** | Commitments found (recall), correct ones (precision), due date right | Compare with labelled commitments | Recall, precision |
| **Clarification rate** | Questions asked per capture; % of questions that were necessary | Compare with ambiguity labels | Mean per capture; % necessary |
| **Wrong-guess rate** | Ambiguous cases where the app guessed instead of asking | From the ambiguous subset | Count / n (this should be near zero) |
| **Latency** | Recording end to draft ready; per stage (upload, STT, LLM, validation) | Timing logs | p50 and p95 in seconds, n runs |
| **Spoken-reply latency** | Confirm tapped to audio starts | Stopwatch or logs | p50 and p95 |
| **Sync reliability** | Offline recordings that synced with zero duplicates | Fault-injection runs (Part 3 D4) | `x / n` |
| **Time saved** | Manual CRM entry time vs voice flow, same tasks | Timed trial, 3+ people, 5+ visits each | Mean time each way, n people, n visits |
| **Crash / error rate** | Sessions with a crash or blocking error | Count across all manual runs | `x / n` sessions |
| **Cost per capture** | Gnani credits plus LLM tokens per completed visit | From dashboards and logs | Average and worst case |
| **App size and startup** | APK size; cold-start time | File size; 5-launch median | MB and seconds |

**How to present results**
- Always give `x / n`, not just a percentage. 14/15 and 93/100 are not the same evidence.
- Show the failures, not only the average: list each failed case with what the app produced vs what was expected.
- Separate **text-only** results (transcript fed in) from **speech** results (audio through STT). Text-only results exclude recognition error and flatter the system; label them as such.
- If you tuned prompts or rules against the cases, say so: the numbers are optimistic. Prefer a held-out set for the headline figure.
- Compare against baselines: manual entry time, extraction without catalogue validation, `verbatim`-only transcription, and the offline rule-based baseline.
- Do not extrapolate (for example, "saves 3 hours a day") from a handful of samples. If you must, state the assumptions beside it and mark it as modelled, not measured.

---

## 6. Non-functional tests

### 6.1 Performance
- Backend latency under load: a few concurrent users (for example 5, 10, 25). Record p50, p95 and error rate. Include the wake-up delay if the host sleeps (Render free tier).
- Front end: cold start time on a mid-range Android phone; check the intro stays smooth (no dropped frames you can see). Record the device.
- Bundle size: JS and CSS gzip from `npm run build`.

### 6.2 Reliability and resilience
- STT or TTS failure after commit: the order stays saved; the user gets a graceful message.
- Provider timeout and malformed model output: the app shows an error or asks again; nothing is half-saved.
- Mid-commit failure: nothing partial persisted (atomicity test in the suite).
- Lose network mid-upload; kill the app mid-upload; restart the backend while a draft is open.

### 6.3 Credit and cost protection
- Per-user and global rate limits hold (`USER_STT_PER_MINUTE` etc.): exceed them on purpose and confirm a clean refusal, not a crash.
- Daily call budget stops calls when exhausted (`GNANI_DAILY_CALL_BUDGET`).
- Transcript and TTS caches avoid re-billing on reruns (compare credit usage before and after a repeat run).

### 6.4 Security (see `security/` reports for the full audit)
- Role checks hold when calling the API directly (rep token on manager endpoints).
- Tenant isolation: a second organisation's data is never returned.
- No secrets in the web bundle, APK, logs or error messages. Note: the APK is a debug build.
- Input handling: oversized audio, wrong content type, extremely long text, invalid language code.
- Report the status of the open release blockers from the latest audit; do not call the release "secure", only what you tested.

### 6.5 Usability
- 3-5 real users (ideally field reps) complete the visit flow unaided. Record: task completed (yes/no), time, errors, where they hesitated, and one quote per person.
- Ask them one question: "What would stop you from using this every day?"

### 6.6 Compatibility
- Browsers: latest Chrome and Edge at least; Safari if claimed.
- Android: at least two versions and two screen sizes. Note any device where the mic permission flow differs.

---

## 7. Credit and run planning

Gnani credits are limited and the unit is easy to misjudge.
1. First, make one real STT and one real TTS call and read the dashboard to learn the cost unit; size everything else from that.
2. Do all functional passes in `offline` mode; use live only for the smoke test, the evaluation run and rehearsals.
3. Keep at least 30% of credits for demo rehearsals and the final recording.
4. Transcribe each clip once per configuration compared, and cache by audio hash.
5. Log how many credits each section of testing consumed; include the total in the report.

---

## 8. Defect log

Every failure gets an entry. Do not leave a failed row without one.

| ID | Title | Severity | Steps to reproduce | Expected | Actual | Env (browser / device) | Evidence | Status |
|---|---|---|---|---|---|---|---|---|

**Severity guide**
- **Blocker:** data loss, duplicate or wrong orders, security hole, app unusable.
- **High:** a core flow fails on one target or in a main language.
- **Medium:** wrong but recoverable behaviour; poor quality in one language.
- **Low:** cosmetic, wording, minor layout.

Summarise counts by severity in section 7 of the report and list which blockers are still open.

---

## 9. Limitations section (do not skip)

State, specifically:
- Sample sizes and who wrote the test cases (and whether they also tuned the system against them).
- Languages or devices not tested, and languages whose text was not reviewed by a native speaker.
- What was text-only vs real audio.
- Anything that used `offline` provider mode and so does not reflect live behaviour.
- The debug APK (not a signed release build) and the single environment it ran in.
- Modelled numbers (time saved) vs measured ones.

---

## 10. Final checklist before you send the report

- [ ] Version, date, environments and devices are stated.
- [ ] Every table row has a result; every failure has a defect entry.
- [ ] Every headline number has `x / n`, a method and evidence.
- [ ] Each scenario was run on both browser and APK (or the gap is stated).
- [ ] Every language was tried, and native review status is stated.
- [ ] Limitations are listed, not buried.
- [ ] No secrets or personal data in logs and screenshots.
- [ ] The conclusion says go / no-go and names the open blockers.
- [ ] Raw evidence is in the appendix and the file names match the report.
