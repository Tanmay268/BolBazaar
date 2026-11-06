# Database ERD

```mermaid
erDiagram
  ORGANIZATIONS ||--o{ USERS : has
  ORGANIZATIONS ||--o{ TERRITORIES : has
  ORGANIZATIONS ||--o{ CUSTOMERS : has
  ORGANIZATIONS ||--o{ PRODUCTS : has
  TERRITORIES ||--o{ CUSTOMERS : contains
  USERS ||--o{ CUSTOMERS : owns
  CUSTOMERS ||--o{ CUSTOMER_ALIASES : known_as
  PRODUCTS ||--o{ PRODUCT_ALIASES : known_as
  USERS ||--o{ CAPTURES : records
  CAPTURES ||--o{ CAPTURE_DRAFTS : revisions
  CAPTURES ||--o{ CLARIFICATIONS : asks
  CAPTURES ||--o| VISITS : commits_to
  CAPTURES ||--o| REPLY_AUDIO : answered_by
  CUSTOMERS ||--o{ VISITS : visited
  VISITS ||--o{ ORDERS : yields
  ORDERS ||--o{ ORDER_ITEMS : contains
  PRODUCTS ||--o{ ORDER_ITEMS : ordered
  VISITS ||--o{ COLLECTIONS : records
  VISITS ||--o{ COMPLAINTS : records
  VISITS ||--o{ COMPETITOR_NOTES : records
  VISITS ||--o{ COMMITMENTS : creates
  CUSTOMERS ||--o{ COMMITMENTS : concerns
  USERS ||--o{ COMMITMENTS : responsible

  ORGANIZATIONS {
    text id PK
    text name
    text timezone
  }
  USERS {
    text id PK
    text organization_id FK
    text role
    text territory_id FK
  }
  CUSTOMERS {
    text id PK
    text territory_id FK
    text owner_rep_id FK
    text name
    bigint outstanding_paise
  }
  PRODUCTS {
    text id PK
    text name
    text base_unit
    int units_per_pack
    bigint price_paise
  }
  CAPTURES {
    text id PK
    text rep_id FK
    text state
    int revision
    text language
    text transcript
  }
  CAPTURE_DRAFTS {
    text capture_id PK
    int revision PK
    jsonb payload
  }
  VISITS {
    text id PK
    text capture_id UK
    text customer_id FK
    timestamptz visited_at
  }
  ORDERS {
    text id PK
    text visit_id FK
    text status
    bigint total_paise
  }
  ORDER_ITEMS {
    text id PK
    text order_id FK
    text product_id FK
    int quantity
    text unit
  }
  COMMITMENTS {
    text id PK
    text visit_id FK
    text owner_rep_id FK
    text action_type
    date due_date
    text status
  }
  COLLECTIONS {
    text id PK
    text visit_id FK
    bigint amount_paise
    text kind
    date due_date
  }
  COMPLAINTS {
    text id PK
    text visit_id FK
    text category
    text status
  }
```

Support tables not drawn for readability: `idempotency_keys`, `outbox_events`, `audit_log`, `reply_audio`, `customer_aliases`, `product_aliases`. The open clarification question is derived from the current draft revision's issues (no separate table). See [DATABASE_SCHEMA.md](../../DATABASE_SCHEMA.md).
