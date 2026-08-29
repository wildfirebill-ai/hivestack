# ADR-0001: SQLite hardening (WAL) and versioned migrations

Status: Accepted
Date: 2026-08-29

## Context

The platform persists everything to a single SQLite file under `/data`. As an
always-on container on Unraid, it faces concurrent reads (chat, dashboard, memory)
while background jobs (AIOps telemetry, workflows, maintenance) write. Historically
the connection used default journal mode and schema was created with
`CREATE TABLE IF NOT EXISTS` plus ad-hoc `_ensure_columns` `ALTER TABLE` calls.

## Decision

1. **WAL + pragmas.** Every connection sets `PRAGMA journal_mode=WAL`,
   `PRAGMA foreign_keys=ON`, `PRAGMA sync_mode=NORMAL`, and `PRAGMA busy_timeout=10000`
   so concurrent reads don't block on writes and short writer locks don't 500.
2. **Versioned migrations.** Schema version is tracked with `PRAGMA user_version` and a
   single append-only `MIGRATIONS` list in `db.py`. New schema changes go in as a new
   migration entry and are applied in order; applied migrations are never edited.

## Consequences

- The single portable file remains backup-friendly (one file per volume).
- Future column/table changes are controlled and reversible instead of ad-hoc `ALTER`.
- `PRAGMA user_version` gives tools/ops an easy way to confirm the schema version.
- Slight write amplification from WAL is acceptable for this workload.

## See also

- `docker/maintenance.sh` runs periodic `VACUUM` + dated backups.
- `../PLAN.md` §5 D8/D15 (memory SQLite-backed, single file per volume).
