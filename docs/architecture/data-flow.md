# Data Flow

## Visit capture to committed records

```mermaid
flowchart TD
  A["Rep speaks"] --> B["Audio capture on device"]
  B --> C{"Online?"}
  C -- "no" --> Q["Local queue with client op id"]
  Q --> C
  C -- "yes" --> D["POST /captures"]
  D --> E["Validate type and size"]
  E --> F["Normalise audio if needed"]
  F --> G["Gnani STT"]
  G --> H["Transcript stored"]
  H --> I["LLM extraction into visit bundle schema"]
  I --> J{"Schema valid?"}
  J -- "no" --> K["Retry once, else FAILED"]
  J -- "yes" --> L["Business validation and entity resolution"]
  L --> M{"Issues?"}
  M -- "yes" --> N["Ask one clarification"]
  N --> O["Rep answers or corrects"]
  O --> P["Apply whitelisted patch, new revision"]
  P --> L
  M -- "no" --> R["Review screen"]
  R --> S{"Rep confirms?"}
  S -- "correction" --> O
  S -- "yes" --> T["Commit transaction"]
  T --> U[("PostgreSQL")]
  T --> V["Outbox event"]
  V --> W["Gnani TTS reply"]
  W --> X["Play spoken confirmation"]
  U --> Y["Manager dashboard"]
```

## Data classification

| Data | Where | Retention |
|---|---|---|
| Raw audio | Object/file storage | `AUDIO_RETENTION_HOURS`, then deleted |
| Transcript | `captures` | With the capture; excluded from logs |
| Drafts | `capture_drafts` | Immutable revisions kept for audit |
| Business records | visits, orders, collections, complaints, commitments | Permanent |
| Reply audio | storage + `reply_audio` | Same as raw audio |

## Manager question flow

```mermaid
flowchart LR
  Q["Question: text or voice"] --> S["Gnani STT if audio"]
  S --> I["LLM maps to intent + parameters"]
  I --> V{"Intent in allow-list?"}
  V -- "no" --> N["Say it cannot answer"]
  V -- "yes" --> P["Parameterised SQL query"]
  P --> R["Rows and computed metrics"]
  R --> F["Template or LLM phrases the answer from rows only"]
  F --> T["Gnani TTS optional"]
```

The LLM never produces numbers; it only selects an intent and phrases results already computed by SQL.
