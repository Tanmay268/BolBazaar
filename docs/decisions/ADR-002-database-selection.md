# ADR-002: Database Selection

- **Status:** Proposed
- **Date:** 2026-11-04

## Context
The product writes related records atomically (visit, orders, items, collections, commitments) and reports on them (overdue payments, inactive retailers, conversion). Drafts are semi-structured and versioned. Matching spoken names to catalogue and retailers needs fuzzy search. A single JSON file would not scale to concurrent reps or aggregation queries.

## Options

| Option | Pros | Cons |
|---|---|---|
| **PostgreSQL** | ACID transactions, constraints for idempotency, jsonb, `pg_trgm`, window functions for analytics, mature tooling | Needs a running service (Docker) |
| SQLite | Zero setup | Weak concurrency, no trigram without extensions, awkward multi-user |
| MongoDB | Flexible drafts | Weaker relational integrity and reporting joins |
| JSON file | Trivial | No concurrency, no analytics, whole-state rewrite on each write |

## Decision
PostgreSQL 16 for all server data. Draft payloads stored as `jsonb` in an append-only `capture_drafts` table; business facts are normalised relational tables. Uniqueness constraints (`visits.capture_id`, `sync_ops.client_op_id`, idempotency scope) enforce at-most-once effects in the database, not only in code.

## Consequences
+ Real transactions make "confirm" atomic; analytics are plain SQL.
+ Fuzzy entity matching via trigram indexes.
− Migrations and a container are required; a seeded demo dataset must be maintained.
− Audio is not stored in the database (object/file storage with keys), avoiding database bloat.

## Amendment 2026-11-04 (implementation)
Models use SQLAlchemy 2.0 with portable types (`JSON` rather than `jsonb`, no database trigram index) so the same code runs on SQLite for tests and local dev and on PostgreSQL for deployment. Fuzzy matching is done in Python (rapidfuzz) over the small per-territory retailer and catalogue lists, which is fast enough and avoids a Postgres-only dependency. If lists grow to many thousands, move matching to `pg_trgm`. Uniqueness-based guarantees (`visits.capture_id`, draft primary key, idempotency scope) hold on both engines. **PostgreSQL has not yet been exercised in tests**; that is a pending task.

## Follow-ups
Choose a migration tool (Alembic) and define seed data; add row scoping tests for rep/manager/admin roles.
