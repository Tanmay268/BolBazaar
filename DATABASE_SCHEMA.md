# Database Schema

Implemented in [backend/src/fieldforce/models.py](backend/src/fieldforce/models.py) with SQLAlchemy 2.0 using portable types: SQLite for tests/local dev, PostgreSQL for deployment (ADR-002 amendment). ERD: [docs/architecture/database-erd.md](docs/architecture/database-erd.md). Tables are created with `create_all`; **Alembic migrations are not written yet** (see TASKS).

## Conventions
Prefixed text IDs (`cus_`, `prd_`, `cap_`…), `org_id` on tenant tables, money as `bigint` paise, UTC timestamps (a `UTCDateTime` type returns aware datetimes even on SQLite), audio stored on disk/object storage and referenced by key.

## Tables

| Table | Key columns | Notes |
|---|---|---|
| organizations | id, name, timezone, default_language | Tenant |
| territories | id, org_id, name, manager_id | Scope for managers and reps |
| users | id, org_id, username (unique), role, territory_id, password_hash | PBKDF2 hash |
| customers, customer_aliases | territory_id, outstanding_paise; alias | Retailers and spoken names |
| products, product_aliases | base_unit, units_per_pack, price_paise; alias | Catalogue |
| captures | id, rep_id, state, revision, language, source, transcript, audio_key, customer_hint_id, error_category/stage, committed_visit_id | One spoken interaction |
| capture_drafts | PK(capture_id, revision), payload JSON, issues JSON | Immutable revisions; the open question is **derived** from `issues[0]` (no separate clarifications table) |
| visits | id, capture_id (unique, nullable for seed history), rep_id, customer_id, visited_at, purpose, summary | |
| orders, order_items | order: visit_id, total_paise, delivery_date; item: product_id, quantity, unit, unit_price_paise, line_total_paise | Totals computed server-side from catalogue prices |
| collections | visit_id, amount_paise, kind (received/promised), due_date | Received reduces `customers.outstanding_paise`; orders increase it |
| complaints | visit_id, product_id?, category, description, status | |
| competitor_notes | visit_id, competitor, note | |
| commitments | visit_id, customer_id, owner_rep_id, action_type, description, **due_date (date)**, priority, status, source_phrase | Index on (owner, status, due_date) |
| idempotency_keys | scope PK, fingerprint, ref_id, response JSON | Capture creation stores `ref_id`; confirm stores the full response |
| outbox_events | type, aggregate_id, payload, delivered_at | Written in the commit transaction |
| reply_audio | capture_id (unique), audio_key, text, status, error_category | TTS result, written after commit |
| audit_log | actor_id, action, entity, entity_id, meta | |

## Integrity rules
- `visits.capture_id` unique → a capture can commit once even under races.
- Drafts are append-only; a concurrent edit collides on the `(capture_id, revision)` primary key and returns `STALE_REVISION`.
- Commit recomputes prices from the catalogue and re-validates the draft; client-supplied totals are never trusted.
- Reps only reach retailers of their territory; managers only territories where `territories.manager_id` is theirs.

## Not yet implemented
Alembic migrations, trigram/fuzzy DB indexes (matching is done in Python with rapidfuzz), targets table for region-vs-target, soft-delete/GDPR deletion flow.
