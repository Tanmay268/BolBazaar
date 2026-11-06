# Sequence Diagrams

## 1. Capture, clarification, correction, confirm (demo scenario)

```mermaid
sequenceDiagram
  actor Rep
  participant App as Rep app
  participant API as FastAPI
  participant STT as Gnani STT
  participant LLM as LLM
  participant DB as PostgreSQL
  participant TTS as Gnani TTS

  Rep->>App: Speak the visit summary
  App->>API: POST /captures (audio, Idempotency-Key)
  API->>STT: transcribe(audio, language)
  STT-->>API: transcript
  API->>LLM: extract(transcript, customer + catalogue context)
  LLM-->>API: visit bundle JSON
  API->>API: schema + business validation
  API-->>App: state NEEDS_CLARIFICATION, draft, question
  App->>Rep: Shows cards, asks which Parle-G pack
  Rep->>App: Speaks "the 10 rupee one"
  App->>API: POST /answers (revision 1)
  API-->>App: READY_FOR_REVIEW, revision 2
  Rep->>App: "Make juice 12 bottles"
  App->>API: POST /corrections (audio)
  API->>STT: transcribe
  API->>LLM: patch(draft, utterance)
  LLM-->>API: patch ops
  API->>API: whitelist check
  API-->>App: diff old to new, revision 3
  Rep->>App: Tap Confirm
  App->>API: POST /confirm (revision 3)
  API->>DB: single transaction
  DB-->>API: committed
  API-->>App: created record ids
  API->>TTS: synthesize(confirmation)
  TTS-->>API: audio
  API-->>App: reply audio URL
  App->>Rep: Plays spoken confirmation
```

## 2. Idempotent replay and stale revision

```mermaid
sequenceDiagram
  participant App
  participant API
  participant DB
  App->>API: POST /confirm (key K, revision 3)
  API->>DB: commit + store response under K
  Note over App,API: network drops before response
  App->>API: POST /confirm (key K, revision 3)
  API->>DB: lookup K
  DB-->>API: stored response
  API-->>App: same response, no duplicate order
  App->>API: POST /corrections (revision 2)
  API-->>App: 409 STALE_REVISION with current revision
```

## 3. Offline capture and sync

```mermaid
sequenceDiagram
  actor Rep
  participant App
  participant Q as Local queue
  participant API
  Rep->>App: Record visit (no network)
  App->>Q: Save audio + client op id
  App-->>Rep: Shows "Saved, will upload"
  Note over App: connectivity returns
  App->>API: POST /sync/captures (op ids)
  API->>API: dedupe on client op id
  API-->>App: capture ids and states
  App->>Rep: Notifies drafts ready for review
```

## 4. Post-commit TTS failure

```mermaid
sequenceDiagram
  participant API
  participant DB
  participant TTS
  API->>DB: commit visit, orders, commitments
  DB-->>API: ok
  API->>TTS: synthesize(text)
  TTS--xAPI: error
  API->>DB: mark reply FAILED
  API-->>API: Respond success with reply status FAILED
```
