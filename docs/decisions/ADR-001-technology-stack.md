# ADR-001: Technology Stack

- **Status:** Accepted for planning (Azure OpenAI access confirmed 2026-11-04; theme details still pending)
- **Date:** 2026-11-04

## Context
Hackathon timeline, a small team, one demo scenario, and required use of Gnani STT and TTS. The initial proposal listed React/Capacitor, FastAPI, Azure OpenAI, PostgreSQL, Redis, Celery, SQLite on device, Docker and AWS.

## Decision

| Layer | Choice | Reason |
|---|---|---|
| Rep app | React + TypeScript + Capacitor | One codebase for Android and browser demo; native recorder plugin |
| Manager dashboard | React + TypeScript (Vite) | Shared types and components with the rep app |
| Backend | Python + FastAPI, modular monolith | Fast to build; strong typing via Pydantic; team familiarity |
| Database | PostgreSQL | Relational integrity, jsonb for drafts, trigram search, real transactions (ADR-002) |
| STT / TTS | Gnani (REST first) | Hackathon requirement; REST is sufficient for P0 |
| Reasoning | Azure OpenAI with strict JSON schema output | Reliable structured extraction; **requires confirmed access** |
| Background work | In-process scheduler + DB outbox table | Enough for reminders/TTS at demo scale |
| Offline (device) | File storage + IndexedDB queue | Captures are audio blobs plus metadata; no need for a full SQLite replica |
| Packaging | Docker Compose | Reproducible local and demo environments |

## Deliberately not adopted for the MVP
- **Redis and Celery:** no workload requires a broker yet; the outbox table plus a polling worker is simpler and keeps one less failure point. Revisit when sync volume or reminder fan-out grows.
- **AWS deployment:** a single host suffices for a demo; the container setup is cloud-portable.
- **Text-to-SQL for managers:** non-deterministic and unsafe; replaced by a fixed intent allow-list.
- **Local SQLite replica:** only justified if reps must browse customer data offline; not P0.

## Consequences
+ Smaller surface area and faster delivery.
+ Clear upgrade path (worker, broker, cloud).
− If the LLM is unavailable, extraction falls back to a weaker offline provider, limiting the live demo; this must be resolved early.
− Streaming STT is deferred; the thread UI shows transcript after upload rather than word-by-word.

## Alternatives considered
Node/NestJS backend (loses Python audio tooling and team skill); Flutter (second UI stack for no gain); Firebase (weaker relational reporting and transactional guarantees).

## Amendment 2026-11-04 (after reading the Gnani docs)
- **No Gnani SDK.** Version 0.8.1 does not expose `codemix`, `timbre-v3.0` or `hi-en`, which are central to the Hinglish goal. We write a small httpx client, with the offline provider implementing the same interface.
- **Segment-then-transcribe** for long visits because STT REST is capped at 30 s; streaming is deferred to P2.
- **A single Gnani call gate** because the default is one active request at a time.
- **Recorder parity:** web encodes WAV client-side; Android uploads AAC/M4A.
- **TTS default:** try `timbre-v3.0` (all-language voices) and keep `timbre-v2.5` + `hi-en` as the Hinglish alternative; choose by listening test, not assumption.
