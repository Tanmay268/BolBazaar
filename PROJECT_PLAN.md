# Project Plan

## 1. Opportunity analysis (Phase 2)

### 1.1 Problem
Field reps spend selling time on admin, lose commitments, and give managers stale data. Voice is the right modality because reps are on their feet, hands busy, often in noisy shops, and think in spoken Hinglish, not form fields.

### 1.2 Honest assessment of the direction
- **Strength:** the interaction→action chain (speech → structured business events → confirmation → spoken reply) uses STT *and* TTS meaningfully, and the commitment engine is a genuinely uncommon angle.
- **Overlap risk:** Module C (spoken orders with clarification and confirmation) is the closest to the reference project's core. Mitigation: orders are one *section* of a visit bundle, validated against a **product catalogue** (the reference deliberately had none), and the story leads with visits and commitments.
- **Scope risk:** six modules is too much for a hackathon. We ship a thin, complete vertical slice (P0) and treat the rest as staged.
- **Claims discipline:** no offline STT claim; no analytics answered by an LLM.

### 1.3 Alternatives considered
| Idea | Why not chosen (or deferred) |
|---|---|
| Rural agri-advisory voice bot | Strong impact, but mostly Q&A; weak structured-action story |
| Voice-based clinic intake | Compliance and data-sensitivity burden for a demo |
| Voice banking assistant | Auth/fraud complexity; trust issues in a demo |
| Legal aid triage | Needs domain-vetted content; hard to evaluate |
| Citizen grievance filing by voice | Good fit, but less measurable than orders/tasks |
| **FieldForce AI** | Measurable (extraction accuracy, time saved), demoable in one scenario, STT+TTS essential |

### 1.4 Technical complexity
Medium-high. The hard parts are reliable Hinglish extraction, entity resolution against a catalogue, conversational correction, and date normalisation. These are exactly what the evaluation set will measure.

## 2. Scope tiers

| Tier | Contents | Done when |
|---|---|---|
| **P0 – demo-critical** | Record audio, Gnani STT, LLM extraction into a visit bundle (customer, 1–N order lines, collection promise, complaint, follow-up), catalogue/customer matching, ambiguity → one clarification at a time, voice or tap correction, review screen, confirm, commit, Gnani TTS confirmation, commitment list | The 10-step demo scenario runs end to end |
| **P1 – differentiators** | Manager dashboard with DB-backed KPIs, voice manager questions over a fixed catalogue of query intents, offline audio queue with idempotent sync | Dashboard shows the demo visit; offline capture syncs without duplicates |
| **P2 – stretch** | Streaming STT for live transcript, declining-demand insight, per-rep conversion, region targets, push reminders | Only if time allows |

Cuts versus the initial proposal: Redis/Celery/AWS (not needed for a demo; see ADR-001), text-to-SQL (replaced by fixed query intents), a separate local SQLite layer (start with file-queue + IndexedDB).

## 3. Roadmap

| Phase | Output |
|---|---|
| 0 | Docs, decisions, repo scaffold *(this stage)* |
| 1 | Backend skeleton: config, provider interface (offline + live), DB migrations, seed catalogue/customers |
| 2 | Gnani STT/TTS adapters verified against live docs; audio normalisation; capture lifecycle |
| 3 | Extraction schema, prompts, validators, entity resolution, clarification engine |
| 4 | Correction patches, confirm/commit transaction, idempotency, outbox, TTS post-commit |
| 5 | Rep mobile app (new UX, below) |
| 6 | Commitments and manager dashboard |
| 7 | Offline queue and sync |
| 8 | Evaluation harness, metrics, demo polish, deployment |

Gate before each phase: working end-to-end behaviour is preferred over more features.

## 4. Design direction (deliberately unlike the reference app)

The reference uses a light pastel, phone-framed screen with a glowing orb and bottom tabs. FieldForce AI uses a different information design:

- **Conversation-first "visit thread"** instead of a single record button: the rep's transcript appears as a thread, and typed cards (Order, Collection, Complaint, Follow-up) assemble beneath it as the system extracts them. Cards show confidence and the source phrase.
- **Dark, high-contrast "sunlight" theme** with large touch targets, built for outdoor/shop use; light theme optional.
- **Hold-to-talk waveform bar** driven by real microphone level, docked at the bottom, with an explicit "listening / transcribing / thinking / speaking" status strip.
- **Route-based home:** today's planned visits as a timeline with overdue commitments badged, not a tab grid.
- **Correction by tapping a card or saying a fix**, shown as a diff (old → new) before applying.
- **Manager dashboard:** dense table + KPI strip + chat-style "ask" panel whose answers cite the query used.
- Distinct typography, colour system and iconography from the reference; design tokens defined in code, not copied.

Screens: Home (route) · Visit thread · Review & confirm · Commitments · Customer 360 · Sync status · Settings; Manager: Overview · Reps · Retailers · Collections · Ask.

## 5. Success criteria
Defined in [TESTING.md](TESTING.md): transcription, extraction, order and commitment accuracy; clarification rate; latency; sync reliability; time saved versus manual entry, all against a labelled test set with a stated baseline.

## 6. Programme fit (Phase 3)

Shortlisting is by engagement on nominated posts plus review of submissions that show genuine Gnani usage; ten separate ₹50,000 awards exist and a team can win only one. Post engagement is outside the codebase; what the product controls is submission quality and award fit.

| Award category | Fit | How we earn it honestly |
|---|---|---|
| Hinglish / code-mixed voice | **Strongest** | Hinglish capture is the default scenario: STT `prisma-v3.0` + `format=codemix`, TTS `hi-en` voice; measured on a code-mixed test set |
| Best 60-second demo | **Strong** | Design the 10-step scenario so the happy path fits ~60 s |
| Regional languages | Good | One regional language (Tamil or Marathi) run through the same pipeline and metrics |
| Real-world impact | Good | Time-saved trial and data-quality metrics |
| Noisy audio | Possible | Include noisy shop recordings in the evaluation set; do not claim telephony |
| Solo/duo, Tier 2/3 | Depends on team facts | Unknown; not designed for |
| Creativity, Crowd Favourite | Depends on execution | Commitment extraction and the new thread UX |

We aim at Hinglish plus the 60-second demo and treat the rest as upside. Requirement: genuine, visible Gnani usage (STT and TTS essential, not decorative).

## 7. Resolved inputs
- LLM: Azure OpenAI available (student pack). Confirm quota and a deployment that supports strict JSON-schema output.
- Gnani: 5,000 credits. **The credit unit and per-call cost are not documented**; measure with one real call on the dashboard before planning volume (see TESTING.md budget rules).
- Demo languages: Hinglish/Hindi (primary), English, plus one regional language (recommend Tamil; Marathi is the alternative). Change only if you prefer.
- Demo device: Android primary, browser with identical flow and equal reliability (recorder differences handled in ARCHITECTURE.md).

## 8. Still open
1. Theme/judging weights beyond the award list, and submission deadlines (engagement cutoff dates).
2. Team size (solo/duo affects an award category).
3. Credit unit and per-call cost.
