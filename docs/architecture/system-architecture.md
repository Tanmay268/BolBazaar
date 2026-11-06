# System Architecture

## Context

```mermaid
flowchart TB
  Rep["Field rep (Android / browser)"]
  Mgr["Sales manager (web dashboard)"]
  FF["FieldForce AI platform"]
  Gnani["Gnani STT / TTS"]
  LLM["LLM provider"]
  Rep -- "voice, taps" --> FF
  Mgr -- "queries, dashboards" --> FF
  FF -- "audio / text" --> Gnani
  FF -- "transcript + schema" --> LLM
  Gnani -- "transcript / speech" --> FF
  LLM -- "structured JSON" --> FF
```

## Containers

```mermaid
flowchart LR
  subgraph Clients
    RA["Rep app: React + TS + Capacitor"]
    MD["Manager dashboard: React + TS"]
  end
  subgraph Backend["FastAPI modular monolith"]
    API["api (routers, auth, RBAC)"]
    CAP["captures (lifecycle, orchestrator)"]
    EXT["extraction (prompts, schemas)"]
    RES["resolution (customers, products, dates)"]
    CLA["clarification (questions, patches)"]
    COM["commit (transaction, outbox)"]
    CMT["commitments (tasks, scheduler)"]
    MET["metrics (named queries, ask)"]
    PRV["providers (stt, tts, llm, offline)"]
  end
  DB[("PostgreSQL")]
  FS[("Audio storage")]
  RA --> API
  MD --> API
  API --> CAP --> PRV
  CAP --> EXT --> PRV
  EXT --> RES --> CLA
  API --> COM --> DB
  COM --> PRV
  CMT --> DB
  MET --> DB
  CAP --> FS
```

Why a modular monolith: one deployable unit is faster to build and demo; module boundaries (separate packages, no cross-imports except through service interfaces) keep a later split possible.

## Layering rules
1. `api` depends on services; services depend on `domain` and `providers` interfaces.
2. `domain` is pure (no I/O).
3. Only `commit` writes business tables, and only inside one transaction.
4. Providers are injected; the offline implementation must satisfy the same contract tests as live ones.

## Provider interfaces (conceptual)
- `SpeechToText.transcribe(audio, language) -> Transcript{text, language, requestId}`
- `TextToSpeech.synthesize(text, language) -> Audio{bytes, contentType}`
- `Reasoner.extract(transcript, context, schema) -> JSON`, `Reasoner.patch(draft, utterance) -> PatchOps`

## Failure domains
| Failure | Effect |
|---|---|
| STT down | Capture stays `RECORDED`/`FAILED`, retryable; audio kept |
| LLM invalid output | Rejected by schema; retry once, then `FAILED` with category |
| TTS down | Commit unaffected; reply marked failed; UI shows text |
| DB commit error | Whole transaction rolled back; client retries with same key |
| Network loss on device | Capture queued locally; synced later |
